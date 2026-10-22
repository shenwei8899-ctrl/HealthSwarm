# 每日安排显式重试与完整来源链路

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/daily_arrangement_tasks.py

## 问题

每日恢复已拒绝过期处理快照，但真实 HTTP 重试保留旧 Agent 回执，处理模型或政策变化后无法生成当前结果。内部服务的 retry_failed 分支没有调用者，不能证明用户可以恢复。此外已有检查点恢复验收未覆盖建档到三餐的完整装配。

## 决策

在显式失败重试的事务 Owner 检查旧回执。当前全员同意及来源有效、仅原 Run 处理快照变化时清除旧生成检查点并递增分析 attempt；暂时服务失败仍复用原 Run。当前配置未审批、未同意或撤权继续拒绝。保留已发布快照及采购幂等事实，自动恢复不采用新政策。

通过隔离 API、实际 Worker、本地确定性协议及正式业务接口验证建档、三餐保存、单餐变更和显式重试。正式政策、真实供应商和订单不在本轮范围；服务器现状仅只读核对。

### 实现方案

`request_daily_resume` 在既有每日安排串行化事务内复用恢复授权校验。仅 `policy_changed` 允许清除旧回执和受影响餐次采购载荷；其他餐次已发布来源保持原键。重新生成后采购请求使用新餐单 ID、版本和分析 attempt。普通外部故障继续复用当前回执及采购键。事务提交后发布唯一 Task，Worker 沿既有生成分支执行；删除无调用者的内部重试参数与分支。

完整链路测试通过实际建档接口建立用户自述资料和 AI 用途同意，管理接口发布独立合成规则、配方映射，实际 Worker 调用本地模型协议并自动保存三餐。仅重试测试明确构造失败业务检查点，前置 Run 和菜单均由真实链路产生；进程失联与撤回注入另见 [恢复验收](2026-10-22-daily-worker-recovery.md)。

## 替代方案

所有重试清空回执会令库存或网络短暂失败重复推理。只调整未被调用的内部重试分支不能改变 HTTP 行为。选择在当前 HTTP 用例按旧处理快照失效原因决定重建。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 证据 | 负向案例 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| 明确同意新配置后可重建 | 重试无限使用旧 Run | request_daily_resume | HTTP/Worker/PG | 未同意403，并发重试只增加一次 attempt | 通过 |
| 暂时失败保留有效回执 | 重试重复生成或采购 | daily_arrangement_service | HTTP/Worker/PG | 同一配置保留原 Run 与采购键 | 通过 |
| 建档到三餐及改单餐可完成 | 局部测试掩盖装配错误 | miniapp_profile / daily services | 完整 HTTP/Worker 与 PG 回读 | 外账号404、其他餐保持 | 通过 |

2026-10-22：`HEALTH_DAILY_RECOVERY_E2E=true python -m pytest test/e2e/test_daily_arrangement_completion_e2e.py -v`，3 passed / 92.62s。固定单份100克/110千卡独立预期，验证默认两人三餐、仅午餐改人、原业务ID及版本、采购键和菜单版本引用、无用户购买时零POST。正式App相关既有单元60 passed。日志仅本地保留 `agent/.tmp/daily-completion-20261022/`。

补强最终 PG 餐单参加者和份量断言后，与恢复测试合并执行：7 passed / 229.23s（`e2e-final-2.log`）。首轮合并执行中的四项恢复测试因 root 测试 Worker 创建的私有工作目录导致绑定接口 500；仅修复隔离目录属主并改用 Compose 服务 UID 后通过，CI 同步使用服务 UID。全非 slow 后端单元 4893 passed、59 skipped；工程契约检查和63项检查器单元通过。正式政策保持暂停。

正式 App 浏览器读取已保存三餐、午餐调整后的1人/100克/110千卡详情及刷新后重进均可观察，打开和刷新没有生成 POST。浏览器整体验收未通过：冷启动重复 `reLaunch` 引发导航取消的未处理异常（`browser-reason.log`）。2026-10-22用户明确本次仅提交 `agent/`、不修改 `App/`；客户端负责人/刘潇后续修复入口与 onShow 导航协调，验收冷启动、深链刷新和切号无未处理异常且不重复生成。完整表单及采购交易仍待联合验收。

最终相关 HTTP/PG 回归 `python -m pytest test/integration/services/test_daily_arrangement_http.py test/integration/services/test_daily_meal_purchase_http.py -q`：30 passed / 133.45s。Ruff、格式、`git diff --check`、文档 `pnpm build` 通过；首次文档构建因本地内存不足失败，释放本轮测试资源后构建完成（27.73s）。独立 Reviewer 审查本次全部变更和失败边界后无阻断。已停止并移除本轮隔离拓扑，不改生产环境。

## 后果

沿用既有 Task 和 AgentRun 状态，不增加并行执行机制。正式数据、人群规则、域名与微信真机仍需要对应负责人交付，不从合成通过推断生产开放。
