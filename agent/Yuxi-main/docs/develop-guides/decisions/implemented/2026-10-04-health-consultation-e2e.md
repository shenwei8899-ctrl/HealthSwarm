# 健康咨询确定性端到端验收

状态：implemented
类型：testing
Owner：backend/test/e2e/test_health_consultation_e2e.py

## 问题

成员绑定、工具读取和 PostgreSQL checkpoint 的局部验证没有覆盖独立 API、ARQ worker、FIFO 派发、SSE 与最终输出的完整因果链。本文面向开发者与 Reviewer，目标是在无真实模型费用和无患者样本的条件下验证这条真实装配链路，不声明正式供应商准确率或医学方案已经验收。

## 决策

复用 shipping Compose 的独立 API、worker、PostgreSQL、Redis、MinIO 和 provisioner，为健康咨询建立专用测试槽位、数据目录和本地端口。只在隔离槽位通过正式管理 API 配置固定本地模型及合成用途审批；生产代码不接受测试后门，现有开发数据和云配置保持不变。测试网络禁止外部连接，重放服务仅接受合成请求标记、固定模型与两项受控工具。

首轮模型请求在本地重放服务等待显式释放，让测试直接观察第二个请求处于 FIFO 队列。释放后由真实 ARQ worker 完成工具、模型续答、checkpoint、输出绑定与后续派发。HTTP、SSE、PostgreSQL Request / Run / Attempt / Message / manifest 与重放端实际收到的必要记录相互核对，清理严格限于本次随机测试账号及 thread。

## 替代方案

进程内 patch worker 或模型加载无法证明跨进程投递与配置一致性，仍属于 integration。临时开启现有开发槽位会改动未经批准的云处理配置，并可能与其他用户请求竞争。独立本地重放槽位保留发布链路和状态 Owner，把替身限定在外部模型协议边界。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 请求经提交、ARQ、独立 worker 完成 | 用 helper 或 mock 绕过真实发布 | request service / worker / PG | 正式 HTTP、SSE、Run / Attempt / manifest 回读 | 缺少绑定或用途同意时零 Message / Request / Run、模型调用为空 | 通过 |
| 同成员会话串行派发且结果不串请求 | 第二请求提前开始或取相邻结果 | request queue / output binding | 模型显式等待、PG 排队行、两个独立输出 | 重放幂等键保持同一个 Run | 通过；撤权后的真实排队执行仍为 Not run |
| 只发送必要已确认记录 | 未确认草稿或额外工具外发 | health backend / local replay | 外部协议收到的 tools 与 ToolMessage、checkpoint 回读 | 非合成输入、错误模型、额外工具、私有证据字段、错误记录 | 通过 |
| 隔离测试不改原开发环境 | 共用数据、凭据、端口或外发云 | Compose slot / test fixture | 实际 PG、独立容器 / 挂载 / internal 网络、原环境 HTTP 回归 | 普通槽位在 fixture 前 skip；测试槽位还必须满足实际数据库与空审批前置条件 | 通过 |

实际命令由[测试规范](../../testing-guidelines.md#健康咨询隔离合成-e2e)维护。独立槽位执行 `pytest test/e2e/test_health_consultation_e2e.py test/unit/services/test_health_consultation_replay.py -q --tb=short --show-capture=no -o cache_dir=/tmp/health-consultation-e2e-guards`，23 项通过，15.42 秒；其中一项真实 API / worker E2E 包含两个正向请求与两个拒绝请求，22 项为外部协议 oracle 的负向及正向单元。原开发槽位执行 `pytest test/unit/services/test_health_consultation.py test/unit/services/test_feedback_service.py test/unit/services/test_health_consultation_replay.py test/integration/services/test_health_vision_http.py -q --tb=short --show-capture=no -o cache_dir=/tmp/health-consultation-regression-final`，41 项通过，41.94 秒，此命令在补充三项控制路由单元前执行。两个命令均使用 `timeout -k 5s 150s uv run --no-sync --group test` 包装。观察到已有 psycopg async pool 构造弃用警告，未影响结果。

独立 Reviewer 实际复测 19 项 oracle 单元及三项控制路由单元，审查真实槽位和失败清理后无遗留 P1/P2。测试失败时所有已尝试提交的 request_id 都进入收敛清理；重放释放失败仍取消 SSE、请求取消并回读 worker 终态，然后才允许 fixture 删除所属业务行。普通槽位执行该 E2E，1 项明确跳过，9.74 秒；原环境服务回读 `report`、`meal` 和 `consultation` 均不可用。工程契约检查与其 62 项脚本单元、相关 Ruff、文档构建和补丁空白检查通过。

## 后果

固定合成重放验证请求协议与状态链路，不能代替真实供应商、脱敏医疗样本、知识库、专业规则和模型质量校准。槽位停止后保留独立数据目录，不删除用户已有卷或目录；所有测试配置均为明确的合成占位值。外部服务与预算未获批准时，正式云验收继续为 Not run。
