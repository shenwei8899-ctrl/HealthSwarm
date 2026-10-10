# 健康任务的重连与权威结果查询

状态：implemented
类型：feature
Owner：web/src/composables/useAgentRequestQueue.js

## 问题

健康任务的客户端需要在排队期间断线、运行期间断线和任务结束后重新进入时找到同一任务的当前状态与有效业务结果。Request 负责排队，Run 负责执行，健康 Task 查询负责当前授权下的业务结果；单个入口的成功不能证明三者的交接正确。流中结束事件、聊天正文和专业批准分别有自己的语义。

该决定面向客户端集成开发者，明确现有三个入口的组合协议，并关闭既有消费路径的断流和并行订阅缺口。正式小程序页面、真机、专业规则、商城、全新调度器和数据库演进由对应范围单独验收。

## 决策

### 实现方案

客户端保存当前账号、成员、线程对应的 `request_id`，并把已派发 `run_id` 和其 Redis 游标绑定到同一请求。重连先读取 `GET /api/health/v1/tasks/{request_id}`：仍排队则重新订阅 Request 当前 PostgreSQL 状态，已派发则订阅该 Run，已终止则读取健康业务投影。Request SSE 没有持久事件游标；Run SSE 使用 `Last-Event-ID` 或 `after_seq`，数据库补发的无 ID 结束通知不推进游标。

Task DTO、来源重验与结果分类由健康 service/repository 拥有；Request/Run SSE 由既有队列和运行 service 拥有，数据库及 Worker 流程保持原合同。健康 API 封装增加独立 `agentTask` 查询，图片识别 Task 沿用原 `task`。恢复合同和结果处理由[接入参考](../../../advanced/health-task-recovery.md)拥有。

Yuxi 聊天队列遇到 EOF 或暂时故障时读取同一 Request 的当前 PG 状态，再按有限退避重订阅；拒读、ID 错绑、停止和组件销毁结束恢复。订阅所有者使用写入响应式状态后读回的 canonical entry，保持 Vue Proxy 下的身份一致。取消或终止队列项保留另一活跃 Run。聊天页同时启动 Run 与队列恢复，Run 初始化保留 Request 流，旧 Run 查询的迟到响应按现有线程、Run 和 controller 身份拒绝回填。排队列表查询前后的线程和队列数组身份不一致时丢弃旧快照，防止已派发或终止的请求重新入队。同 Run 重复交接保留存活订阅，连接已停止则沿已消费游标恢复，避免从零追加已有正文。

不同活跃 Run 的交接先查询候选 Run 当前状态并核对 Request 和线程。旧终态候选不覆盖活跃 Run；查询期间已进入后续 Run 时拒绝迟到交接。前驱正常结束或同 Run 重连仍允许 pending/running 候选接管。候选读取暂时失败沿原 Request 有限重试，拒读或来源错绑结束该恢复。异步交接由 Request consumer 的局部 Promise 等待，通用 SSE parser 继续同步分发。

采用独立合成资源与模型回放验证真实执行边界，不使用生产健康资料或收费任务。实际模型质量、正式客户端和真机由其对应验收范围单独关闭。正式参考页拥有接入步骤与结果语义，测试规范拥有命令，决策仅保留取舍和证据。

## 替代方案

只说明三个独立接口会留下派发期间断线、旧游标混用和流结束后结果来源不明确的消费窗口。新增健康事件表、第二执行状态或全新恢复接口会复制现有 Request/Run/PostgreSQL 事实，需要额外迁移和双向同步；目前现有入口能表达恢复所需事实。直接显示流或最近聊天消息不能证明同一请求、当前来源和专业状态。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 排队断线后仍找到同 Request 派发的 Run | EOF 后不回读，或使用相邻 Run | Request service、既有 consumer | 真实 Worker E2E；实际页面强制 queued EOF、同 Request GET、重订阅和同 Run 回答 | 省略 PG 交接、错绑 ID、raw/Proxy 身份恢复均使目标断言变红 | Passed |
| Run 游标只属于同一 Run，无 ID 终态可查询权威结果 | 重复事件、混用游标、缺 Redis 结束事件后永久等待 | Run service、健康 Task service | 实际 SSE ID、Last-Event-ID 优先、重复无 ID end、PG Message 直接回读 | 回零产生重复帧；删除所属 Redis 流后仍查询当前 PG 结果 | Passed |
| 追问、失败、取消与专业状态分别表达 | 执行结束被误当作业务批准 | 健康 Task DTO 与业务结果 Owner | 新恢复 E2E 的取消，既有 meal_preview 参数及 Task HTTP 的追问/失败/拒读投影 | 空最终指针 409、错绑定 410、来源失效；专业批准由领域服务拥有 | Passed |
| 恢复不重复执行、不跨账号/成员公开结果 | 自动重提 POST、迟到响应回填、撤权后泄露 | Request 幂等、授权 repository、consumer | 三 Request/两 Run/各唯一 Attempt；前端停止、迟到查询和授权拒绝用例 | 跨账号/撤成员授权 404、撤用途同意 403；恢复另一 Run 清理与 timer 缺陷使回归变红 | Passed |

命令与 fixture 所有权见[测试规范](../../testing-guidelines.md#健康-agent-任务恢复验证)。前端目标集合 97 项通过；Vue 响应式装配的三个用例在 raw entry 变异下均按目标断言失败，交接、重试、timer、并发与迟到响应的内存变异按目标断言变红。真实 composable 与 stream handler 组合验证同 Run 重复交接、两 Request 迟到列表、跨 Run 候选查询及临时失败的有限恢复；前驱正常结束和同 Run 重连仍允许下一任务接管。后端新增真实恢复用例和复用的五项真实业务验证零跳过。浏览器通过独立合成账号、固定回放和本地一次性断流代理验证同任务恢复；主服务配置和供应商基线保持原值，所属 PG、Redis、临时凭据与 helper 完成精确清理后回读。

## 后果

Request 事件不是历史事件存储；重新订阅只观察当前状态，不能承诺补齐排队事件。Redis 运行事件有保存期限，数据库状态和健康 Task 业务投影用于查询兜底。接口内容、来源和授权可能在两次读取间变化，客户端需要按当前同任务事实重新展示。专业等待属于业务状态，不增加新的 Run 执行终态。

现有 `AgentView` 在路由初始化的长流等待期间禁止发送新输入，该交互限制保留。恢复验证通过预先存在的运行和排队任务重新进入页面，不宣告恢复期间新增输入、正式小程序健康结果卡片或真机验收完成。临时断流代理只转发 HTTP，开发 HMR WebSocket 的诊断不作为业务恢复失败；代理不进入正式部署。
