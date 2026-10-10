# 普通配餐 Agent 的显式次日提议登记

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_next_day_agent_service.py

## 问题

普通单成员配餐 Agent 已能持久化当前 Run 的三餐预览，并输出服务器复算后的权威回执。用户登记明日提议时，已有入口只接收预览 ID，缺少从客户端选中的 Request、完成 Run 和最终消息到预览的完整核对。客户端需要一个明确用户动作，将当前有效的 Agent 明日预览登记为可回读的提议。

读者为家庭营养业务与 Agent 后端维护者；前置知识是 [架构说明](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/ARCHITECTURE.md) 与 [测试规范](../../testing-guidelines.md)。本记录只覆盖普通单成员配餐模式的明日预览。家庭、初始、安全改版模式、自动触发建议、模型登记提议、正式采用、饮食写入和客户端页面均不在范围内；外部档案、专业规则与商城接口继续由各自 Owner 联调。

## 决策

### 实现方案

用户显式调用 `POST /api/health/v1/members/{member_id}/meal-planner-runs/{run_id}/next-day-proposals`。请求包含既有 `client_request_id`、`preview_id`、`source_date`，以及用户选中的 `request_id` 和 `final_message_id`。Request ID 沿用平台 1 至 64 字符的字符串，最终消息 ID 是严格正整数。HTTP 路由执行认证与输入解析，并禁止缓存响应。桥接 service 在同一 PostgreSQL 事务内，先取得既有提议幂等锁，再复用健康任务 repository 核对当前账号 Request、线程绑定和 Request 的 `dispatched_run_id`；路径 Run 与该 Request 的当前执行一致，固定角色为普通配餐师，路径成员与线程成员一致。

成员授权锁取得后，桥接立即拒绝非 `completed` Run，避免持成员锁等待活跃 Worker 的 Run 锁。完成 Run 是终态；桥接随后取得其写锁并 refresh，再次核对完成状态及正文指针。最终消息是 `output_message_id` 指向的同 Run、同 Request 完整 assistant 正文，不回退到相邻历史或猜测消息。

桥接在服务器重新核对当前成员授权、处理配置与用途同意，再复用普通预览的全文复算校验。用户选择的预览必须是最终消息中的回执，并属于同 actor、member、Run；计划日期必须是北京时间明天。登记在既有提议 Owner 中执行，将 Run、Request 与最终消息标识纳入幂等指纹，复用预览来源复算、食品当前来源和日期检查。采用、专业复核与实际饮食仍通过已有独立业务入口执行；模型工具不增加提议登记能力。

提议保持既有 `HealthNextDayProposal` 表和 `preview_id` 关联。其 Agent 来源沿 `preview_id → HealthMealPlanPreview.run_id → AgentRun.request_id/output_message_id` 核对，桥接响应附带已核对的 Run、Request 与消息引用；无需增加数据库表或迁移版本。既有手工预览登记入口继续保留。桥接使用不同来源指纹，阻止同一个用户动作幂等键换成相邻 Run、不同消息或普通手工登记。

## 替代方案

直接由客户端读取任务结果再调用普通登记入口最少改动，但两次请求之间无法证明登记动作与用户选中的完成消息一致。模型调用登记工具会把用户动作混入规划执行，并允许重试或工具误用产生写入。另建次日建议任务表会复制既有 Request、Run 和提议状态，并增加迁移、恢复与双事实维护。采用同事务的最小桥接，保留现有各状态 Owner。

## 后果

桥接与既有提议 Owner 共用事务，来源校验与提议写入在同一提交点生效。提议与正式餐单、采用、专业复核和饮食记录分别持久化；桥接仅产生 `HealthNextDayProposal`，Worker 工具仅产生预览。既有手工入口保持原指纹，Agent 登记增加来源指纹；同一幂等键换成相邻 Run、消息或手工登记返回冲突。

完成结果仍受当前成员授权、处理同意、配置版本和食品/菜谱来源约束，撤权或来源失效后历史提议无法通过桥接重放。活跃 Run 在取得 Run 锁前拒绝，完成 Run 的锁后复核依赖平台终态不回到执行状态的约束。数据库模型、迁移与 Agent 工具注册保持既有 Owner；家庭配餐、自动触发、外部专业规则与客户端接入分别维护后续验收范围。

## 验证

相关 unit 为 33 项，覆盖输入边界、当前 Request/Run/消息关联、模式拒绝和同事务登记。非完成 Run 的六种状态均断言不调用 Run 锁与最终消息查询；锁后 refresh 的状态变化仍拒绝登记。`ruff format --check` 与 `ruff check` 通过。

独立合成 Compose 槽位的真实 API、PostgreSQL 与 ARQ Worker 验收为 4 项通过：桥接 HTTP 2 项、Worker E2E 1 项、原手工次日提议回归 1 项。Worker E2E 消费真实 SSE，回读五个 Request 的 Run、最终 Message、preview 与用户登记后的唯一 proposal。模型协议通过本地确定性 replay 服务执行；真实外部模型与生产处理审批留在单独的外部联调范围。

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 真实 Worker 普通配餐完成后，用户明确选择明日回执可登记且幂等重放返回同一提议 | 工具成功但 Run、最终消息或业务落库错绑 | 桥接 service、提议 service 与现有 Request/Run/Message repositories | `test_health_next_day_proposal_e2e.py` 从真实 HTTP 发起，消费 SSE，回读 PG Run、Message、preview、proposal | 相邻 Request、Run、预览与最终消息互换均拒绝且无提议写入 | Passed |
| 跨 actor/member、非完成 Run、非明日结果不能登记 | 客户端仅靠 UI 隐藏、模型字段或相邻历史获得写入 | 健康任务 repository 与桥接 service | `test_health_next_day_proposal_http.py` 与 Worker E2E，并回读提议数量 | 外部账号、管理员、错误成员、failed/pending/cancelled/interrupted Run、questions、今天日期 | Passed |
| 非普通模式及锁后终态变化拒绝 | 普通入口误接家庭或改版结果，锁前判断代替锁后复核 | 桥接 service | `test_health_next_day_agent.py` unit | family/initial/safe selection、refresh 后状态变化 | Passed |
| 活跃 Run 不等待 Worker 的运行锁，拒绝后释放成员锁 | Member→Run 与 Worker Run→Member 形成锁循环 | 桥接 service 与 PostgreSQL | 真实 HTTP 在独立 session 持 Run `FOR UPDATE` 时 3 秒内返回 409，同 session 随后取得 Member `FOR UPDATE NOWAIT` | running 当前 Request/Run、0 proposal；删除早返会等待 Run 锁并超时 | Passed |
| 登记时授权、同意与预览来源变化拒绝写入 | 在 Run 完成后撤回来源仍使用历史答案 | 当前授权/同意与预览来源 Owner | 真实 PostgreSQL + HTTP，原手工次日提议回归 | 同意撤回、处理配置变化、消息或预览快照篡改、食品来源变化 | Passed |
| 登记没有正式保存、批准、采用或饮食副作用 | 将提议误报为正式业务结果 | 既有提议持久化 Owner | E2E 回读 HealthMealPlan、adoption、DietLog 无新增，提议 formal_plan_saved 为 false | 真实 Worker 只产生 preview，明确 HTTP 动作仅产生 proposal | Passed |
| 外部模型与档案、专业规则、商城和客户端联调 | 合成工程回放被误用为外部业务验收 | 对应外部接口与业务 Owner | 外部联调验收 | 家庭/自动建议、外部模型质量、正式采用与真实饮食闭环 | Not run |

实际链路命令在独立槽位执行，测试的环境与数据库保护由 fixture 拥有：

```bash
HEALTH_CONSULTATION_E2E_ISOLATED=true TEST_BASE_URL=http://localhost:5050 uv run --no-sync pytest test/integration/services/test_health_next_day_proposal_http.py test/e2e/test_health_next_day_proposal_e2e.py test/integration/services/test_health_plan_adoption_http.py::test_next_day_proposal_date_idempotency_sources_and_no_formal_plan -q -p no:cacheprovider
```

测试结束后，54 个带合成账号归属字段的持久化表均回读为零，合成 provider 与次日提议为零，7 个用途的模型、审批指纹及 policy 关闭，readiness 返回 200。既有全局配置行保留管理员审计标记，关闭值已复核；回放进程已停止，8774 端口关闭。

