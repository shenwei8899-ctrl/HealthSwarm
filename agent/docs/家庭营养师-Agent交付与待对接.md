# 家庭营养师 Agent 交付与待对接

更新日期：2026-10-13。本文依据当前源码、决策记录和实际验收整理交接事实；原始分工见[模块划分](家庭营养师平台-Agent模块划分.md)。A 负责专业数据、计算、校验及业务结果；B 负责 Agent、受控工具、检索、图片交互、采购适配和运行监控。正式小程序页面由同事负责。

## 当前可交付范围

当前有八个固定、受控的 Agent 入口，八个角色均保持 `partial`。完整专业资料、适用规则和外部联调未交付前，不将工程闭环标为完整营养业务完成。角色目录及剩余范围由 [health_agent_roles.py](../Yuxi-main/backend/package/yuxi/services/health_agent_roles.py) 拥有。

| 固定入口 | 当前能力 | 保留的边界 |
|---|---|---|
| `health-consultation` 家庭营养师 | 授权成员事实、本人确认档案及独立实测指标、审核科普本地检索与当前来源引用、自述记忆与每日消息摘要 | 科普回答不等于个体化临床建议；完整专业档案及跨用途协调待定 |
| `health-blood-glucose` 血糖记录助手 | 本人实测血糖回顾、测量条件追问、审核科普解释与来源重验 | 不提供控糖目标、21 天计划或诊断 |
| `health-blood-lipids` 血脂记录助手 | 本人同条血脂四项回顾、资料追问、审核科普解释与来源重验 | 不提供诊断或治疗方案；生产审核资料与模型质量待验收 |
| `health-blood-pressure` 血压记录助手 | 本人成对血压回顾、资料追问、审核科普解释与来源重验 | 不提供诊断或治疗方案；生产审核资料与模型质量待验收 |
| `health-meal-planner` 配餐师 | 普通、初始个人/家庭、家庭改版及单成员安全改版的受控预览；服务端复算、当前 Run 回执；普通模式显式次日提议 | 保存、专业复核、正式采用分别执行；21 天及自动日终/跨模式次日联动待定 |
| `health-diet-analyst` 饮食分析师 | 确认单餐和 1/7/30 天记录事实、显式选餐反馈；普通分析可选绑定当前批准个人目标 | 当前目标独立投影，不套历史窗口，不产生达标、差额、趋势或全天完成结论 |
| `health-quality` 质量审核 | 程序营养复算与限制检查、当前版本及专业状态读取 | 专业批准仍由具备资格与成员授权的业务入口执行，模型不能批准 |
| `health-purchase` 采购助手 | 有效采用餐单的可食克数汇总、用户确认同食材版本/生熟状态库存扣减、独立用途及同 Run 回执 | 无 SKU/报价/交易；`purchase_available`、`order_available` 为 `false`，生产采购用途默认关闭 |

`health-profile` 是档案业务能力，不是新增固定 Agent。角色目录的 `health-glucose` 对应 `health-blood-glucose` 固定入口，状态为 `partial`；它只回顾记录和解释审核知识，`glucose_plan` 仍未就绪。

统一入口支持十一类显式任务：`consultation`、`blood_glucose_review`、`blood_lipids_review`、`blood_pressure_review`、`meal_preview`、`initial_meal_preview`、`family_meal_revision`、`safe_meal_revision`、`diet_analysis`、`quality_check`、`purchase_requirements`。输入与结果以 [Task DTO](../Yuxi-main/backend/package/yuxi/services/health_task_types.py) 为准：

- `POST /api/health/v1/members/{member_id}/task-entries` 返回 `ready`、`needs_input` 或 `dependency_not_ready`；就绪只表示固定线程已创建，客户端仍需显式提交 `POST /api/agent/runs`。
- `GET /api/health/v1/tasks/{request_id}` 从 PostgreSQL 读取当前 Request、Run、权威最终 Message 和业务结果；排队时重新订阅 Request 当前 PG 状态，派发后 Run SSE 按游标恢复，Task GET 提供断线查询兜底。Request 排队事件没有持久事件游标。执行完成、追问、专业批准和交易状态分别表达。
- `glucose_plan`、`multi_day_plan`、`automatic_family_coordination` 当前返回 `dependency_not_ready` / `external_contract_required`。纯意图建议可由营养师 Skill 引导用户明确选择上述十一类入口；当前没有自动调用通用 subAgent 的健康协调闭环。

## 独立核心项与事实 Owner

下列决策记录保留具体命令、正负控及实际回读结果；合成工程回放不代表生产专业资料或真实模型质量验收。

| 能力 | 当前交付及验证边界 | 决策与源码 Owner |
|---|---|---|
| 任务入口与结果 | 十一类显式任务、来源重验、追问/失败/取消投影；真实 HTTP、Worker、PG 最终结果及清理回读 | [首版 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-10-health-task-projection.md)、[指标助手 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-13-health-indicator-agents.md)、[Task service](../Yuxi-main/backend/package/yuxi/services/health_task_service.py) |
| 咨询引用 | 只读当前完成咨询实际采用的引用，保序去重；同 actor/member/thread/Run 来源校验，撤回/过期/篡改返回 410；不猜测旧最终指针 | [引用 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-10-health-consultation-citations.md)、[evidence service](../Yuxi-main/backend/package/yuxi/services/health_evidence_service.py) |
| 受限知识索引与正文来源 | 审核科普逐查询重建本地词法索引，命中后 fresh PG proof；最终发布及 result/history/state/search 只公开当前有效的实际引用；搜索先统计有效匹配再限制摘要和分页；合成 Recall/F1、真实 HTTP/Worker 与零残留回读通过 | [索引 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-10-health-evidence-lexical-index.md)、[index Owner](../Yuxi-main/backend/package/yuxi/services/health_evidence_index.py)、[来源 repository](../Yuxi-main/backend/package/yuxi/repositories/health_evidence_repository.py) |
| 当前个人目标 | 普通分析师显式选择、不可变绑定，复用 A 的当前目标计算；Schema 23 正式增量迁移及实际 HTTP/Worker 验证 | [目标 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-10-health-agent-personal-targets.md)、[target service](../Yuxi-main/backend/package/yuxi/services/health_agent_personal_target_service.py) |
| 次日提议 | 用户明确选择普通单成员配餐的 Request/Run/最终 Message/预览后登记；无自动保存、采用或饮食写入；实际并发锁及 Worker 验证 | [次日 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-10-health-agent-next-day-proposal.md)、[bridge service](../Yuxi-main/backend/package/yuxi/services/health_next_day_agent_service.py) |
| 采购需求 | 当前有效个人/家庭采用、确认库存及独立用途绑定；受控两工具与同 Run 回执；真实 PG/Worker 验证 | [采购 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-10-health-purchase-agent.md)、[purchase service](../Yuxi-main/backend/package/yuxi/services/health_purchase_service.py) |
| 图片交互 | 受控上传、候选、用户确认、程序计算和正式饮食记录；识别失败保留手动路径 | [图片链路 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-04-health-meal-e2e.md)、[vision service](../Yuxi-main/backend/package/yuxi/services/health_vision_service.py) |
| 后台分析与反馈入口 | 健康识图选择成员和1/7/30日或确认单餐后进入分析会话；确认记录旁提供固定选餐反馈对话与最终事实卡片，手动反馈保留；模型用途配置完整保存采购值 | [使用说明](../Yuxi-main/docs/advanced/health-diet-analysis.md)、[入口 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-10-health-analysis-web-entry.md) |
| 追踪、用量与装配 | 安全 `trace_id`、识图供应商已报告用量与未知值分离；本地独立固定图门禁核对 Worker/PG；远端自动入口单独验收 | [观测 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-10-health-observability.md)、[statistics Owner](../Yuxi-main/backend/package/yuxi/services/health_vision_statistics.py)、[运维参考](../Yuxi-main/docs/advanced/health-agent-operations.md) |
| 执行预算与失败发布 | 八个固定健康角色按首次执行起点共享跨 attempt 预算；SDK 受剩余时限约束；咨询失败不保留回答正文或最终指针；实际取消、撤同意、lease 及重试恢复验证 | [预算 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-10-health-run-execution-budget.md)、[失败发布 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-10-health-consultation-partial-publication.md)、[Worker Owner](../Yuxi-main/backend/package/yuxi/services/run_worker.py) |

## B 的剩余接口交付

任务输入、结果分类、安全错误、七用途模型可用原因和平台 readiness 分别由当前 DTO、配置服务和系统就绪接口拥有。当前成员及任务依赖的能力汇总见[能力 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-10-health-member-capabilities.md)，饮食、草稿和任务列表的当前授权分页合同见[分页 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-10-health-meal-plan-pagination.md)。这些接口交付与正式客户端消费验收分别记录。

成员业务就绪 GET 按入口补充运行依赖、对象存储、Skill 发布登记版本和专业目录缺项；任务创建在队列或 Worker 不可用时返回明确依赖状态，不创建线程。人工路径使用自身授权，普通咨询不受专业来源目录缺失整体阻断。接入合同见[成员就绪参考](../Yuxi-main/docs/advanced/health-member-capabilities.md#按业务依赖降级入口)；正式小程序的入口禁用和允许动作展示由客户端负责人对接，目录存在不表示生产专业内容或医学质量已验收。

排队 Request 重订阅、Run 游标恢复及 Task GET 兜底沿用既有事实 Owner，接入步骤见[任务恢复参考](../Yuxi-main/docs/advanced/health-task-recovery.md)。Yuxi 聊天页补齐断流后的当前状态回读、有限重连和 Run/Request 并行恢复；恢复运行中的线程在完成当前绑定及初始状态读取后可以追加排队问题，持续 SSE 不占用输入初始化锁。正式小程序仍需对接健康结果卡片、业务结果失效、追问、取消和专业等待的具体展示并完成真机验收，该范围由同事负责。

## 待对接清单

以下必需字段是交接契约要求，不声称已存在对应生产接口。接口就绪后，B 继续接入现有业务 Owner 和运行底座，不重复建设营养计算、业务状态或通用调度设施。

### 1. A 的专业来源与 RAG：待定

- **提供方与必需契约：**A/专业审核方提供稳定 source/document/chunk ID、来源版本与正文 hash、发布/停用/替代状态、有效期、适用/排除人群及冲突元数据、审核依据；明确变更游标或版本轮询、删除标记和幂等约定。专业评估集需给出查询、应命中来源、必要依据点和正确引用。
- **当前接口状态：**PostgreSQL 审核登记的 `general_education` 科普片段已接入本地有界词法索引及合成检索/引用评估，最多五条；每次查询读取当前事实，命中重验版本/hash/标题，发布、撤回、过期和新版本同步均已验收。批准片段已是 chunk，不重复分块；未新增云 embedding、通用 KB 选择、向量库或持久缓存。最终发布和四个正文读取入口验证实际采用来源，失效回答隐藏且不误封未采用来源或相邻 Run。搜索保留较早有效回答，完整有效匹配数与有限摘要分开，排序和分页以公开匹配为准。工程结果不替代完整专业来源证明和医学质量。
- **验收触发：**正式专业语料、适用范围和必要依据 gold 到位后，B 接入已有来源、权限及检索 Owner，补专业命中、医学依据完整性和引用准确性验收；若以原始文档交付，再明确解析/分块输入与稳定来源关联。当前本地索引、更新失效及合成评估工程已完成，剩余待定是专业数据和真实质量契约。

### 2. A 的 21 天、控糖与历史目标：待定

- **提供方与必需契约：**A/专业方提供多日计划 ID/版本、日期与逐日参与者、逐日目标/规则/档案来源、局部重算和整体失效范围、专业复核/采用/替代/取消状态、原子保存与幂等接口；控糖另需批准适用人群、排除及共病冲突、测量条件（空腹/餐后/随机）、目标范围、样本与可比性、异常转专业复核规则。历史目标需有效区间、每日记录完整度/未知项、差额/达标及趋势最低样本规则。
- **当前接口状态：**当前批准目标和 1/7/30 天确认事实已可独立读取；今日目标不应用于历史窗口。独立实测血糖是事实读取，不构成控糖判定。多日/控糖 Task 入口明确为依赖未就绪，尚无正式多日业务闭环。
- **验收触发：**上述业务及批准规则契约、模型用途审批到位后，B 接入受控工具和任务分支；验证跨日版本、重算/撤回/恢复、专业门禁及 PG 最终事实。重复普通一天任务不能代替 21 天计划持久化与安全重算。

### 3. 产品跨用途协调与日终联动：待定

- **提供方与必需契约：**产品/授权及模型用途 Owner 明确成员与业务对象选择、允许的任务类型与顺序、每阶段 purpose/processor/policy_version/同意范围、失败/取消/恢复及专业等待边界；明确哪些动作必须用户确认。日终需业务日期/次日日期、触发与补跑时间、去重键、优先级事实来源、费用承担和通知许可；家庭/初始/安全模式需各自次日来源及提议契约。
- **当前接口状态：**十一类显式任务入口已可用，纯意图引导可以在营养师 Skill 完成。日终 [daily service](../Yuxi-main/backend/package/yuxi/services/health_daily_service.py) 生成消息摘要，`meal_plan_generated=false`；普通单成员次日桥接须用户显式动作。尚无自动跨成员/跨用途执行或自动登记。
- **验收触发：**流程与用途契约确认后，B 在现有 Request/Run 上落实协调；覆盖午夜边界、补跑/重复触发、成员撤权、阶段取消、来源变化及明确确认。是否需要新角色由批准流程决定，不能用通用 subAgent 绕过阶段授权。

### 4. A 的换算与商城：待定

- **提供方与必需契约：**A 提供批准的换算 ID/版本、单位、生熟状态、可食部与采购毛重维度、适用条件和未知项；商城提供 SKU/版本与食材版本映射、包装/毛重、报价 ID/有效期/价格币种、库存版本、配送范围，以及购物车/订单/支付/退款 ID、最终状态、回调/查询、幂等和未知结果核对契约。B 负责映射和商城适配。
- **当前接口状态：**`purchase-requirements` 业务读取和采购 Agent 只产生 `edible_g` 需求；仅扣明确同状态库存，未知净量保持 null，`sku_candidates=[]`，不可下单。跨状态/毛重换算、商品筛选和交易尚未接入。
- **验收触发：**批准换算与商城沙箱接口到位后，验证缺货、替换再校验、价格/包装变化再确认、重复/超时查询和权威交易回执。供应商仅获采购履约必要字段，不获健康档案；营养硬约束由 A 校验。

### 5. 运营模型用途、费用与告警：待定

- **提供方与必需契约：**用途审批/运营方确认各 purpose 的模型及 provider 指纹、processor、policy_version、成员同意期限和撤回语义；供应商提供用量/账单、价格版本、币种/生效期及失败重试/OCR 计费归属；运营确认 SLO、告警阈值、接收方和处置流程。仓库维护者确认根仓库远端 CI 入口。
- **当前接口状态：**用途配置和处理同意已有服务端门禁，未审批用途不能启用。安全错误追踪与已报告 token 统计已实现；未知不记零，`billing_complete=false`。本地固定图门禁通过不等于生产模型质量、账单对账、告警送达或远端自动 CI 通过。
- **验收触发：**审批与真实供应商契约到位后，验证配置变化/撤同意阻断、实际模型质量、失败尝试和 OCR 用量、价格版本/账单对账、告警送达及日志无健康正文；远端入口启用后另核对远端运行记录。

### 6. 同事小程序与真机：待定

- **提供方与必需契约：**页面 Owner 区分家庭档案的 `source_member_id` 与健康业务的 `member_id`，本人明确确认身份后通过[本人关联 service](../Yuxi-main/backend/package/yuxi/services/health_family_profile_service.py)建立映射。家庭创建和基础档案确认不自动创建健康业务成员或授予健康用途权限。页面接入显式任务选择、用途同意版本、`client_request_id` 与实际 `request_id`/`run_id`、结果分类及恢复查询；预览、次日提议、保存、采用分别确认。
- **当前服务端契约：**任务入口、运行结果与业务结果分类由 [Task DTO](../Yuxi-main/backend/package/yuxi/services/health_task_types.py)拥有，客户端按[任务恢复参考](../Yuxi-main/docs/advanced/health-task-recovery.md)消费 Request 与 Run，处理缺选择、409/410、取消、追问和专业等待。本人关联读写、普通咨询创建和列表的四个成功响应在 OpenAPI 声明类型，分别由本人关联及[健康响应 DTO](../Yuxi-main/backend/package/yuxi/services/health_vision_types.py)拥有。未关联保留空来源且不增加家庭字段；普通创建保留空反馈选择，列表仅含元信息和分页。健康成员列表与建档、修改授权、用途同意的四个成功响应也声明类型：成员保留裸数组和 scopes 顺序，建档返回 id，授权返回 saved:true，同意与撤回分别返回 accepted:true/false；边界及真实 HTTP/PG 证据见[成员与用途同意 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-11-health-member-access-contract.md)。当前授权和幂等由既有服务负责，模型用途同意在实际执行边界独立校验。
- **固定 Agent 会话响应：**普通配餐、饮食分析、选餐反馈与已保存餐单安全改版的四个 201 成功响应由[固定会话 DTO](../Yuxi-main/backend/package/yuxi/services/health_fixed_conversation_types.py)声明。分析未选目标时省略 `target_selection`，已选目标时保留批准版本；选餐反馈的 `feedback_selection`、安全改版的 `safe_selection` 必须包含实际来源和版本。四项业务日期为空，创建仅形成会话与业务绑定；客户端显式提交 Agent 请求后才执行。五种成功形状、幂等重放、权限和来源版本拒绝已通过真实 HTTP/PG 回读，验证边界见[固定会话 ADR](../Yuxi-main/docs/develop-guides/decisions/implemented/2026-10-13-health-fixed-conversation-contract.md)。
- **App 接入状态：**`1358318` 交付 App 的微信登录服务适配和账号家庭页面，默认仍为 mock。真实模式仅开放登录及账号家庭页；[服务注册](../../App/src/services/index.js)只注册登录，其余未适配方法返回 `ADAPTER_NOT_READY`。聊天、菜单、记忆、图片、报告、饮食记录及交易仍含本地演示逻辑，页面 Owner 需完成各页全部数据来源的适配后，再按[路由守卫](../../App/src/services/navigation.js)放行。
- **微信后台与部署待办：**主检出的 [auth 路由](../Yuxi-main/backend/server/routers/auth_router.py)仍无 `/api/auth/wechat/*`，现有 Yuxi 账号密码登录不代表微信 code 身份验证已完成。主检出的 [business schema](../Yuxi-main/backend/package/yuxi/storage/postgres/manager.py)为 12；[App README](../../App/README.md)记录的独立微信后台拟升级至 13，尚未合入主服务。微信后台负责人负责合入、正式迁移和部署，平台与客户端确认实际 AppID、公开 HTTPS 合法域名及会话身份映射。
- **请求封装待对齐：**普通咨询创建等包含 `client_request_id` 且调用 `require_request_key` 的指定写入，按[HTTP 路由](../Yuxi-main/backend/server/routers/health_vision_router.py)要求 `Idempotency-Key` 与该字段相同；本人关联等其他入口按各自请求 DTO 与路由发送。上述四个固定 Agent 会话入口只要求正文 `client_request_id`，没有额外 `Idempotency-Key` 或 `If-Match` 要求。健康成员列表、建档、修改授权及用途同意这四项没有 `client_request_id`、`Idempotency-Key` 或 `If-Match` 要求；建档每次创建新 ID，授权及用途同意更新当前槽位。调用 `require_match` 的版本编辑显式带 `If-Match: "<version>"`。健康业务错误使用顶层 `code`、`message`、`trace_id`、`retryable` 及 `detail`；[App request](../../App/src/services/request.js)当前只提供认证头、读取 `detail.code` 与请求 ID 响应头，需由页面 Owner 补充请求头和错误解析。认证错误由[认证依赖](../Yuxi-main/backend/server/utils/auth_middleware.py)返回；FastAPI 请求校验错误和健康业务错误均可使用 422，客户端按实际载荷区分。
- **验收触发：**实际客户端和联调环境到位后，用合成账号完成微信开发者工具及真机登录、上传、重复点击、断网恢复、跨账号拒绝、取消/撤权、来源变化和用户确认测试；回读同 Request/Run 的 PG 最终业务结果。实际 AppID/AppSecret、合法域名、iOS/Android 真机和真实供应商尚待验收；需要语音时另定供应商及用途契约。页面建设由同事负责，B 继续维护 Agent 服务端协议与受控业务入口。

交接关闭条件：提供方确认字段、错误状态、版本及幂等契约，B 完成真实接口与 Worker 联调并回读最终持久化结果；未运行的专业、生产模型、商城或真机验收继续保持待定。
