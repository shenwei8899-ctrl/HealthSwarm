# 健康错误追踪与识图供应商用量事实

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_vision_statistics.py

## 问题

健康业务错误需要通过同一追踪标识关联客户端与运维日志。识图调用的供应商用量需要区分实际报告的零用量、缺失用量与历史未知。健康固定图的装配需要可重复执行且核对实际 Worker 与 PostgreSQL 结果的发布门禁。

## 决策

### 实现方案

`HealthRoute` 在受控业务异常时生成一次追踪标识，同时写入响应和结构化日志。日志只保存方法、路由模板、HTTP 状态、稳定错误代码和追踪标识，不保存请求 URL、成员值、正文、凭据或异常原文。响应使用 `no-store`，现有错误代码和重试语义保持由业务 Owner 决定。

识图执行器从供应商返回的 `usage_metadata` 提取有界非负整数 input/output/total tokens。无报告或不一致的用量保留为空。成功 hook 与当前 Durable Task lease、草稿和终态共用提交点，安全用量回执保存在既有 Task result JSON，无需新表。统计 repository 在现有成员、用途、窗口和仍有效上传过滤之后读取该事实；统计只给已报告调用的已知总和、缺失调用及缺回执任务数，不把失败尝试、OCR 费用或缺失 token 当零，不估供应商计费金额。失败、取消及 lease 丢失不能发布成功回执，历史任务没有回执时明确未知。

`scripts/ci_health_agent_replay.sh` 复用 Compose 建立独立的 `health-agent-ci` 项目和新数据目录，要求已构建镜像，拒绝接管既有项目，只清理自身容器和卷。门禁串行验证固定图，复用合成账号、PG、ARQ 和已有回放服务，不使用真实云凭据。测试 CLI 以 root 写入挂载回执目录，API 与 Worker 保持服务 UID。Yuxi 子目录的系统测试模板调用该门禁；HealthSwarm 根仓库的自动 CI 入口待维护者配置。新增运维参考只解释追踪、未知用量及受控重试，运行与权限机制仍由既有 Owner 拥有。

## 替代方案

把原始响应放进日志扩大健康数据暴露。读取私有结果对象统计需要不必要的对象权限且无法与任务提交一致。新增用量账本表会把有限模型统计误称供应商完整账本。单元测试不能证明 Worker 的真实装配；另建测试基础设施增加当前没有必要的维护面。

## 后果

成功任务回执只覆盖该成功尝试里已返回或已发起的模型请求，重试前的失败尝试与 OCR 计费仍未知。供应商价格、账单对账、生产负载和告警策略由外部验收提供，不从 token 数推算。错误日志使用路由模板和稳定代码，业务 Owner 仍决定重试语义。

本地固定图门禁使用独立标记和真实数据库名作保护，拒绝占用中的回放端口，逐阶段要求非空用例与零跳过。远端 GitHub 自动入口和运行状态分别验收，本地门禁通过不能代替远端状态。查找方式由[运维参考](../../../advanced/health-agent-operations.md)拥有，命令由[测试规范](../../testing-guidelines.md)拥有。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 客户端标识可查同一安全日志 | HTTP/日志 | HealthRoute | 真实ASGI及HTTP错误响应、日志回读 | 私有值/查询/异常文本不进日志，重试语义不变 | Passed |
| 用量与成功终态同事务 | PG/lease | health vision executor/Task hook | 真实PG及MinIO执行器 | 撤权、删源、取消、过期lease无成功回执 | Passed |
| 已知、零值和未知分别报告 | 类型与聚合 | statistics service/repository | 手算unit、真实HTTP/PG | 缺失/非法/不一致/历史用量，成员用途窗口及删源 | Passed |
| 本地门禁装配确定性健康 Worker 路径 | 注册/HTTP/ARQ/PG | 隔离门禁、健康E2E | 全新专属Compose运行8阶段、10个实际用例，最终Message和回执回读 | 缺固定工具、非法结果、失效来源及活跃Run锁明确拒绝 | Passed |
| 根仓库远端自动CI入口 | 工作流发现和远端运行 | 仓库维护者 | 配置仓库根入口并检查远端运行 | 子目录模板不能被当作已启用入口 | Not run |

2026-10-10 实际运行：`test_health_route_trace.py`、`test_health_vision_usage.py` 与 `test_health_vision_statistics.py` 共36项unit通过；用量真实HTTP/PG1项通过。`test_health_vision_executor.py` 的30个真实PG/MinIO执行器变体分批验证：首轮25项通过后人工中断，后续选择6项通过，其中1项为重验，覆盖剩余5项。首轮命令不能报告为整次退出成功，30个不同变体均有实际通过证据。另7项重试与菜谱来源回归通过。

实际 Bash 门禁使用全新隔离数据目录，8个阶段的JUnit共10项、零失败、零错误、零跳过，命令退出0。咨询、配餐、分析、专业审核、采购、次日提议和目标绑定均验证实际Worker最终Message、业务回执及负控；最后两项HTTP/PG验证活跃Run快返409和零提议。结束后专属项目的容器和网络均已删除，原主服务ready200、健康配置摘要不变、采购生产用途保持关闭。真实供应商模型效果和生产费用未由该合成门禁验证。
