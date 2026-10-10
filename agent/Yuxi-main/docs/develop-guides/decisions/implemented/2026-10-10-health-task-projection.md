# 健康任务入口与权威结果投影

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_task_service.py

首版范围为四角色及其现有配餐模式；已实现的采购与可选个人目标扩展见[独立决定](2026-10-10-health-task-purchase-target-entry.md)。

## 问题

客户端读取家庭营养 Agent 的结果时需要拼接普通 Request、Run 和字符串 Message。执行完成与业务需要补充信息没有统一的健康协议；直接把任意 Run 输出标为经过营养校验会混淆科普答复、程序结果和专业批准。

## 决策

### 实现方案

增加严格的任务类型入口与只读查询，复用现有健康角色创建服务及 PostgreSQL Request、Run、最终 Message。入口只创建固定角色和成员的线程，使用 `entry_status` 表示就绪或缺少选择；客户端明确提交现有 `POST /api/agent/runs` 后才产生任务。初始配餐、家庭改版、单成员安全改版和质量检查缺少明确选择时返回 `needs_input`，不写入项目、线程、Request 或 Run。入口幂等键命名为 `client_request_id`，响应不声称它是已创建任务。

任务查询使用已存在的 `request_id`，分别返回 Request 状态、Run 执行状态和业务结果类型。只读取 Request 绑定的 Run 及显式 `output_message_id` 对应的完成正文，重验账号、线程、成员授权、当前来源和结果收据。结构化配餐、分析、质量结果通过各自当前业务 Owner 复核后返回；咨询返回科普正文及实际采用的有效引用，保持 `general_education` 范围。`needs_input` 可以来自已完成 Run；质量检查保持独立的专业复核状态。等待、失败、取消和中断不返回部分结果、工具审计或模型错误正文。

使用既有 Request/Run SSE URL 和事件游标，查询作为断流后的事实兜底。不新增表、状态机、事件流、调度模型或通用子 Agent。控糖、21天计划和自动多角色协调返回 `dependency_not_ready`。采购入口复用独立用途和来源契约，具体范围见扩展决定。

## 替代方案

- 直接返回普通 Run 字符串：无法表达业务语义或证明当前来源，拒绝。
- 入口创建线程并立即提交 Request：现有线程创建服务拥有独立事务，提交失败会留下半交付状态；保留客户端明确提交的现有操作。
- 建立健康 Task 表及专属 SSE：复制当前执行 Owner、游标和恢复机制，增加平行状态，拒绝。
- 通用模型自行决定任务类型及成员：会扩大数据和用途范围；使用用户明确类型和现有严格选择。

## 后果

客户端需要一次线程创建和一次显式消息提交。新查询严格要求权威最终指针，缺少指针的旧 Run 不做猜测性兼容读取。已撤回或变化的来源使读取失败，不继续返回历史健康正文。业务快照结构继续由对应结果服务拥有，新协议用明确结果分类包装通过复核的 JSON 结果，不复制营养数据结构。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 每种任务类型固定映射，缺选择不持久化 | 假任务、模式混入或跨成员 | task types/service、现有创建服务 | test_health_task_projection.py、test_health_task_http.py | 缺选择、额外身份字段、错模式、跨成员计划 | Passed |
| 查询只认同 Request/Run 的权威完成正文 | 相邻 Run、审计、缺指针被当最终结果 | task repository、AgentRunOutputRepository | 专属unit、HTTP/PG与test_health_task_e2e.py | pointer错Run、pending/failed审计和旧源 | Passed |
| 执行状态与 needs_input 分离 | 追问被当执行中断或正式结果 | task response DTO、业务 validator | 隔离实际Worker执行 | completed追问、伪造批准/数值、撤权/失效引用 | Passed |
| 结果经过当前业务来源验证 | 健康200或字符串被当验收 | 现有分析/配餐/质量/引用服务 | 隔离HTTP→Worker→PG及负控 | 同Run复核、来源变更、授权撤回 | Passed |

2026-10-10实际命令在`health-diet-analysis-e2e-api-1`运行，使用`uv run --no-sync --group test pytest`；unit32项49.12秒、HTTP3项19.26秒、Worker8项110.27秒。后两项固定`cache_dir=/app/test/.tmp/health-task-projection/pytest-cache`，Worker显式使用`-m e2e`，没有skip。实际Request、Run、最终Message与Worker attempt核对后沿既有清理Owner收敛；只读回查合成账号命名空间的用户、项目、线程、Request、Run、成员、业务预览、菜谱及引用均为0，本次12个准确thread ID及隔离库Message也为0。6个本次启动的既有本地回放进程按准确PID结束，不变更主服务审批。

扩展装配的真实复验包含首版全部模式及新增采购、个人目标。HTTP4项通过；Worker首轮10项通过，目标负控按真实规则字段更正测试后定向1项通过，合计11个唯一Worker案例，无skip。每case通过既有清理Owner清理准确账号和关联ID后，回查24张表均为0；共16轮、15个唯一HTTP/Worker案例。最终50张健康表及Request、Run、Message、attempt、运行租约和待清理状态均为0。健康运行配置与24个provider完整行hash恢复到验收前值；7个准确PID的自有回放进程已停止，含fixture采购端口在内的8个端口关闭，API ready200、Worker healthy。扩展证据与结果范围见[独立决定](2026-10-10-health-task-purchase-target-entry.md)。

正式页面、生产专业资料、真实供应商效果和新用途审批属于外部依赖，留待定。
