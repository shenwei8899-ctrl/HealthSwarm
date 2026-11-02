# 参考餐单原文引句失败的一次修正

状态：proposed
类型：bug-fix
Owner：backend/package/yuxi/agents/toolkits/meal_planner.py

## 问题

参考配餐的保存调用因 `reference_quote_invalid` 在预览持久化前被拒绝。精确运行的受控核验显示必填菜名、食材和步骤逐字匹配，六份可选份量引句未逐字匹配；该结果不能解释为翻译、估算或某种字符差异。业务校验需要保持严格，模型需要一次读取真实失败反馈并修正可选引句的机会。

## 提案

### 实现方案

专用保存工具仍每次只调用一次原保存服务。当前参考请求的首次原文引句错误返回同工具名称及 call ID 的失败 ToolMessage，保存原错误代码和公开消息。模型调用身份必须来自当前带 `health_request_id` 的 Human 消息之后实际声明的保存操作。其他错误及再次引句失败继续抛出，原保存服务的档案、授权、原文、采购及持久化边界不变。

配餐 graph 在下一普通模型节点指定一个保存调用；纠错回复必须恰好包含一个有效保存操作，夹带无效调用或其他回复在执行器前明确拒绝。当前请求已有一次修正模型回复后仍未获得成功保存回执时，继续模型调用被拒绝。次数从当前请求的模型及工具消息推导，不使用进程布尔、配置项或独立状态表。

每次准备调用均提示 `portion_quote`、`nutrition_quote` 只能逐字引用已读原文，无对应说明时用 null 或省略；不得估算、拼接、翻译或用个人食用份量冒充原文。必填菜名、食材、步骤保持原样校验，程序不填写或规范化模型引句。

工具内部返回错误 ToolMessage 经真实 `tool-finished` 生命周期进入现有 Collector 的失败分支，首个审计关闭为 failed，不能作为保存成功回执。下一模型节点继续经过既有授权、执行预算和 TokenUsage；每节点只调用一次 handler，图执行步数上限保持不变。

## 替代方案

放宽原文匹配会改变来源证据，未采用。直接丢弃可选引句会隐去模型提交错误，也未采用。graph 外层捕获工具异常会先产生裸 tool-error，其审计须等终态对账；专用工具内处理使失败审计的关闭路径更直接。同一模型节点内重发会覆盖用量累计，未采用。

## 验收标准

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 局部回放保留首个引句失败身份 | 假成功或错误被吞掉 | 专用工具、ToolMessageAuditCollector | 实际 SDK/v3、ToolRuntime、Collector 算法的源码 AST 组装回放，Repository 为合成依赖 | 其他错误、旧请求、错误 call ID 不恢复 | Passed |
| 局部图的下一节点只允许一次保存修正 | inline 重试、并行调用或重复修正 | 配餐 middleware | 同一新增测试加载 Git HEAD 旧保存函数恢复首个引句错误；当前实现失败、修正、最终模型三次调用累计 15 tokens | 重复错误、多工具、夹带无效调用、其他工具、撤权时停止 | Passed |
| 可选份量修正不削弱逐字校验 | 静默删掉必填或程序改写原文 | checked_reference_meals | 实际逐字校验拒绝错误 portion_quote；仅改为 null 后通过，必填引用保持相同 | 既有必填原文、权限及来源校验保持原实现 | Passed |
| 真实 PG 首失败即时关闭且没有预览 | 审计悬置或失败被当成功 | ToolMessageAuditRepository、保存服务 | 新增 HTTP/PG fixture 加真实 ToolNode/v3 的 integration | 首个 failed 不进入成功回执，修正后仅一个成功保存 | Not run |
| 完整 Linux 装配及真实配餐可用 | 局部回放未覆盖生产路径 | 项目 unit、Worker 与客户端 | Linux unit、PG integration、独立审查和真实 UI 配餐 | 权限、来源、预算及运行终态 | Not run |

局部回放执行了既有测试文件中的 12 个 SDK/v3 场景和 10 个身份、模式及错误码边界；真实 HealthAuthorization、默认 TokenUsage、两类 Collector 算法及逐字校验保留，权限存储、来源读取、最终结果和审计 Repository 使用显式合成依赖。该证据不覆盖完整项目装配、Steer、真实数据库或外部模型。

常规 pytest 在本地 Windows 的 POSIX 文件系统模块导入处受 `os.O_DIRECTORY` 限制，实际零项收集、两项导入错误。新增真实 PG 测试限定观察两次显式 ToolNode/v3 操作之间的失败审计落库、首次失败无预览及 null 修正后的唯一成功回执，不声称证明完整 worker 或下一 SDK 调用前的落库时序。

首次隔离 Linux 验证为 5423 项 unit 通过；57 项真实 PostgreSQL integration 中 53 项通过、此审计测试失败、三项语音测试在 fixture 初始化时报错。局部真实 SDK 对照实验确认裸 StateGraph 必须在编译时装配 `ToolCallTransformer`，才能产生 Collector 消费的工具生命周期事件；仅在流读取时启用 `CustomTransformer` 不会产生这些事件。该实验明确使用合成数据库依赖，不能恢复旧 PostgreSQL 失败行或替代真实持久化验证。语音 HTTP fixture 使用 asyncpg 支持的 `server_settings.search_path` 设置隔离 schema。完整新快照、真实 PostgreSQL、独立审查、发布和两轮用户配餐仍需分别验证。

补齐 transformer、语音 fixture 与所有模型的一次修正预算守卫后，源码摘要 `3a1c697c45c2` 的完整 Linux 验证实际为 5424 项通过；57 项 PostgreSQL integration 全部收集和执行，56 项通过，仅 `test_reference_quote_failure_audit_then_null_correction` 在 call 阶段失败。其语音用例均通过，PostgreSQL 和 Redis 正常关闭、进程退出及容器消失的独立回执均完成。该轮没有发布，线上 API、Worker 身份和健康状态保持原样。

现有失败回执仅包含阶段与分类，未保存异常类型或源码位置，不能据此断定剩余失败原因。下一诊断快照仅补充白名单异常类别及已归档源码路径、行号，禁止输出异常消息、局部变量、数据库内容或凭据；仍完整执行原 unit 与 57 项 integration，保留失败记录及正常清理检查。该诊断准备不代表此测试通过，也不代表真实用户配餐或发布完成。

诊断快照 `ea05e7b614d7` 的完整 Linux 5424 项通过，但其打包输入误将历史 PostgreSQL、Redis 回执作为同名证据附件，和运行期的独占写入路径冲突，集成阶段因此以 `FileExistsError` 停止。附件中的旧结果及旧清理状态均不代表该轮结果。后续验证包将历史附件统一放入独立文件名前缀，并在冻结、执行前检查附件名与全部运行期输出名互斥；原失败包保持不变。该打包修复仍不证明剩余业务审计用例已通过。

## 风险

命名调用不保证外部模型正确理解修正，因此执行前还需要调用数量和名称校验。错误反馈不代表新来源或专业通过。checkpoint 重放继续遵循既有 at-least-once 语义，一次修正指一个逻辑操作，不新增跨崩溃的绝对物理执行保证。
