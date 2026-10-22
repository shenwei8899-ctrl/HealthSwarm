# 每日安排持久阶段的跨进程恢复验收

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/daily_arrangement_service.py

## 问题

每日安排已有持久任务与失联恢复，但 HTTP 去重和单进程测试不能证明实际 Worker 退出后能够沿用已完成的配餐结果，也不能证明恢复期间撤回授权会阻止发布。

实际故障注入发现，已有 `agent_result` 的恢复路径跳过了咨询用途同意复验，导致撤回 `meal_plan` 同意后仍可发布就绪安排。

## 决策

复用隔离健康拓扑和真实初始配餐回执，从已经保存 Agent 结果的每日安排阶段开始，使用实际 API、ARQ Worker 和 PostgreSQL 验证完成及恢复。模型与商城目录只使用本地合成协议。测试独占 Worker 进程，在菜单保存后、目录请求返回前杀死该进程，等待真实 lease 到期并启动新的 Worker；保持正式政策和生产环境不变。

每日服务在恢复入口和最终发布事务中，按原 Run 的身份、完成状态和冻结处理快照复用 `require_consultation`，重验全部参与者的当前授权、用途同意、配置和原选择。最终发布持有既有成员锁，与同意撤回使用同一锁边界；普通程序化保存餐单接口不增加 AI 用途前置。

### 实现方案

CI 的 `scripts/ci_health_agent_replay.sh` 在既有回放结束后停止该隔离槽位的常驻 Worker，再运行专用恢复测试。fixture 只启停自己持有的子进程，失败时先终止执行再清理所属数据。

## 替代方案

直接调用失败 hook 只能验证单次事务；修改数据库 lease 时间不能证明实际进程退出。采用真实进程终止，接受约一个租约周期的测试耗时。

只在恢复入口复验无法覆盖执行期间的撤回；因此最终发布事务也复验。未将校验加到所有普通餐单保存流程，以免改变非 AI 业务的授权契约。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 证据 | 负向案例 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| 页面离开仍完成保存，重复投递不重复生成 | 页面继续接口承担业务执行 | daily_arrangement_tasks | 独立 Worker、HTTP 与 PG 回读 | 同 Task 重复投递 | 通过 |
| 失联恢复沿用 Run、Plan 和业务版本 | 重复推理或重复菜单 | daily_arrangement_service | 杀死进程后新 Worker 消费 | 比对恢复前后 ID、版本和数量 | 通过 |
| 恢复时或发布前撤回同意拒绝发布 | 旧结果绕过当前用途同意 | daily_arrangement_service / require_consultation | 当前同意撤回后的 Task 和安排终态 | 已保存 Agent 回执仍不得发布 | 通过 |

2026-10-22 在全新隔离数据库 `health_consultation_e2e` 执行 `HEALTH_DAILY_RECOVERY_E2E=true python -m pytest test/e2e/test_daily_arrangement_recovery_e2e.py -q`：4 passed / 163.65s。断言包括成功任务和租约清理、失联任务失败并仅创建一次恢复任务、始终一个 AgentRun 和一个 Plan、三餐采购键各不相同、未确认采购时零 POST、异账号 404。修正前同意撤回用例实际失败（2 passed / 1 failed），修正后负控通过。

相关单元 `test_daily_arrangement.py`、`test_daily_completion.py`、`test_daily_recovery_authorization.py`：37 passed；新增负控覆盖缺失/他人/非配餐/未完成/错误请求 Run、缺处理快照、不同来源选择。实际运行日志保留于本地 `agent/.tmp/daily-recovery-20261022/`，未写入生产资料。

`test_daily_arrangement_http.py` 与 `test_daily_meal_purchase_http.py` 真实 HTTP/PG 回归：30 passed / 161.99s。全非 slow 单元首轮 4885 passed / 59 skipped / 2 failed / 6 errors，8 个异常均因合成拓扑的 `LANGFUSE_ENABLED=false` 与 Langfuse 单元夹具前提冲突；仅在测试命令中 `env -u LANGFUSE_ENABLED` 重跑该模块 10 passed / 1.14s，未改应用配置，不将首轮记录成全绿。工程契约检查、63 项检查器单元、Ruff/格式及 docs build 通过。独立 Reviewer 审核本次范围无阻断。同日重试补齐后，全非slow单元重新完整执行：4893 passed、59 skipped（165.25秒）。

## 后果

本阶段从已有配餐回执的持久检查点开始，不证明正式资料、真实模型、微信真机、实际采购或完整建档到三餐的生产链路。

本记录仅补充每日安排后台恢复子阶段；完整建档、来源优先级和客户端闭环仍按既有每日安排决策及 TODO 04.6 / 12.6 继续验收。既有就绪快照的长期保留与展示策略不在本次修改范围。

处理政策或模型快照已变化时，自动恢复明确拒绝沿用旧 Run。同日后续已补齐 [HTTP 显式重试与完整来源链路](2026-10-22-daily-retry-completion.md)：当前同意有效且明确重试时重建处理快照；内部未使用的 `resume_daily_arrangement(retry_failed=True)` 分支已删除。撤回后重新同意同一处理配置不等同于政策变更后的重新生成。
