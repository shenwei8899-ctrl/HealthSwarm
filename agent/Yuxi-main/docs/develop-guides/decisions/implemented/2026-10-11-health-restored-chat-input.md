# 恢复运行中的会话后继续输入

状态：implemented
类型：bug-fix
Owner：web/src/components/AgentChatComponent.vue

## 问题

重新打开已有活跃 Run 的后台会话时，AgentView 的路由初始化锁等待 selectChat 完整返回。selectChat 等待持续 Run SSE，导致成员、配置及历史已经读取完成后，输入仍保持禁用直到运行流结束。用户无法在原线程追加排队请求。Request 订阅原本已在有限状态同步后后台运行，保持该契约。

## 决策

### 实现方案

由既有聊天组件区分会话初始化与持续订阅生命周期：先确认选中的 Agent、线程、成员绑定、配置、初始历史与 Run/Request 的当前 PostgreSQL 状态，再让持续 Run SSE 在后台继续。恢复 Run 查询确认 activeRunId 等状态后才解除初始化锁，持续 startRunStream 不阻塞路由初始化完成。默认恢复调用仍等待流结束，选会话入口明确指定后台长流及当前选择校验。追加请求复用既有提交和服务端 FIFO。

聊天组件用初始化就绪线程及选择代次保护实际发送入口；AgentView 用路由代次保护当前初始化锁。线程、账号变化或组件销毁后，迟到的 Agent、历史、状态、附件、Run 与 Request 读取均不得发布；A→B→A 也视为不同选择。当前初始读取失败时拒绝原线程就绪，沿用 AgentView 返回新草稿的行为，健康角色仍须重新绑定成员。服务端确认新建线程且创建上下文仍匹配后才标记就绪，包含附件先创建线程的入口。

Run 流通过当前连接控制器、Run 状态和选择共同判定归属，防止旧连接的迟到帧、错误、结束状态查询或重连影响新选择。任务结束后的历史与状态 HTTP 刷新默认捕获调用时的选择，即使后续排队 Run 没有传入恢复选项也受保护。发送前捕获 Agent、模型、附件和健康角色，避免 nextTick 后切换到普通角色时使用普通标题模型处理原健康问题。

不修改后端执行状态、Schema、Worker、专业规则或正式小程序页面。不新增调度器或客户端持久任务状态。

## 替代方案

保持等待流结束会使长任务持续禁用输入。直接删除全部 send-disabled 条件会允许绑定尚未完成时发送。后台启动整个恢复查询会在 activeRunId 未确认时允许发送，导致输入逻辑误判当前运行。仅在 AgentView 提前清锁会使聊天组件其他选会话入口继续等待长流；当前方案在初始化与订阅的实际 Owner 收敛。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 活跃任务恢复时，初始化完成后可追加同线程请求 | 初始化持续等待 Run SSE 结束 | AgentChatComponent、AgentView | 实际组件方法装配及真实浏览器重新进入 running 会话后发送 | 恢复等待长流后，目标断言观察到 settled=false、disabled=true | Passed |
| 切换会话仍等待当前绑定，迟到初始化不污染新选择 | 旧历史、配置或恢复晚到 | 线程状态及现有选择入口 | 组件定向测试覆盖 A→B→A、账号变化、销毁、初始失败、新建及附件先创建 | 移除对应保护后命中当前配置、正文、就绪或发送上下文断言 | Passed |
| 旧连接和终态 HTTP 刷新不污染当前选择 | 同 Run 重订阅、后续排队 Run 默认调用的迟到结果 | Run consumer、聊天组件 HTTP 发布入口 | 实际 composable 与组件方法装配；独立延迟帧、错误及默认后续 Run 历史刷新探针 | 旧控制器帧或旧历史写入当前选择；移除捕获后正文变为 stale-terminal-a | Passed |
| 追加、取消复用既有 FIFO 与执行事实 | 重复执行或串 Request/Run | 既有提交、队列 consumer 与 PG | 隔离真实 API/Worker、浏览器及最终 PG/Task GET | 第三条排队请求取消；切换新草稿后回原线程 | Passed：前两条各一 Run、一 Attempt、一最终回答，按顺序完成；取消项无 Run/Attempt/最终 assistant Message |

定向组件与 composable 测试使用真实 Vue 响应状态和实际源码方法，HTTP/SSE 依赖受控；这类装配不是完整挂载浏览器。最终 helper 的 32 项测试通过，独立定向审查的四文件测试共 133 项通过，另对最终 helper 补充账号状态正负控。独立审查发现的旧控制器、健康角色标题绑定及后续 Run 终态刷新问题均已修复并验证。

```bash
cd web
node --test --test-concurrency=1 test/unit/restoredChatInput.test.js test/unit/conversationModelBinding.test.js test/unit/runStreamResume.test.js test/unit/agentRequestQueue.test.js
```

真实浏览器使用合成账号与本地回放模型 gate 保持真实 Worker Run 为 running；输入就绪后追加第二条并取消第三条，切换新草稿再返回原线程，释放 gate 后读回最终持久化结果。测试结束后按本轮所属 ID 清理 PG、checkpoint、Redis、工作区、登录审计及凭据；独立读回为零，主服务配置与模型提供方完整行保持原值，隔离配置保留审计更新时间变化。初次准备因追加修复停止，未作为浏览器通过证据。详细接线与复核步骤见[测试指南](../../testing-guidelines.md)。

## 后果

后台长流的错误继续由现有 Run consumer 处理。解除初始化锁的时间不能早于绑定和初始状态确认；切换时停止旧连接并丢弃迟到结果。正式小程序、真机、健康结果卡片、真实供应商质量与专业医学效果仍待对应 Owner 验收，本轮合成回放只验证工程链路。
