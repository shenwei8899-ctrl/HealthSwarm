# worker 的轻量健康探针

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/worker_health_service.py

## 问题

worker 的 Docker 健康检查通过 ARQ CLI 导入完整执行设置，冷进程同时加载模型、工具与业务服务。实际成功检查需要 20.65 秒，超过 Compose 的 10 秒限制，开发容器持续显示 unhealthy；同一实例的 API readiness 与三项短期租约均有效。读者为运行链路维护者，需要在原有预算内判断当前执行能力。

## 决策

轻量健康服务拥有三项 key、周期、TTL 上限与校验。现有 ARQ 消费、AgentRun 收敛和 Durable Task 收敛生产者继续在完成启动和实际工作成功后续租，队列模块保留现有常量导出；API readiness 与独立 `server.worker_health` 入口共同检查非空值及有限正 TTL。独立入口只加载轻量 Redis 配置和健康服务，不装配执行器、Agent、模型或 PostgreSQL 业务层。

开发和生产 Compose 使用独立入口，外部超时保持 10 秒，Redis 操作预算为 2 秒。成功静默并返回 0；缺失或无效租约、连接失败与超时返回非零，输出只包含异常类型。独占 Redis 连接在成功和失败时均关闭。CI 调用 shipping 入口及真实 Redis 租约负控，保留暂停 worker 后 API readiness 失效的验证。隔离 E2E 继承 shipping 超时。

终态竞争单测只验证当前终态 Owner 不重复发布事件，替代该测试中的状态用量读取，避免 unit 初始化真实 PostgreSQL/checkpoint 连接池并在 teardown 遗留后台任务。生产执行流程与真实 E2E 仍读取持久状态。

## 替代方案

扩大 Docker 超时仍会让每次探针初始化整套业务，增加 CPU 消耗且无法识别收敛停止。仅采用轻量 ARQ 设置只验证消费 key。共用 API 的三项租约验证可以同时移除冷导入故障并保持 readiness 语义。

## 后果

默认开发和隔离槽位均使用相同的 10 秒探针配置并显示 healthy，启动未完成时探针返回未就绪。三项 key 保留既有兼容 worker 契约，未引入本进程身份、集群选主、业务 schema 或新的医学规则。健康表示近期消费及收敛成功；业务正确性、真实模型质量和外部资料仍需独立验收。生产 Compose 已核对配置，生产镜像部署和生产负载未执行。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 冷探针不加载业务执行器 | 冷导入再次超出 10 秒 | 独立入口与健康服务 | `test/unit/services/test_worker_health_service.py` 子进程导入禁止器；实际新 worker 探针 0.731 秒、exit 0 | 禁止 Agent、模型、repository、PG、执行服务导入 | Passed |
| 三项租约共同决定健康 | 永久、空值或过长 TTL 掩盖失联 | 健康服务与既有生产者 | `test/integration/services/test_worker_health_service.py`，17 项真实 Redis 5.04 秒通过 | 三项逐个缺失、永久、过长、空值、自然过期 | Passed |
| 连接失败有界且无敏感输出 | 错目标或阻塞命令静默成功 | 独立入口 | CLI unit 的超时/连接关闭/异常内容；真实子进程错 Redis 目标 | 非零退出，输出仅异常类型 | Passed |
| Compose 与 CI 选择真实轻量探针 | 健康代码未装配或扩大超时掩盖故障 | Compose 与 workflow | 宿主机两个健康装配 unit 0.16 秒通过；实际两容器 Test/Timeout 回读 | 开发、生产、CI 与隔离 override 漂移必须失败 | Passed |
| 实际 worker 失联使接流量门禁关闭 | 只显示 healthy 而执行停止 | API readiness 与短期租约 | 隔离 worker 暂停后 API 503/WorkerUnavailableError、同队列探针 exit 1；恢复后 API 200 | worker 停止续租后拒绝接流量 | Passed |
| 实际业务执行仍正确绑定 Run | 探针成功但模型/工具/PG 输出异常 | Run/worker/SSE 与健康业务 Owner | 质量/配餐 9 项 E2E 98.42 秒通过，3 项实际 API/worker/SSE 与 6 项 PG 发布/checkpoint 负控 | 改源、撤同意、伪造上下文和检查回执 | Passed |

`test/unit/services/test_worker_health_service.py`、`test_readiness_service.py`、`test_run_queue_service.py`、`test_run_worker.py` 共 90 项通过，72.56 秒；另有宿主机两个健康装配 unit，通过的不同相关 unit 共 92 项。终态竞争测试修正前两个扩大回归在 teardown 被诊断中断，不计为通过。实际 HTTP 的 health/readiness 两项 2.33 秒通过，连同 Redis 17 项共 19 项 integration。Ruff 10 文件检查与格式、工程契约 147 decisions/196 docs、62 项检查器 unit 与 docs build 通过。

宿主机完整配置文件的 15 项运行中，初始化脚本两项在 Windows 失败：现有 `init.sh` Git 模式为 100644，不满足执行位断言，WSL 无 `/bin/bash`，无法完成正常初始化脚本执行。其余宿主机结果不替代 Linux 脚本验收；此次没有改写初始化脚本或伪造权限。健康装配两项已独立执行并通过，仓库全量 unit 与生产部署未声明通过。
