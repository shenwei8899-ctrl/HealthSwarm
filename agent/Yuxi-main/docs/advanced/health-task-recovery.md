# 恢复家庭营养师任务

供接入家庭营养师任务的客户端开发者查阅。登录后的当前账号使用同一 `request_id` 读取任务状态、恢复进度并取得当前有效的业务结果。任务入口就绪、Request 排队、Run 执行、业务校验和专业批准分别表达；正式小程序的页面与真机验收由客户端负责人完成。

## 选择恢复入口

重连先调用 `GET /api/health/v1/tasks/{request_id}`。响应中的成员、线程及 Run 必须属于客户端当前选择，随后按当前状态选择连接：

| 当前事实 | 客户端动作 |
|---|---|
| `request_status=queued`、尚未派发 Run | 订阅响应的 `request_events_url`，读取当前排队位置与派发状态 |
| 同请求的 Run 仍在执行 | 订阅响应的 `run_events_url`，使用该 Run 的已消费游标 |
| Request 或 Run 已终止 | 使用同一健康 Task 查询返回的结果分类，停止等待过程正文 |

Request 事件流没有持久事件 ID。重新订阅直接读取 PostgreSQL 当前状态：仍排队时收到 `queued` 与 `position`；已派发时收到 `run_created` 与确切 `request_id`、`run_id`；已取消、拒绝或失败时收到对应终态。派发后客户端核对同一请求，切换到该 Run 的事件流。

Run 事件流使用 `?verbose=false` 返回精简载荷。收到 `end`、`error` 或连接结束后，再查询健康 Task；流结束只表示需要查询当前事实，流正文不代替当前授权及来源校验后的健康业务结果。暂时无法读取时显示恢复失败并保留手动重试入口，采用有限退避，避免持续快速重连。

普通咨询、血糖、血脂、血压四个教育角色在执行中只公开固定运行与校验进度。它们的 `verbose=true` 与 `verbose=false` 使用相同的最小公开载荷；模型正文、推理、工具输入输出、自由错误、模型填充状态和供应商自由文本不进入普通流。旧 Redis 事件从已消费游标或 `0-0` 回放也受当前读取白名单约束。执行状态中的模型候选不能用于补正文。

## 绑定请求与游标

任务入口的 `client_request_id` 用于业务入口幂等；创建线程不表示已执行。客户端显式提交 `POST /api/agent/runs` 后保存服务端返回的 `request_id`，查询及恢复都使用该 ID。输入重试沿用同一次提交的幂等键；恢复连接只读取状态，不重新提交执行。线程中相邻任务各自保留 Request 和 Run 关联，不能用最近一条消息或线程当前活跃 Run 替换原任务。

Run 游标来自已接收 Redis 事件的真实 `id`，只与该 `run_id` 绑定。重连可发送 `Last-Event-ID` 或 `after_seq`；同时提供时以请求头为准。数据库根据终态补发的 `end` 没有 ID，收到后保持已有游标并查询结果。事件保存期已过时不能承诺补齐全部过程，最终状态与有效结果从 PostgreSQL 查询。

```http
GET /api/agent/runs/{run_id}/events?verbose=false
Last-Event-ID: <last-consumed-redis-id>

GET /api/health/v1/tasks/{request_id}
```

客户端先由 Task 查询核对 Request、Run、成员与线程，再核对事件中的 `run_id` 和 `thread_id`。通用角色的精简 `metadata` 帧不含 `request_id`；上述四个教育角色的最小公开帧保留请求与线程标识。载荷带该字段时核对相等，结束帧核对同一请求。重复接收已有 Redis ID 时不重复追加内容，无 ID 的数据库结束通知按终态处理。切换账号、成员或任务时取消旧连接，隔离迟到读取，并清除旧健康内容。

## 展示当前结果

`request_status` 描述排队请求，`execution_status` 描述 Run；具体字段和结果分类由 [Task DTO](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_task_types.py) 定义。`final_message_id` 只指向同一已完成 Run 的权威消息，服务端在每次查询时复核授权、处理审批和当前业务来源。

四个教育角色先执行来源、引用和当前授权校验，再在同一业务事务提交权威 Message、输出指针与 Run 完成状态。客户端收到终态后回读当前结果或历史，一次展示有效正文；提交未完成、失败、取消或中断时不补出积累候选。已完成后来源撤回或权限变化，结果与历史读取仍重新校验，旧游标和旧完成通知不能恢复失效正文。这一机制验证技术发布条件；专业正确性和真实模型质量须通过各自验收。

知识引用同时核对真实角色及登记范围。资料范围变化时，当前结果与专用引用接口拒绝失效正文；普通历史、state 与 search 过滤该答复。校验器以 `source_invalidated` 表示范围失效，以 `citation_invalid` 表示跨角色引用；checkpoint 在 Worker 模型执行前完成校验。未登记范围的历史资料只供原普通咨询使用，三个指标角色的旧结果若采用这类资料须重新咨询。提交接口接受 Request 后仍可能执行失败，客户端继续以同 Request 的实际终态和当前结果为准。资料发布契约见[审核范围登记](./health-agent-operations.md#登记科普资料的审核范围)。

| 查询结果 | 展示与后续动作 |
|---|---|
| 尚未完成、`result=null` | 显示当前执行状态，继续恢复进度或按有限频率查询 |
| 已完成、`result_type=needs_input` | 显示具体补充问题，等待用户明确回答；这是已完成 Run 的业务追问 |
| `execution_status=interrupted` | 显示执行中断，按既有恢复入口处理；不等同于业务追问 |
| `result_type=error` | 显示固定失败、取消、拒绝或中断分类；`retryable=false` 不触发自动重提任务 |
| 其他有效结果分类 | 展示当前授权下的结果；餐单预览、保存、专业复核和正式采用分别执行 |

专业等待由业务结果或业务查询中的专业状态表达。客户端不能增加一个 Run 终态代替专业等待，也不能把程序复算通过、执行 `completed` 或预览保存显示成专业批准。取消排队请求只影响该 Request；同线程中另一 Run 的进度与结果仍按其自身事实展示。

## 处理拒读与断流

SSE 已建连后的错误可以通过 `event:error` 返回，也可以使连接直接结束，HTTP `200` 不表示任务或恢复成功。客户端查询同一健康 Task 后决定下一步，不展示上游错误正文，不从缓存健康回答补结果。

| 查询边界 | 客户端处理 |
|---|---|
| `401` | 结束旧连接，清除健康内容，重新登录后重新核对任务 |
| `403` 或 `404` | 停止自动恢复并清除私有投影；核对当前账号、成员与用途授权，不据此推断他人资源存在 |
| `409` | 当前审批、来源或权威输出条件不满足；隐藏旧结果，提示核对当前条件 |
| `410` | 绑定或采用来源已失效；清除旧结果，等待用户选择当前来源 |
| 临时网络或服务故障 | 有限退避后查询同一任务；持续失败显示错误，允许用户手动重试 |

授权和用途同意在服务端读取边界重新检查。客户端保存的旧正文、游标和家庭管理员身份都不能绕过当前授权。撤权后 Request 流可能直接断开，Run 流可能返回错误；最终是否可读取以当前健康 Task 查询为准。

## 复用现有客户端装配

Yuxi 的聊天页同时恢复活跃 Run 和排队 Request。队列流遇到 EOF 或暂时故障时，先通过既有 Request GET 查询当前 PostgreSQL 状态，再重新订阅同一 Request；连续失败按 500 毫秒起步、上限 5 秒的退避重连，最多重连五次，收到有效排队帧后清除连续失败次数。拒读、错绑 ID、切换线程或组件销毁时停止该恢复。取消或拒绝一个排队请求保持另一活跃 Run 的进度。

重新打开运行中的会话时，先读取当前线程的 Agent、配置、历史、状态、附件以及活跃 Run 和排队 Request，再解除输入锁；持续 Run SSE 在后台继续，不等待执行完成。用户可以在同一线程追加排队问题，沿用服务端 FIFO。初始化读取失败时拒绝当前线程就绪，由页面既有恢复入口处理；AgentView 返回新对话草稿，健康角色仍须重新完成成员绑定。切换线程、账号或销毁组件后，旧读取不得解除当前选择的锁或覆盖其内容；任务结束后的历史与状态刷新也受此约束，包含后续排队请求派发的 Run。新增线程在服务端创建成功且创建上下文仍匹配后即可发送，附件先创建线程也使用同一入口。

Run 恢复期间保留同线程的 Request 订阅；迟到的旧 Run 查询不得覆盖新任务。队列、运行及线程状态分别由现有 [Request consumer](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/web/src/composables/useAgentRequestQueue.js)、[Run consumer](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/web/src/composables/useAgentRunStream.js) 和线程 composable 拥有。健康接口封装的 `healthVisionApi.agentTask(requestId)` 查询本页健康 Agent Task；`healthVisionApi.task(taskId)` 继续查询图片识别 Task。

读取排队列表期间，若同一队列已被派发、终止、取消或另一同步替换，丢弃迟到快照，避免复活旧请求并切回已结束的 Run。同 Run 重复交接保持已有存活连接；连接已停止时沿该 Run 的已消费游标恢复，避免从零追加已有过程正文。

派发候选与当前活跃 Run 不同时，先查询候选 Run 的当前 PG 状态与 Request、线程绑定。已结束的旧候选只结束自身 Request 订阅，保持当前 Run；读取期间若已进入后续 Run，忽略迟到交接。前驱 Run 正常结束或沿同 Run 游标重连时，仍允许当前 pending/running 候选接管。候选读取暂时失败沿同 Request 有限重试；拒读或来源错绑则结束该 Request 恢复，不把读取失败写成后台执行失败。

正式客户端使用本页协议结合健康业务结果卡片完成展示与真机验收。现有聊天页验证通用队列和 Run 的恢复装配；健康结果的采用、专业等待及业务失效展示仍由正式客户端交接。验证层级和命令见[测试规范](../develop-guides/testing-guidelines.md#健康-agent-任务恢复验证)。
