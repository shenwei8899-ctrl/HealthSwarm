# 指标助手按角色检索专题科普库

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_family_kb_service.py

## 问题

三个指标助手可回顾授权记录和检索审核证据，但知识库管理页面导入的专题资料没有进入其工具链。用户确认先提供一般科普检索，保持模型和政策暂缓。

## 决策

复用现有科普工具与来源校验。服务器按真实 AgentRun 角色选择环境配置中的知识库 ID 清单，三个指标角色分别使用自己的清单，普通咨询保留现有单库配置。API 与 Worker 使用相同配置，不从名称、用户输入或模型参数推断库权限。

检索对每个绑定库执行只读 BM25，关闭外部 embedding、rerank 与图检索；合并结果最多四个片段。多库回执记录有序库清单，各片段保留独立库、文件、分片及版本。普通咨询的单库回执保持兼容。检索前后校验成员、用途和 Run；checkpoint、发布、结果与审计按原角色重验当前绑定和来源，绑定变更或资料失效拒绝旧正文。

工具依赖、固定工具列表与三个指标 Skill 同步装配。片段只用于一般科普，记录回顾权限和专业规则门槛不变。本轮不自动启用真实模型、不部署生产、不索引未处理文件，也不扩展配餐计算或普通咨询的库范围。

## 替代方案

在普通 Agent 配置里开放任意知识库会绕过当前健康用途工具约束。复制三个检索服务会重复来源和撤权校验。复用一个受控来源服务并按真实角色限库，维护面较小。

## 验收标准

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 三个角色只检索自己的配置库 | 用户输入或其他角色取得越界片段 | health_family_kb_service | 定向 unit、隔离 PG integration、双库 Worker 回放 | 越界库、绑定变化、缺配置 | Passed |
| 同 Run 来源在发布和读取时仍有效 | 旧版本或其他 Run 引用泄露 | 同上及 conversation_service | PG 来源、锁与真实任务/审计路由验证 | 改版、删除、撤权、跨角色回执、未完成审计 | Passed |
| 工具在真实装配路径可用 | Skill 与固定工具不同步 | graph、health_consultation_service、Skill | 三角色装配测试及真实 HTTP/Worker/Milvus/PG 回放 | 缺依赖、错误工具与来源改版 | Passed |
| 普通咨询保持单库兼容 | 旧回执被错误拒绝或扩大范围 | health_family_kb_service | 原单库测试与 PG 集成 | 错库与伪造引用 | Passed |

## 验证

2026-10-20，独立内部网络与合成数据库中执行：

- `python -m pytest test/unit/services -k health -q --disable-warnings`：2301 passed、872 deselected；不是全后端单元测试。
- `python -m pytest test/integration/services/test_health_family_kb_sources.py -q`：5 passed；真实 PostgreSQL，任务和审计路由使用 ASGI transport。
- `python -m pytest test/e2e/test_health_indicator_agents_e2e.py -q --disable-warnings`：6 passed、0 skipped。三个新用例走真实 TCP HTTP、ARQ Worker、双库 Milvus BM25、同 Run 工具审计、最终 Message 和任务回读，次库改版后返回 410；另三个用例覆盖原有记录、审核引用、更正和作废。模型由独立合成协议服务重放，不调用真实供应商。
- 测试清理后回读：测试账号、Run、专题库、分片均为 0，Milvus 测试集合与 Redis 对应知识库配置缓存均为空。

回执为 `backend/test/.tmp/indicator-topic-20261020/result.xml`、`final-e2e.log`、`cleanup.json`。独立 Reviewer 发现的审计消费者遗漏与旧两工具回放契约均已修复。Ruff、工程契约及 63 项 gate 测试通过。生产部署、正式库绑定、真实模型答复与人工质量验收未执行。

## 后果

数据库索引状态不能证明 Milvus 当前可检索。生产绑定、真实检索和真实模型答复分别验收；本轮使用隔离合成资料，不能算生产质量验收。任一配置库不可用时明确返回不可用，不静默省略资料库。
