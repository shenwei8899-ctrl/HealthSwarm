# 家庭营养 Agent 运维

面向维护健康业务接口和 Worker 的平台管理员。本文说明执行预算、业务错误追踪、识图用量统计和健康图回放的查找范围。运行状态、lease 和恢复机制由 [Agent 运行](../mechanisms/agent-runtime.md) 与 [测试规范](../develop-guides/testing-guidelines.md)解释。

## 排查入口不可用

平台 `GET /api/system/ready` 检查核心接流量条件。已授权成员的用途和存储、角色版本及业务目录缺项使用[成员业务就绪诊断](./health-member-capabilities.md#按业务依赖降级入口)；先读取具体入口原因，再恢复对应配置、Worker、存储或外部专业来源。诊断不调用云模型；恢复依赖后重新查询，并以实际业务操作结果为准。正式小程序须消费入口状态和允许动作，生产告警及外部模型质量另行验收。

## 启用成员营养咨询

管理员在“健康识图 → 服务与食品数据 → 健康服务配置”查看咨询启用指引。页面展示 `GET /api/health/v1/configuration` 返回的已保存咨询模型、处理政策版本及不可用原因；表单编辑或勾选审批不会改变该状态，保存成功后由父页面重新读取配置。服务配置可用后，成员授权和实际问答仍须各自验收。

| 当前原因 | 负责人与恢复操作 | 验收结果 |
|---|---|---|
| `policy_not_approved` | 服务负责人确认真实数据处理政策，管理员登记实际政策版本、明确审批并保存 | 重新读取配置取得政策版本；其他缺项继续按响应处理 |
| `model_unavailable` | 管理员配置并启用有凭据的兼容供应商，选择经过验证的固定咨询模型 | 咨询模型与处理方由服务端解析，配置返回当前可用状态 |
| `processor_approval_changed` | 服务负责人重新核对供应商端点及请求配置，管理员重新审批保存 | 成员重新给予相应用途同意；旧同意不能代替新处理方同意 |
| 配置可用 | 成员核对 AI 读取授权并确认咨询用途；开发者与业务负责人执行真实问答验收 | 同一 Run 的最终答复、实际引用及撤回授权后的访问结果符合预期 |

处理方标识由服务端依据所选模型供应商和请求配置生成，管理员无需另外手填处理方字段。政策版本与审批确认用于成员数据处理；固定家庭知识库的一般科普使用范围遵循[普通咨询固定知识库决定](../develop-guides/decisions/implemented/2026-10-14-health-consultation-reviewed-family-knowledge.md)。一般科普与正式个体化建议分别验收，逐篇专业资料审核不作为一般科普启用的附加条件。配置页不执行模型调用，也不替成员签署用途同意。

## 用客户端追踪标识定位错误

健康接口的受控业务错误返回 `code`、`trace_id`、`retryable`，并使用 `Cache-Control: no-store`。在 API 日志中查找同一 `trace_id` 对应的 `health_business_error` JSON。该记录包含 HTTP 方法、路由模板、状态码与稳定业务代码；路由模板保留 `{member_id}` 等占位符。

提供追踪标识和错误代码即可帮助管理员定位受控失败。请求正文、URL 查询、令牌、成员实际标识和异常原文不属于这条日志的内容。普通认证、协议验证与未知系统异常仍由各自 HTTP Owner 处理；不要把所有错误都假定为健康业务错误。

## 读取已报告识图用量

成员识图统计的 `provider_usage` 仅聚合当前有权读取、用途与时间窗口内、原始上传仍有效的任务。`reported_tokens` 为成功任务中供应商报告且通过类型与总数一致性校验的 token 总和；只有真实报告的零值才计为零。没有任何有效报告时，总计为空。

`reported_call_count` 表示有效报告调用数，`missing_call_count` 表示成功尝试中已记录但没有有效报告的调用数，`unknown_task_count` 表示缺回执、旧格式或失败任务数。`complete` 仅表示本统计范围的成功尝试模型调用都有有效回执；`billing_complete` 始终为 `false`。失败重试之前的调用、OCR 费用、供应商价格和账单对账不在该回执范围内。

该统计由成功任务终态提交中的安全回执提供，不需要读取识图原始对象或公开供应商响应。Agent 聊天的模型归属和网关计量另见 [按用户统计模型用量](./model-usage-tracking.md)。

## 设置健康任务执行预算

Worker 的 `YUXI_HEALTH_RUN_TIMEOUT_SECONDS` 默认值为 `300` 秒，适用于注册的固定健康角色。配置必须为正整数，且不得超过 `YUXI_JOB_TIMEOUT_SECONDS` 减去 `30` 秒；保留的时间用于关闭执行链、提交终态和清理。无效配置会阻止 Worker 启动。配置在进程启动时读取，修改后重启 Worker；正在运行的 Run 仍沿用其持久化首次执行时间，后续 attempt 按当前部署预算计算剩余时间。

首次开始执行之前的 FIFO 排队不消耗预算；同一 Run 首次开始后的准备、模型、工具以及重试等待均消耗预算。耗尽时返回不可重试的 `health_execution_timeout`，最终状态由 PostgreSQL Run 和 Request 记录提供。用户补充信息后的新 Run 使用自己的首次执行起点。模型 SDK 只使用剩余时间且关闭自动 HTTP 重试；人工重试仍须满足当前授权、来源和原 Run 剩余时间。

用户取消、失去 lease 和基础设施取消分别沿其既有流程处理。数据库不可用时，终态提交及清理由既有恢复机制处理；接收到超时错误后仍应查询同一 Request/Run 的最终状态。该预算约束执行时间，用量或费用上限须另行审批。边界与隔离复验见[执行预算决定](../develop-guides/decisions/implemented/2026-10-10-health-run-execution-budget.md)。

## 登记科普资料的审核范围

平台管理员使用 `POST /api/health/v1/nutrition-evidence` 登记专业审核后的资料版本。既有来源、审核人、审核凭据及带时区的审核和有效日期继续必填；可选的 `reviewed_scope` 对象登记以下使用条件。字段校验由[发布 DTO](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_evidence_types.py)拥有，许可真实性及专业内容由资料负责人和专业审核人确认。

| 字段 | 发布者填写内容 | 当前使用条件 |
|---|---|---|
| `domains` | 从 `nutrition`、`blood_glucose`、`blood_lipids`、`blood_pressure` 中选择一到四个不重复领域 | 分别对应普通咨询、血糖、血脂、血压角色；真实 Run 决定检索领域 |
| `population_category` | `general_education` 或 `professional_selection_required` | 当前教育流程只使用 `general_education` |
| `population_description` | 专业填写的适用人群说明 | 保存审核登记，不从说明文本推断个体适用性 |
| `exclusion_conditions` | 专业填写的排除条件列表，可为空 | 当前流程只使用空列表的资料；有排除条件时须等待专业匹配契约 |
| `license_ref` | 非空许可依据引用 | 保存专业许可记录，不自动验证许可真实性 |

来源的 `reviewed_scope` 和服务端生成的 `scope_hash` 随不可变版本保存，引用同时记录采用时的范围摘要。领域或适用条件调整须发布新版本，并按需要通过 `DELETE /api/health/v1/nutrition-evidence/{evidence_id}` 撤回旧版本。未登记范围的历史资料保留原普通咨询语义；三个指标角色要求明确的领域登记。

检索前先按当前角色及通用适用条件筛选，索引命中后重新锁读当前来源。引用、最终发布、当前结果、历史及 checkpoint 工具历史均复核角色、范围摘要和来源内容；范围变化或撤回、过期时拒绝复用旧正文。没有可用片段时返回 `insufficient_evidence`，角色仍可回顾已授权记录并追问。部署须先由 `storage-migrator` 将健康 Schema 升至 24，再启动 API 和 Worker；升级增加三个可空字段并保留历史记录。范围契约与验证见[审核范围决定](../develop-guides/decisions/implemented/2026-10-13-health-evidence-reviewed-scope.md)。

## 配置、重试与隔离回放

健康角色使用业务入口固定的成员、用途、版本、模型和工具。配置缺失、用途尚未审批、处理同意撤回或来源失效时，先处理响应中的业务原因。可重试错误也需要当前授权及来源仍有效；更换处理方或策略后须重新取得相应用途同意。各用途的配置与默认关闭状态由 `health_vision` 的[配置 Owner](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/config/options.py)拥有。

健康固定图的确定性回放通过真实 API、ARQ Worker、最终 Message 和 PG 结果验证装配；回放不能证明真实模型效果或专业规则正确。按[测试规范](../develop-guides/testing-guidelines.md)准备合成隔离槽位，然后在 API 容器运行 `uv run --no-sync --group test python test/support/health_agent_replay_gate.py`。门禁要求独立合成标记及固定测试数据库，拒绝占用中的回放端口，并要求实际执行的用例零跳过。

普通咨询及三个指标教育角色的普通 SSE、Run 进度、状态与历史只提供固定执行事实或当前有效的已发布结果。排障所需模型和工具候选仍保存在私有审计中：`GET /api/chat/thread/{thread_id}/audits` 需要超级管理员身份、会话归属及当前成员健康授权；普通会话所有者不能直接读取。不要用 `verbose=true`、checkpoint 或旧事件游标取得候选内容。首模型输出时间使用 Worker 内部有限标记记录，不能用普通进度时间代替。

Yuxi 的系统测试模板使用 `scripts/ci_health_agent_replay.sh` 建立专属 `health-agent-ci` Compose 项目；脚本拒绝接管已存在项目，只清理自身创建的容器与卷。HealthSwarm 保留的工作流位于 `agent/Yuxi-main/.github/workflows/`，GitHub 只发现仓库根 `.github/workflows/`；该模板在 HealthSwarm 根仓库的自动运行入口仍待维护者配置。本地门禁结果与远端运行状态分别验收。
