# 审核科普片段的本地词法索引与检索评估

状态：implemented
类型：feature
Owner：backend/package/yuxi/repositories/health_evidence_repository.py

## 问题

原健康知识工具只做连续整句包含查询，并按创建时间返回五条，无法检索分散关键词或表达词法相关度。现有 `NutritionEvidence` 的稳定片段 ID、版本、正文 hash、审核凭据、撤回和有效期已经足够验证受限 `general_education` 工程，但尚未接入检索评估。

图引用 validator 结束独立事务之后，来源仍可能在最终 Message 提交前撤回。已完成回答也可能经普通 result、history、state 消息或 search 摘要重新公开，专用引用入口的拒绝不能替代这些正文边界。读者为健康检索、Agent 与接口维护者；既有指针政策见[引用决定](2026-10-10-health-consultation-citations.md)。

搜索在来源校验前限制摘要和线程页会丢失较早的有效回答，并把摘要数量误当完整匹配数。健康咨询须先逐条核对公开 Message，再统计有效匹配、取有限摘要、按最新公开匹配排序并分页。

## 决策

### 实现方案

知识工具仍只接受短关键词，账号、成员、用途和执行 lease 由 consultation Owner 固定。repository（`backend/package/yuxi/repositories/health_evidence_repository.py`） 读取 PostgreSQL 当前未撤回、未过期的审核科普片段，本地 adapter（`backend/package/yuxi/services/health_evidence_index.py`） 使用已声明的 scikit-learn `TfidfVectorizer` 建立短生命周期字符 `char_wb` 1–3 稀疏索引。Unicode 词法项均须出现，再按 TF-IDF 相关度与稳定 ID 排序返回最多五个命中；单字及零分合法候选保留稳定排序。已批准片段本身就是 chunk，不再次分块，不调用 embedding，不开放模型选择通用知识库。

adapter 只返回 ID、版本和 hash。命中后 repository 按稳定来源 ID 顺序 fresh `FOR SHARE` 锁读，使用 `populate_existing` 避免 identity map 旧值，核对版本、hash、真实正文摘要、标题快照、撤回和 UTC 有效期。标题不在既有正文 hash 内，单独比较快照防止仅标题变化后的旧命中。缺 proof 或不符返回 `source_invalidated`，不发布索引正文；service（`backend/package/yuxi/services/health_evidence_service.py`） 在纯计算结束后重验当前 attempt，再创建同 Run 引用。

每次查询从当前 PG 重建，发布、撤回、过期和新版本自然同步到下一次读取；没有持久 cache、第二套来源状态、新表、Schema 版本或索引设施。上限为 1000 片段、单条标题及正文 4200 字符、总文本 420 万字符、10 万词法特征；单条上限对应发布 DTO 的标题 200 字与正文 4000 字。SQL 读取 N+1 行及正文上限加一字符发现异常，不能截短参与索引；词表提前枚举至上限加一，在建矩阵前 fail closed，不用 `max_features` 静默截断。查询沿既有 120 字符边界。

CPU 索引在纯后台线程执行，每进程最多一个构建。排队取消不提交线程，native 线程 `finally` 在实际结束时释放许可；awaiter 使用 shield，取消仅设置计算标志。线程不接收 Session、Run Context 或模型，不执行 IO 或业务写入；取消后不回到原 Owner 链，不延长执行预算。

chat final save（`backend/package/yuxi/services/chat_service.py`） 在已经锁住 Run 的 owning Session 内调用 evidence publication guard。规范提取最终正文实际引用，本 Run 曾取得证据时不能完全漏引用；严格核对 actor/member/thread/run，fresh SHARE 锁持有至普通 Message、权威 pointer 与 completed 同事务提交。图校验后撤回、过期、改正文或换别 Run 引用仍拒绝发布，保留私有审计。无检索、无引用的普通咨询兼容；预算和 partial 失败守卫保持原 Owner。

只读正文 guard 使用当前成员授权及权威最终指针，验证实际采用的同 Run 引用，不要求新模型处理审批，不查询未采用回执。普通 result（`backend/package/yuxi/services/agent_run_service.py`） 将失效转为无正文的受控 HTTP 错误；history 与 search（`backend/package/yuxi/services/conversation_service.py`） 仅隐藏失效 answer，保留同线程其他有效 Run。咨询 `state?include_messages=true` 从公开 PG history 窄投影，不原样公开 checkpoint 工具、审计或未发布候选。默认 state 和非健康 Agent 兼容；不改变通用 authorize、SSE 或 Run 终态。旧 completed 咨询缺明确 pointer 时沿引用入口的严格政策拒绝猜测。历史轻量 Run 显式载入所需五个身份及指针字段，保留 `raiseload=True`；search 返回既有 DTO 必需的工作目录字段，摘要由实际 Message 重建。

咨询搜索的 repository（`backend/package/yuxi/repositories/conversation_repository.py`）沿既有关键词转义、普通消息及来源排除条件，分批读取当前账号 active 咨询的完整候选。service 先核对成员授权及每条 Message 的公开性，统计全部有效匹配，只保留既有两条摘要；最新匹配时间取最新公开 Message。混合搜索取得所需前缀的可见非咨询线程，与咨询汇总按公开匹配时间排序后再执行 offset、limit 和 has_more。较新的全失效线程不占分页；失效的近期回答不吞较早有效 Run；匹配数独立于摘要数。明确选择普通 Agent 时沿用原查询与计数。

合成 query→gold evidence ID 使用现有 Recall/F1 Owner（`backend/package/yuxi/knowledge/eval/metrics.py`），由评估适配（`backend/test/support/health_evidence_evaluation.py`）映射真实发布 ID。gold 查询与必需来源独立声明，不从命中结果生成期望；实际 Worker 最终引用与原片段核对。专业语料、适用人群、医学必要依据及专业 gold 继续待对接，五个角色保持 `partial`。

## 替代方案

- 通用 Milvus KB 同时要求 dense embedding，可能扩大处理方，不用于本次受限查询。
- 健康 sparse collection 可复用基础设施，但增加派生同步与恢复状态，当前片段规模采用 live-PG 本地索引。
- 连续整句包含和最新排序不能关闭分散关键词与相关度缺口。
- 全量持久缓存增加失效时序及第二套事实，每次重建避免这项维护面。

## 后果

字符 TF-IDF 只证明词法相关度，不理解同义词或医学语义。所有片段仍为审核登记的 `general_education`，合成指标不提升为个人临床方案或专业质量结论。完整专业来源和适用范围由 A/专业方提供。

每次重建成本随语料增长，超界明确失败；扩大规模需要新的容量取舍。线程不能强制终止已进入的矩阵计算，因此纯计算、容量和并发上限共同限制影响。验收证明逐 query 和新 adapter 重建，不声称实际进程重启前后同来源验收；没有新增持久状态需要恢复。

咨询搜索为取得准确公开匹配数，需要校验全部符合关键词的候选，延迟随历史命中数增长。PG 游标每批 100 条，每线程仅保存两条公开摘要及汇总；没有查询缓存、额外状态或向客户端发送全部候选。性能数据不构成生产搜索 SLO。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 词法检索与稳定排序，片段不重复分块 | 连续原句、日期排序或单字丢失 | local adapter/repository | index及lease unit、实际PG/HTTP | 分散词、英文/CJK、空语料/空词、无交集、单字、零分及同分 | Passed |
| 索引有界且CPU不阻塞async | 无界矩阵、取消提前释放许可 | local adapter/既有Run预算 | 容量、offload、native/queued cancel unit与资源测量 | N+1、超字符/特征上限、取消后不回Owner写引用 | Passed |
| 逐查询读取当前语料 | 旧cache、静默截断、不能恢复新版本 | PG source/on-read重建 | 实际发布/撤回/过期/新版本及新adapter回读 | 旧ID不命中、容量明确不可用；未运行进程重启对照 | Passed |
| 命中取得fresh当前来源proof | identity map旧值或伪造hit | repository/service | 双sessionPG竞态、真实HTTP14case | 撤回/删除/过期/版本/hash/正文/仅标题变化、错hit/重复ID | Passed |
| 合成检索及引用评估 | 自造指标、动态gold、缺依据仍合格 | 现有Recall/F1 | 独立固定指标unit、实际Worker gold ID | 无命中、漏依据、重复/伪造ID、无gold不评估 | Passed |
| 最终发布与来源保持同事务 | 图验证后撤回仍提交正文 | owning Chat/evidence guard | 实际finalsave、PG SHARE NOWAIT及纯unit | 图校验后撤回/过期/正文篡改/换Run；无text/pointer/completed | Passed |
| 四正文读取只守实际采用来源 | 失效正文旁路或误封邻Run | result/history/state/search services | 真实HTTP同线程两Run、实际checkpoint Worker | 未采用C撤回不误封A，B失效隐藏、私有工具不公开、special410保留 | Passed |
| 搜索有效匹配先统计再分页和限制摘要 | 最近失效片段吞掉较早有效Run，摘要数冒充总数 | conversation service/repository | 四completed Run及跨线程真实HTTP | 最新三条失效、四条有效、失效线程占页、普通Agent兼容 | Passed |
| 实际装配与零残留 | helper通过但正式Worker/PG不符 | 固定11工具、Run/citation Owner | lexical与nutritionist E2E、精确资源/配置/队列回读 | 别Run/伪造引用、来源撤回失败无正文、回放helper精确停止 | Passed |
| 生产专业RAG质量与新处理用途 | 合成被误当专业或云审批 | A专业数据/运营用途 | 正式语料、适用范围及专业gold/处理方审批 | 科普不升级为个体临床方案 | Not run |

实际验证命令在隔离合成槽位运行，均使用 `uv run --no-sync --group test pytest`；常规兼容、PG与Worker批次禁用pytest缓存，专属35项unit使用已有测试临时缓存目录：

- `test/unit/services/test_health_evidence_index.py`、`test_health_evidence_index_publication.py`、现有引用/营养师及 chat/result/state/history/partial 初次兼容集：200 passed，102.04 秒；后续显式Run投影与search DTO字段修正由35项专项及真实11项HTTP重验，完整装配沿最终门禁记录。
- `test/unit/services/test_health_evidence_publication.py test/unit/services/test_health_evidence_read_boundary.py`：35 passed，56.61 秒。独立测试进程函数副本的 9 种有效变异触发 10 项业务、SQL及DTO断言失败，均取得预期 exit 1；生产文件及运行配置未变异。
- `test/unit/services/test_health_evidence_search_visibility.py`：14 passed，58.32 秒。11 种测试进程函数副本变异各触发一项预期业务或 SQL 断言失败，覆盖摘要提前截断、有效总数、公开时间、分页与 has_more、普通候选补页、公开性校验，以及当前账号、审计排除、fresh 候选和无 LIMIT；生产源码与运行配置未变异。
- `test/integration/services/test_health_evidence_lexical_http.py test/integration/services/test_health_consultation_citations_http.py`：16 passed，61.06 秒。
- `test/integration/services/test_health_evidence_final_publication_http.py test/integration/services/test_health_consultation_citations_http.py`：11 passed，90.40 秒。前两轮各 4 passed/1 failed 的真实失败日志保留；补齐轻量 Run 显式字段及搜索必需 DTO 字段后完整重验。未删除或削弱四入口负控。
- `test/integration/services/test_health_evidence_search_visibility_http.py test/integration/services/test_health_evidence_final_publication_http.py test/integration/services/test_health_consultation_citations_http.py`：14 passed，106.32 秒。三个新增场景各有四条真实 completed Run/权威 Message，验证全量有效计数与两条摘要、最新三条撤回后最早有效回答、全失效线程不占页、混合普通线程完整计数；读取不改变 completed 或 pointer。搜索修复后的现有 `test_health_evidence_read_boundary.py` 及 `test/unit/storage/test_conversation_repository.py`：30 passed，56.90 秒。
- `test/e2e/test_health_evidence_lexical_e2e.py test/e2e/test_health_nutritionist_e2e.py`：2 passed，43.58 秒。实际 Worker 的 gold 两条→新版本一条均 Recall/F1=1，实际 checkpoint 保留工具事实但公开 state 不暴露工具正文。

publication PG fixture 使用真实 Request/Run/attempt、检索 service、图 validator、Model lifecycle 和 owning final-save；未投递模型任务或创建 runtime，合成 Owner 收尾与实际 Worker 清理分别验证。最终 50 张健康表、Run/Request/Attempt/Message 均零行；所有七类健康模型及审批恢复关闭，完整配置与24个provider哈希和默认ARQ空队列基线一致，独占8766 helper精确停止、端口关闭、API ready 200、Worker healthy且未暂停。没有主服务配置变更或新云调用。

宿主 scikit-learn 1.9.1 预热纯计算实测：3条/240字符 0.003秒；1000条/420万字符 6.433秒，10毫秒heartbeat执行205次、最大间隔0.046秒；400条/40400字符的独立特征语料超10万特征时0.046秒拒绝。它仅支持容量取舍，不是SLO。完整命令、独立gold、变异选择及实际日志保留在 `agent/.tmp/agent-completion-20261010/`，正式门禁沿[测试指南](../../testing-guidelines.md)。本记录不替代最终全后端及freshCI装配结果。
