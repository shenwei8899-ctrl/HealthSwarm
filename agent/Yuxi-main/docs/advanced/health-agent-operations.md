# 家庭营养 Agent 运维

面向维护健康业务接口和 Worker 的平台管理员。本文说明执行预算、业务错误追踪、识图用量统计和健康图回放的查找范围。运行状态、lease 和恢复机制由 [Agent 运行](../mechanisms/agent-runtime.md) 与 [测试规范](../develop-guides/testing-guidelines.md)解释。

## 用客户端追踪标识定位错误

健康接口的受控业务错误返回 `code`、`trace_id`、`retryable`，并使用 `Cache-Control: no-store`。在 API 日志中查找同一 `trace_id` 对应的 `health_business_error` JSON。该记录包含 HTTP 方法、路由模板、状态码与稳定业务代码；路由模板保留 `{member_id}` 等占位符。

提供追踪标识和错误代码即可帮助管理员定位受控失败。请求正文、URL 查询、令牌、成员实际标识和异常原文不属于这条日志的内容。普通认证、协议验证与未知系统异常仍由各自 HTTP Owner 处理；不要把所有错误都假定为健康业务错误。

## 读取已报告识图用量

成员识图统计的 `provider_usage` 仅聚合当前有权读取、用途与时间窗口内、原始上传仍有效的任务。`reported_tokens` 为成功任务中供应商报告且通过类型与总数一致性校验的 token 总和；只有真实报告的零值才计为零。没有任何有效报告时，总计为空。

`reported_call_count` 表示有效报告调用数，`missing_call_count` 表示成功尝试中已记录但没有有效报告的调用数，`unknown_task_count` 表示缺回执、旧格式或失败任务数。`complete` 仅表示本统计范围的成功尝试模型调用都有有效回执；`billing_complete` 始终为 `false`。失败重试之前的调用、OCR 费用、供应商价格和账单对账不在该回执范围内。

该统计由成功任务终态提交中的安全回执提供，不需要读取识图原始对象或公开供应商响应。Agent 聊天的模型归属和网关计量另见 [按用户统计模型用量](./model-usage-tracking.md)。

## 设置健康任务执行预算

Worker 的 `YUXI_HEALTH_RUN_TIMEOUT_SECONDS` 默认值为 `300` 秒，仅适用于五个固定健康角色。配置必须为正整数，且不得超过 `YUXI_JOB_TIMEOUT_SECONDS` 减去 `30` 秒；保留的时间用于关闭执行链、提交终态和清理。无效配置会阻止 Worker 启动。配置在进程启动时读取，修改后重启 Worker；正在运行的 Run 仍沿用其持久化首次执行时间，后续 attempt 按当前部署预算计算剩余时间。

首次开始执行之前的 FIFO 排队不消耗预算；同一 Run 首次开始后的准备、模型、工具以及重试等待均消耗预算。耗尽时返回不可重试的 `health_execution_timeout`，最终状态由 PostgreSQL Run 和 Request 记录提供。用户补充信息后的新 Run 使用自己的首次执行起点。模型 SDK 只使用剩余时间且关闭自动 HTTP 重试；人工重试仍须满足当前授权、来源和原 Run 剩余时间。

用户取消、失去 lease 和基础设施取消分别沿其既有流程处理。数据库不可用时，终态提交及清理由既有恢复机制处理；接收到超时错误后仍应查询同一 Request/Run 的最终状态。该预算约束执行时间，用量或费用上限须另行审批。边界与隔离复验见[执行预算决定](../develop-guides/decisions/implemented/2026-10-10-health-run-execution-budget.md)。

## 配置、重试与隔离回放

健康角色使用业务入口固定的成员、用途、版本、模型和工具。配置缺失、用途尚未审批、处理同意撤回或来源失效时，先处理响应中的业务原因。可重试错误也需要当前授权及来源仍有效；更换处理方或策略后须重新取得相应用途同意。各用途的配置与默认关闭状态由 `health_vision` 的[配置 Owner](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/config/options.py)拥有。

健康固定图的确定性回放通过真实 API、ARQ Worker、最终 Message 和 PG 结果验证装配；回放不能证明真实模型效果或专业规则正确。按[测试规范](../develop-guides/testing-guidelines.md)准备合成隔离槽位，然后在 API 容器运行 `uv run --no-sync --group test python test/support/health_agent_replay_gate.py`。门禁要求独立合成标记及固定测试数据库，拒绝占用中的回放端口，并要求实际执行的用例零跳过。

Yuxi 的系统测试模板使用 `scripts/ci_health_agent_replay.sh` 建立专属 `health-agent-ci` Compose 项目；脚本拒绝接管已存在项目，只清理自身创建的容器与卷。HealthSwarm 保留的工作流位于 `agent/Yuxi-main/.github/workflows/`，GitHub 只发现仓库根 `.github/workflows/`；该模板在 HealthSwarm 根仓库的自动运行入口仍待维护者配置。本地门禁结果与远端运行状态分别验收。
