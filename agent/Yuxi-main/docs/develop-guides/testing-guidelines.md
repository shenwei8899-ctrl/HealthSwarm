# 测试规范

测试的目标是证明用户可观察的结果和工程边界，而不是堆积测试数量。先选最接近风险的最小测试集，再按改动范围扩大；单元测试不能代替真实 HTTP、数据库、worker、文件或浏览器验证。

## 测试分层

| 层级 | 目录 | 适合验证什么 | 环境 |
| --- | --- | --- | --- |
| Unit | `backend/test/unit` | 纯逻辑、边界值、状态转换和失败分支 | 不依赖运行中的 Docker 服务 |
| Integration | `backend/test/integration` | 真实 HTTP、认证、事务、锁、Schema、lease 和服务副作用 | 依赖 Docker Compose |
| E2E | `backend/test/e2e` | Run、SSE、worker、文件落盘和完整用户链路 | 依赖完整 Compose，数量少、速度慢 |
| Web unit | `web/test/unit` | 前端状态、组件和交互逻辑 | 通过 `pnpm test:unit` |
| CLI | `packages/yuxi-cli/tests` | CLI 配置、命令和客户端行为 | 独立 Python 包 |

同一个子项目只保留一个测试根目录，不要同时创建 `test` 和 `tests`。

高风险 Agent 主链路优先使用不依赖外部密钥的 deterministic assembled-path E2E；真实模型、浏览器和外部服务用于手工或周期探针。E2E 需要经过实际 API、worker、SSE 和最终持久化事实，不能用进程内 monkeypatch 代替。

## 如何选择目录

- 只调用纯 Python 逻辑、fake repository 或临时目录：放 `unit`。
- 要验证真实接口、认证、事务或 Redis/PostgreSQL 边界：放 `integration`；API 测试放 `integration/api`。
- 要从入口一路验证到最终 Run、文件或对象：放 `e2e`。
- 前端和 CLI 测试留在各自项目的测试根，不放到 backend。

不要因为测试文件少或执行快就把 integration 降成 unit；测试层级反映它依赖的真实边界。

## 命名和结构

文件名使用 `test_<domain>_<target>.py`，一个文件围绕一个清晰主题。测试函数使用 `test_<行为>_<预期结果>`，名称直接表达业务语义：

```text
test_create_agent_run_commits_before_enqueue
test_viewer_download_returns_attachment_response
test_agent_bubble_sort_run_creates_expected_artifacts
```

测试尽量保持 Arrange → Act → Assert 三段结构：

1. 准备数据、fixture 和外部条件；
2. 调用真实被测行为；
3. 断言业务结果、状态和副作用。

不要只断言 `status_code == 200`。根据风险回读数据库行、文件、对象、DOM、SSE 游标或协议 payload。失败信息应指出目标和实际值。

每个新 guard 都要有负向案例：恢复目标缺陷或制造非法状态后，测试必须因正确原因失败。Fixture、snapshot 和 expected output 只能显式更新并进入 diff，CI 不得一边生成 oracle 一边验证它。

## Fixture 和测试数据

- 同一文件内复用的准备逻辑优先写本地 helper；多个文件需要时再放对应层级的 `conftest.py`。
- `backend/test/conftest.py` 只保留通用 marker，不绑定真实服务。
- integration fixture 负责创建 `test_client`、测试用户和测试资源；不要依赖数据库里碰巧存在的 Agent、模型或知识库。
- E2E fixture 负责真实入口、账号和资源清理；测试结束后删除自己创建的对话、文件、Run 和外部对象。
- 不在测试或文档中写真实账号、密码、Token、用户数据和本地绝对路径。

## skip 规则

只在以下情况使用 `pytest.skip`：

1. 外部可选服务确实未提供，例如 OCR 或真实模型服务；
2. E2E 所需的测试账号或环境变量没有配置。

“系统没有默认数据”不是 skip 理由。用 fixture 显式创建资源，或者让测试失败暴露环境问题。不要用 `print`、日志关键词或 `if __name__ == "__main__"` 判断测试结果。

## 修改 Bug 或既有功能

修复 Bug：

1. 先补一个稳定复现原问题的测试；
2. 再修改实现；
3. 先运行最小相关测试；
4. 再运行受影响层级的回归测试。

修改既有行为时，同时更新正向和负向断言。涉及 API、权限、持久化、队列、SSE、沙盒或恢复时，按风险升级到真实 integration 或 E2E。

## 常用命令

### 餐单列表分页验证

餐单列表的 unit 验证参数传递、页切片和当前授权拒绝；integration 使用 shipping 路由、真实 TCP 与独立 PostgreSQL schema，按预先确定的 61 份合成餐单核对跨页顺序、相同更新时间的次排序、账号和成员隔离、主成员及家庭参与者撤权。每次 GET 前后比较全 schema 的行内容及 `xmin`，清理后核对 schema 已从 catalog 移除。数据库须为独立测试环境；未配置 PostgreSQL 时的 skip 不能算验收通过。

```bash
docker compose exec -T -u root api uv run --no-sync --group test pytest test/unit/services/test_health_meal_plan_pagination.py test/unit/services/test_health_meal_planner.py test/unit/services/test_health_family_meal_plan.py -q
docker compose exec -T -u root api uv run --no-sync --group test pytest test/integration/services/test_health_meal_plan_pagination_http.py -q
docker compose exec -T web pnpm run test:unit
docker compose exec -T web pnpm run lint:check
docker compose exec -T web pnpm run build
```

实际浏览器在已有后台核对首页 50 份、末页 11 份、前后翻页、刷新、空成员和撤权清理；迟到读取、保存后重置首页和网络失败分支另由编译组件 unit 验证。偏移分页不承诺并发修改期间的固定快照，客户端行为见[餐单分页参考](../advanced/health-meal-plan-pagination.md)。此查询没有新增 Worker 或模型执行路径。

先启动开发环境：

```bash
docker compose up -d
docker compose ps
docker compose logs --tail=100 api
```

后端：

```bash
docker compose exec api uv run --group test pytest test/unit -m "not slow"
docker compose exec api uv run --group test pytest test/integration
docker compose exec api uv run --group test pytest test/e2e/test_deterministic_agent_path_e2e.py -m e2e
docker compose exec api uv run --group test pytest test
```

也可以从仓库根目录使用脚本：

```bash
backend/test/run_tests.sh unit
backend/test/run_tests.sh integration
backend/test/run_tests.sh e2e
backend/test/run_tests.sh e2e-all  # 显式运行真实模型与外部服务探针
backend/test/run_tests.sh all
```

前端：

```bash
docker compose exec web pnpm run lint:check
docker compose exec web pnpm run test:unit
docker compose exec web pnpm run build
```

CLI：

```bash
cd packages/yuxi-cli
uv run pytest
```

工程契约、文档构建和补丁检查：

```bash
python3 scripts/verify_engineering_contracts.py
python3 -m unittest scripts.test_verify_engineering_contracts
cd docs && pnpm run build
git diff --check
```

依赖供应链检查：

```bash
make audit-dependencies
make audit-licenses
```

Windows 初始化脚本的安全行为需要在 Windows 或 PowerShell 7 环境中验证：

```powershell
pwsh -NoProfile -File scripts/test_init_security.ps1
```

这些命令的实际 workflow 和 selector 由仓库 `.github/workflows` 与 `Makefile` 维护；文档不复制一份会漂移的 CI 配置。

## 健康咨询隔离合成 E2E

健康咨询的确定性链路只在专用 Compose 槽位运行，使用独立数据库、状态目录及禁止外联的网络。普通 E2E 命令明确跳过这个用例。配置和重放入口由 `backend/test/support/health_consultation_e2e.*` 及 `health_consultation_replay_server.py` 拥有；样例凭据仅用于合成测试，不能用于部署。测试 runner 从 API 容器内访问实际 HTTP 进程，独立 worker 负责执行，不依赖宿主机能否访问 internal 网络的发布端口。

仓库根目录 PowerShell 命令如下。需要已构建的 API 与 provisioner 镜像；名称不同时显式设置 `YUXI_TEST_API_IMAGE`、`YUXI_TEST_PROVISIONER_IMAGE`，不要更改原开发槽位。

```powershell
$healthCompose = @('--env-file', 'backend/test/support/health_consultation_e2e.env.example', '-f', 'docker-compose.yml', '-f', 'backend/test/support/health_consultation_e2e.compose.yml')
docker compose @healthCompose config --quiet
docker compose @healthCompose up -d --no-build --pull never postgres redis minio sandbox-provisioner api worker
docker compose @healthCompose exec -d api uv run --no-sync --no-dev python test/support/health_consultation_replay_server.py
docker compose @healthCompose exec -T api timeout -k 5s 150s uv run --no-sync --group test pytest test/e2e/test_health_consultation_e2e.py test/unit/services/test_health_consultation_replay.py -q --tb=short --show-capture=no -o cache_dir=/tmp/health-consultation-e2e-guards
docker compose @healthCompose stop api worker sandbox-provisioner minio redis postgres
```

应观察 23 项通过；真实链路将模型首次响应暂停，核对第二条 Request 排队，再释放并回读各自 SSE、Run / Attempt / Message、manifest 与 PostgreSQL checkpoint。未绑定或未同意的请求不得创建业务行。停止后保留专用卷；不要使用 `down -v` 删除已有数据。审批配置恢复为空，成功用例只精确清理自身的随机测试账号和 thread。测试失败时先检查所属 Run 是否收敛，不直接删除活动 worker 的数据。固定合成模型不证明真实供应商质量、医学准确性或专业知识库验收，范围见[端到端决策](./decisions/implemented/2026-10-04-health-consultation-e2e.md)。

## 饮食识图与咨询联合合成 E2E

饮食验收复用上一节的专用槽位。视觉重放只接受一到三张人工定义的纯色 PNG，返回没有份量及营养数值的固定食品候选。用户纠错、份量和个人食用比例经版本化计算后，正式确认生成私有日记。两个重放服务分别监听不同端口，实际 worker 连续执行饮食和咨询，覆盖配置切换后的跨进程读取。

启动专用槽位后执行下列 PowerShell 命令；`$healthCompose` 沿用上一节，不与原开发 Compose 混用。

```powershell
docker compose @healthCompose exec -d api uv run --no-sync --no-dev python test/support/health_meal_replay_server.py
docker compose @healthCompose exec -T api timeout -k 5s 150s uv run --no-sync --group test pytest test/e2e/test_health_meal_e2e.py test/e2e/test_health_consultation_e2e.py test/unit/services/test_health_meal_replay.py test/unit/services/test_health_consultation_replay.py -q --tb=short --show-capture=no -o cache_dir=/tmp/health-joint-e2e
docker compose @healthCompose stop api worker sandbox-provisioner minio redis postgres
```

应观察 57 项通过，包含四种保持旧投影的排队撤销。饮食用例回读上传摘要、实际视觉请求、Task 终态及清空的 owner/lease、原始识别对象、草稿修订、计算快照与唯一日记；未同意、旧计算确认和跨账号读取均拒绝。协议重放 guard 有独立负控。任务收敛失败仍撤销合成审批；外层 fixture 遇到本轮非终态或残留租约 Task 时拒绝删除账号、PG 及图片对象，保留诊断事实。普通开发槽位明确跳过合成 E2E。范围及手算 oracle 见[饮食验收决策](./decisions/implemented/2026-10-04-health-meal-e2e.md)，审批与外呼配置核对见[健康模型配置决定](./decisions/implemented/2026-10-04-health-model-authority.md)。真实模型识别、专业规则及食品授权需要另行验收。

## 有效采用餐单采购验证

采购从已正式采用的个人或家庭餐单读取食材可食需求，用用户明确确认的同食品版本、同烹饪状态库存计算净量。单元测试核对独立手算、未知和零的语义及固定模型输出协议；独立PG schema验证正式21→22升级、幂等及旧事实保留。权限、独立用途、运行回执与外部边界由[采购决定](./decisions/implemented/2026-10-10-health-purchase-agent.md)解释。

```powershell
docker compose exec -T api timeout -k 5s 240s uv run --no-sync --group test pytest test/unit/services/test_health_purchase.py test/unit/services/test_health_nutritionist.py test/integration/services/test_health_purchase_schema.py test/integration/services/test_health_safe_planner_schema.py -q --tb=short -o cache_dir=/tmp/health-purchase-unit-schema
```

真实HTTP与Worker验证复用前述专用健康槽位及`$healthCompose`，要求当前schema、API和Worker就绪且没有其他活动用例。fixture核对隔离标记及独立数据库，自动启动8776本地重放；通过真实配置接口审批该合成采购处理方，逐成员取得`purchase`同意。相同处理方的`meal_plan`审批和同意仅用于用途不能复用的负控。fixture恢复全部用途关闭，删除本轮provider并停止精确重放进程。普通环境明确跳过需要该装配的用例。

```powershell
docker compose @healthCompose exec -T -e HEALTH_CONSULTATION_E2E_ISOLATED=true -e TEST_BASE_URL=http://localhost:5050 api timeout -k 5s 180s uv run --no-sync --group test pytest test/integration/services/test_health_purchase_http.py test/e2e/test_health_purchase_e2e.py -q --tb=short -o cache_dir=/tmp/health-purchase-http-worker
```

必须核对个人300−40=260g、家庭360−40=320g、并发幂等、当前Request与Run、固定Skill和工具manifest、同Run唯一PG回执及权威Message。正常、重复和问题输出完成；非法字段、伪造及前Run回执不能发布。工具回执形成后撤用途同意、撤采用、专业源版本变化或家庭第二成员撤权，迟到模型答复均不能成为Message。测试结束回查所属资源、provider和重放进程归零、审批关闭；全局配置的管理员审计标记保留。历史执行结果见采购决定，当前数量以实际收集和终态为准。生产采购模型审批、SKU/包装/毛重换算、价格、交易及会计费用另行对接验收。

## 目标绑定、次日提议与任务投影验证

个人目标只绑定当前已发布规则与档案版本；分析记录窗口和当前目标的适用时间分别报告。用户登记次日提议核对同一完成 Request、Run、最终 Message 与普通预览，活跃 Run 必须快速拒绝并释放成员锁。统一任务投影沿用已有执行链路，分别读取执行状态与当前授权下的业务结果。验收边界由[个人目标决定](./decisions/implemented/2026-10-10-health-agent-personal-targets.md)、[次日提议决定](./decisions/implemented/2026-10-10-health-agent-next-day-proposal.md)和[任务投影决定](./decisions/implemented/2026-10-10-health-task-projection.md)拥有。

```powershell
docker compose exec -T api uv run --no-sync --group test pytest test/unit/services/test_health_agent_personal_targets.py test/unit/services/test_health_next_day_agent.py test/unit/services/test_health_task_projection.py test/unit/services/test_health_consultation_citations.py test/unit/services/test_health_route_trace.py test/unit/services/test_health_vision_usage.py -q
```

真实接口及 Worker 用例复用前述独立健康槽位。各 fixture 拥有当前配置恢复、合成身份和结果清理；需要回放的 Worker 用例启动其对应 support 回放服务，同一槽位串行运行。目标撤回、来源变化、最终消息错绑、非法字段、缺失选择和不支持的任务必须显式失败或返回补充状态；失败或依赖未就绪不能产生正式业务写入。正式升级的私有 PG schema 测试核对 22→当前版本、幂等升级、历史空绑定和未来版本拒绝，版本值以迁移 Owner 为准。

## 隔离固定图发布门禁

从 Yuxi 目录运行 Bash 门禁，使用已构建的项目镜像及 Docker Compose。隔离 Compose 的 `YUXI_TEST_API_IMAGE`、`YUXI_TEST_PROVISIONER_IMAGE` 和 `YUXI_TEST_MINIO_IMAGE` 指定三个已构建镜像的标签；使用不同于隔离配置默认值的标签时先设置这三个环境变量，门禁不构建或下载镜像：

```bash
bash scripts/ci_health_agent_replay.sh
```

脚本建立全新的 `health-agent-ci` 项目，拒绝接管已有同名容器；独立标记和真实数据库名通过保护后，顺序执行咨询、审核科普检索、配餐、分析、专业审核、采购、目标、次日提议的 Worker 和 PG 负控，以及来源撤回后的搜索计数、摘要和公开线程分页。每阶段必须实际收集用例、零跳过且退出成功；最终结果、同 Run 回执、授权撤销、非法输出和活跃 Run 锁拒绝均由各领域 oracle 核对。脚本在结束时清理本轮专属容器和卷，测试回执留在被忽略的 `backend/test/.tmp/`。API 与 Worker 沿用服务 UID，独立测试 CLI 以 root 写入挂载的回执目录。

该命令验证合成协议、装配和持久链路。真实模型质量、专业内容、生产费用及外部接口仍须分别验收。HealthSwarm 的工作流模板位于 Yuxi 子目录，远端仓库根自动 CI 入口待维护者配置；本地门禁通过与远端工作流通过分别记录。

## 审核科普索引、引用发布与正文读取

受限科普检索使用当前 PostgreSQL 片段重建本地词法索引；容量、取消、fresh 来源、同 Run 引用及普通 Agent 兼容分别在语义 Owner 处验证。合成 gold 与 Recall/F1 只验证工程检索，不替代专业语料或医学评估，范围见[检索决定](decisions/implemented/2026-10-10-health-evidence-lexical-index.md)。

```powershell
docker compose exec -T api uv run --no-sync --group test pytest test/unit/services/test_health_evidence_index.py test/unit/services/test_health_evidence_index_publication.py test/unit/services/test_health_evidence_publication.py test/unit/services/test_health_evidence_read_boundary.py test/unit/services/test_health_evidence_search_visibility.py test/unit/services/test_health_consultation_citations.py -q
```

真实 PG 与 HTTP 验证复用专用健康槽位及 `$healthCompose`，同一槽位不并发修改审批配置。下列用例调用真实检索、图校验与最终 save Owner；两 Session 分别更新和读取来源，核对 owning publication 持有的共享锁、提交或回滚结果。Completed 答复随后撤回实际采用来源，核对 result、history、state 消息投影和 search，保留相邻有效 Run 与未采用来源，并复验专用引用和 Task 的错误状态。

```powershell
docker compose @healthCompose exec -T -u root api uv run --no-sync --group test pytest test/integration/services/test_health_evidence_lexical_http.py test/integration/services/test_health_evidence_final_publication_http.py test/integration/services/test_health_evidence_search_visibility_http.py -q
```

固定图发布门禁另执行检索 Worker 用例，使用预先声明的合成 gold 核对最终同 Run 引用、当前来源、撤回及新版本重建。所有用例结束后回读所属 PG/Redis 资源、审批及 provider 基线恢复、精确 helper 进程和 readiness；重新创建 adapter 证明无持久缓存，不作为实际进程重启或生产 SLO 的验收。

## 健康 Run 预算与咨询失败发布

五个固定健康角色的预算从 Run 首次执行起计，同一 Run 的重试不能重置起点。先运行预算、取消竞争及咨询失败发布的相关单测：

```powershell
docker compose exec -T api uv run --no-sync --group test pytest test/unit/services/test_run_worker.py test/unit/services/test_health_consultation_partial_publication.py -q --tb=short
```

SDK 的剩余时限与单次 HTTP 发送由 `test/integration/services/test_health_model_execution_budget_http.py` 验证。真实三秒实验须在健康隔离 Compose 后追加 `backend/test/support/health_run_budget_e2e.compose.yml`，启动所属预算回放，执行 `test/e2e/test_health_run_execution_budget_e2e.py`；其中双 attempt 用例需要暂停隔离 Worker，必须在 finally 恢复。完成后去掉预算覆盖层，以原隔离配置重建 API 和 Worker，核对默认预算、ready、所属队列、PG 终态与清理。该覆盖层不用于主服务或固定图 CI。

咨询失败验收核对同 Run/Request 的 failed 状态、空最终指针以及没有普通回答正文；显式 interrupt 仅保留固定错误投影。恢复正常隔离配置后，再执行 `test/e2e/test_health_nutritionist_e2e.py`，核对有效答案和无效引用两条发布路径。使用量缺失保持未知，合成回放不证明实际供应商质量或专业判断。

## 多页报告与健康链路联合合成 E2E

多页报告验收面向后台维护者，复用健康专用槽位并叠加 `backend/test/support/health_report_e2e.compose.yml`。临时证书只在该测试槽位受信任，OCR 和字段模型使用同一个本地 HTTPS 重放进程；原开发和部署环境不加载覆盖层。测试 runner 直接调用真实解析客户端做公共 CA 拒绝负控，独立 worker 完成两页 PDF、失败页重识别及人工确认。重放返回像素框和匹配输入元数据，第二页使用包含身份、表头、指标及注入行的 HTML 表格；字段协议只接受预定归一化框及脱敏后的指标行。坐标规则与验证边界见[坐标验收决策](./decisions/implemented/2026-10-04-health-report-coordinates.md)，行与列语义见[表格验收决策](./decisions/implemented/2026-10-04-health-report-tables.md)。合成样本只证明装配与协议回归，范围见[报告验收决策](./decisions/implemented/2026-10-04-health-report-e2e.md)。

以下 PowerShell 命令从仓库根运行，镜像前置条件沿用健康咨询节。先确认专用槽位没有活动测试任务，再停止专用 API 与 worker；证书生成覆盖的只是该槽位的合成证书对，有效期两天，不能将挂载目录指向部署证书。停止进程也关闭旧的重放服务，因此重新启动后每个重放只启动一次。

```powershell
$healthReportCompose = @('--env-file', 'backend/test/support/health_consultation_e2e.env.example', '-f', 'docker-compose.yml', '-f', 'backend/test/support/health_consultation_e2e.compose.yml', '-f', 'backend/test/support/health_report_e2e.compose.yml')
docker compose @healthReportCompose config --quiet
docker compose @healthReportCompose stop api worker
docker compose @healthReportCompose run --rm --no-deps --entrypoint openssl api req -x509 -newkey rsa:2048 -noenc -days 2 -keyout /app/health-report-tls/key.pem -out /app/health-report-tls/cert.pem -subj /CN=api -addext 'subjectAltName=DNS:api,DNS:localhost,IP:127.0.0.1'
docker compose @healthReportCompose up -d --no-build --pull never postgres redis minio sandbox-provisioner api worker
docker compose @healthReportCompose exec -d api uv run --no-sync --no-dev python test/support/health_report_replay_server.py
docker compose @healthReportCompose exec -d api uv run --no-sync --no-dev python test/support/health_meal_replay_server.py
docker compose @healthReportCompose exec -d api uv run --no-sync --no-dev python test/support/health_consultation_replay_server.py
docker compose @healthReportCompose exec -T api timeout -k 5s 180s uv run --no-sync --group test pytest test/e2e/test_health_report_e2e.py test/e2e/test_health_meal_e2e.py test/e2e/test_health_consultation_e2e.py test/unit/services/test_health_report_tables.py test/unit/services/test_health_report_coordinates.py test/unit/services/test_health_report_replay.py test/unit/services/test_health_meal_replay.py test/unit/services/test_health_consultation_replay.py test/integration/services/test_health_vision_http.py -q --tb=short --show-capture=no -o cache_dir=/tmp/health-model-table-joint-regression
docker compose @healthReportCompose stop api worker sandbox-provisioner minio redis postgres
```

必须全部通过，包含四种保持旧投影的排队撤销；实际数量以当前收集及终态输出为准，历史运行结果见上述决策。报告回读两页上传摘要、固定 OCR multipart、逐页下载和字段请求、私有 HTML 原文、规范行证据、重新识别的新外部标识及 v3 草稿。像素原始框与归一化字段证据逐层对照；47 项坐标用例覆盖未知元数据、越界、预处理及零面积，46 项表格用例覆盖行与列、未知或重复表头、空表及损坏结构。第一页补充的日期保留，未解决失败页和旧版本不能确认；三次并发确认只写两条成员指标。通用配置 API 按字段合并，因此 fixture 显式清空 OCR 地址和凭据，并回读 PG；健康审批恢复关闭。成功清理包含重识别之前的原始 receipt，真实 PG 和 MinIO 负控证明越出所属 Task 前缀的文件保留。非终态或残留 owner/lease 保留账号及诊断事实，不执行 `down -v`。

普通槽位的报告 E2E 为明确 skip；相关 unit 和 HTTP 仍可运行：

```powershell
docker compose exec -T api timeout -k 5s 240s uv run --no-sync --group test pytest test/unit/services/test_health_vision_statistics.py test/unit/services/test_health_model_freshness.py test/unit/services/test_health_report_tables.py test/unit/services/test_health_report_coordinates.py test/unit/services/test_health_vision.py test/unit/services/test_health_vision_protocol.py test/unit/services/test_health_report_transforms.py test/unit/services/test_health_report_reprocess.py test/unit/services/test_health_ocr_resume.py test/unit/services/test_health_recipe_portions.py test/unit/services/test_health_consultation.py test/unit/services/test_model_cache.py test/integration/services/test_health_vision_http.py test/e2e/test_health_report_e2e.py -q --tb=short --show-capture=no -o cache_dir=/tmp/health-statistics-final-regression
```

应观察 373 passed、1 skipped。跳过是缺少合成隔离与 TLS 装配，不代表真实云识图通过；云质量、临床词典和授权食品数据需单独批准及验收。

## 健康模型配置撤销验证

健康外呼的 PostgreSQL 配置核对、旧投影拒绝和内部实例绑定由[健康模型配置决定](./decisions/implemented/2026-10-04-health-model-authority.md)解释。相关 unit 不使用云模型；executor 用独立 PG Schema、唯一合成账号和真实 MinIO，不改变运行实例的审批。执行器集合需要 240 秒上限，不能把超时或中途终止算作通过。

```powershell
docker compose exec -T api timeout -k 5s 90s uv run --no-sync --group test pytest test/unit/services/test_health_model_freshness.py test/unit/services/test_model_cache.py test/unit/services/test_health_vision.py test/unit/services/test_health_consultation.py -q --tb=short --show-capture=no -o cache_dir=/tmp/health-model-final-unit
docker compose exec -T api timeout -k 5s 240s uv run --no-sync --group test pytest test/integration/services/test_health_vision_executor.py -q --tb=short --show-capture=no -x -o cache_dir=/tmp/health-model-pg-final
```

应观察 unit 69 passed、PG executor 31 passed。数据库停用、清空凭据、改变端点或模型类型后，保持旧投影的执行器必须在下一外呼前拒绝，无草稿、原始结果或正式记录，Task 释放 lease。恢复仅缓存授权或去掉实例绑定必须使相应回归变红。

按上一节启动专用 Compose 和三个重放入口后，在停止服务前执行：

```powershell
docker compose @healthReportCompose exec -T api timeout -k 5s 180s uv run --no-sync --group test pytest test/e2e/test_health_meal_e2e.py test/e2e/test_health_report_e2e.py test/e2e/test_health_consultation_e2e.py test/unit/services/test_health_model_freshness.py test/unit/services/test_model_cache.py test/unit/services/test_health_vision.py test/unit/services/test_health_consultation.py test/integration/services/test_health_vision_http.py -q --tb=short --show-capture=no -x -o cache_dir=/tmp/health-model-authority-joint-verified
```

必须全部通过；实际数量以当前收集及终态输出为准，历史运行结果见健康模型配置决定。四种排队撤销保持旧 Redis 模型视图，通过实际 ARQ worker、健康 HTTP 状态及 PG 终态核对拒绝；本地重放调用列表不增加，审批接口拒绝旧模型。正常报告、饮食和成员咨询继续执行。真实云凭据、样本准确率、费用和临床质量不在这些合成用例的验收范围。

## 健康识图运行统计验证

成员、用途及三十天统计口径由[成员统计决定](./decisions/implemented/2026-10-04-health-vision-statistics.md)拥有。统计只读已有 PG 事实，不发起 OCR 或模型调用；HTTP fixture 创建自己的合成账号和资源。任务时间点及识别初始快照显式写入 PG，修订、营养计算、确认和摘要读取走真实 HTTP。它们证明统计与权限，不证明真实模型质量。

```powershell
docker compose exec -T api timeout -k 5s 180s uv run --no-sync --group test pytest test/unit/services/test_health_vision_statistics.py test/unit/services/test_health_model_freshness.py test/unit/services/test_health_vision.py test/unit/services/test_health_consultation.py test/unit/services/test_model_cache.py test/integration/services/test_health_vision_http.py -q --tb=short --show-capture=no -x -o cache_dir=/tmp/health-statistics-joint
docker compose exec -T web node --test test/healthVisionStatistics.test.js test/healthVisionView.test.js test/healthVision.test.js test/healthReportReview.test.js test/healthMealReview.test.js test/unit/conversationModelBinding.test.js
```

应观察后端一百项、前端三十七项通过。核对六十条任务的完整窗口及最近秩 P50/P95、窗外和未来记录排除、无时间点不补零、修改与排除分母、待复核及人工来源不当作模型修改、未知份量及不完整日记。双账号、管理员、用途 scope、撤权与删源必须限制统计可见性，响应不得包含正文、对象键或原始 Task 错误。页面展开时按需加载，切换成员及用途清空旧值，迟到响应或刷新失败不保留私有摘要；真实页面另查空样本、撤权错误及窄屏。深色主题需获临时偏好更改授权后检查并恢复，不能用 token 检查代替。

## 饮食固定快照请求验证

共享调用的 SDK wire 单测使用保留域名和 httpx 重放，不需要云凭据。饮食固定快照省略供应商 JSON 模式参数，报告字段仍请求 JSON 对象；返回内容继续经过本地 JSON 和领域 Schema 校验。恢复饮食旧参数会使对应 wire 断言及合成视觉协议失败。普通文本、JSON 数组和模型补造的份量或营养字段必须被拒绝，不能自动追加第二次请求。

```powershell
docker compose exec -T api timeout -k 5s 90s uv run --no-sync --group test pytest test/unit/services/test_health_vision_model_wire.py test/unit/services/test_health_meal_replay.py test/unit/services/test_health_vision_protocol.py test/unit/services/test_health_vision.py -q --tb=short --show-capture=no -o cache_dir=/tmp/health-wire-final-unit
```

真实 Task 装配验证复用[多页报告与健康链路联合合成 E2E](#多页报告与健康链路联合合成-e2e)的隔离槽位、TLS 和三个重放服务；先启动并确认 ready，再执行以下命令。`$healthReportCompose` 沿用该节的 Compose 参数。完成后按该节停止专用服务，保留卷，不改变原开发槽位的云配置。

```powershell
docker compose @healthReportCompose exec -T api timeout -k 5s 180s uv run --no-sync --group test pytest test/e2e/test_health_meal_e2e.py test/e2e/test_health_report_e2e.py test/e2e/test_health_consultation_e2e.py test/unit/services/test_health_vision_model_wire.py test/unit/services/test_health_meal_replay.py test/unit/services/test_health_vision_protocol.py test/unit/services/test_health_model_freshness.py test/unit/services/test_model_cache.py test/unit/services/test_health_vision.py test/unit/services/test_health_consultation.py test/integration/services/test_health_vision_http.py -q --tb=short --show-capture=no -x -o cache_dir=/tmp/health-snapshot-json-joint
```

检查实际 Task 终态和清空的 lease、私有识别结果、草稿版本及确认后 PG 快照。合成重放校验调用形态和持久链路；真实快照能否稳定返回 JSON、实际菜品召回、称重误差及费用需要另行批准的云探针与质量样本。

## 饮食照片观察验证

可见食材和多视角位置框属于待复核观察；来源、版本及兼容边界由[饮食照片观察决定](./decisions/implemented/2026-10-05-health-meal-observations.md)解释。SDK wire 独立核对实际 system 提示词的字段与语义，不从 producer 生成期望值；DTO、模型 parser、HTTP 修订及人工来源负控分别验证各自边界。相关命令不调用真实云模型。

```powershell
docker compose exec -T api timeout -k 5s 180s uv run --no-sync --group test pytest test/unit/services/test_health_meal_observations.py test/unit/services/test_health_vision_model_wire.py test/unit/services/test_health_vision.py test/unit/services/test_health_recipe_portions.py test/unit/services/test_health_vision_statistics.py test/unit/services/test_health_model_freshness.py test/integration/services/test_health_vision_http.py -q --tb=short --show-capture=no -x -o cache_dir=/tmp/health-meal-observations-regression-final
docker compose exec -T web node --test test/healthMealReview.test.js test/healthVision.test.js test/healthVisionStatistics.test.js test/healthVisionView.test.js test/healthReportReview.test.js test/unit/conversationModelBinding.test.js
docker compose exec -T web pnpm run lint:check
docker compose exec -T web pnpm run build
```

必须全部通过；历史运行分别为 136 项后端、39 项前端。实际 worker 验证复用前述健康隔离槽位及三个重放服务，沿用 `$healthReportCompose`。启动并确认 ready 后运行，结束后停止专用服务并保留卷。

```powershell
docker compose @healthReportCompose exec -T api timeout -k 5s 180s uv run --no-sync --group test pytest test/e2e/test_health_meal_e2e.py test/e2e/test_health_report_e2e.py test/e2e/test_health_consultation_e2e.py test/unit/services/test_health_vision_model_wire.py test/unit/services/test_health_meal_observations.py test/unit/services/test_health_meal_replay.py test/unit/services/test_health_model_freshness.py test/unit/services/test_health_vision.py test/unit/services/test_health_consultation.py test/integration/services/test_health_vision_http.py -q --tb=short --show-capture=no -x -o cache_dir=/tmp/health-meal-observations-joint
```

必须全部通过；历史运行 147 项。回读服务器照片序号与原上传绑定、修订不改变原框和来源、人工食材纠正、确认日记的观察快照及独立手算营养。修改来源、新项伪造框、人工草稿伪造来源和旧提示词均拒绝；失败后回读原草稿保持不变。浏览器视觉验证使用实际组件的明确合成替身，检查食材编辑、加载与错误恢复、只读预览及浅/暗色响应式；以 DOM 实测 CSS 宽度为准。视觉替身不能代替真实 HTTP 权限与持久链路，也不证明真实模型食材或定位质量。

## 健康识图重试与 JSON 包装验证

页面重试通过实际编译事件和页面脚本验证，不能只测试脚本中的全局 UUID。视觉非 JSON 模式接受单个完整代码块；报告 JSON 模式仍拒绝包装。混合正文、多块、截断、数组以及模型份量/营养字段负控由 SDK wire 验证，任何输入都不追加自动纠正调用。边界与未验证范围见[重试与包装决定](./decisions/implemented/2026-10-05-health-recognition-retry-json.md)。

```powershell
docker compose exec -T api uv run --no-sync --group test pytest test/unit/services/test_health_vision_model_wire.py test/unit/services/test_health_meal_replay.py -q --tb=short --show-capture=no -o cache_dir=/tmp/health-retry-reviewed
docker compose exec -T web node --test test/healthVisionView.test.js test/healthVision.test.js test/healthMealReview.test.js test/healthReportReview.test.js test/healthVisionStatistics.test.js
docker compose exec -T web pnpm run lint:check
docker compose exec -T web pnpm run build
```

真实 worker 验证复用[健康咨询隔离合成 E2E](#健康咨询隔离合成-e2e)的 `$healthCompose` 和镜像前置条件，启动后只需饮食重放。重放成功内容采用完整 JSON 代码块，由响应 oracle 独立核对；裸对象路径另由 wire 验证。

```powershell
docker compose @healthCompose exec -d api uv run --no-sync --no-dev python test/support/health_meal_replay_server.py
docker compose @healthCompose exec -T api timeout -k 5s 150s uv run --no-sync --group test pytest test/e2e/test_health_meal_e2e.py test/unit/services/test_health_meal_replay.py test/unit/services/test_health_vision_model_wire.py -q --tb=short --show-capture=no -x -o cache_dir=/tmp/health-retry-fenced-e2e
docker compose @healthCompose stop api worker sandbox-provisioner minio redis postgres
```

历史运行后端 wire/replay 51 项、前端五文件 35 项、隔离联合 56 项通过。结束后回读活动任务为零及合成审批关闭，再停止专用服务，保留卷。浏览器只能使用明确合成替身或经批准的隔离资源；不得通过用户现有收费任务证明按钮修复，也不能据重放推断原失败响应的具体格式。

## 单成员安全配餐真实模型探针

维护者使用[健康咨询独立槽位](#健康咨询隔离合成-e2e)和已配置的固定聊天模型验证中文换菜、三餐重生成、无候选与规则未就绪。探针仅创建合成资料、菜谱和批准规则；覆盖边界见[真实模型探针决定](./decisions/implemented/2026-10-09-safe-planner-real-model-probe.md)。先确认独立API与Worker就绪、无活动请求，并保留原Compose参数。增加`backend/test/support/health_safe_planner_live.compose.yml`覆盖层后，仅API与Worker获得外部网络。

```powershell
$safePlannerLiveCompose = @($healthCompose) + @('-f', 'backend/test/support/health_safe_planner_live.compose.yml')
docker compose @safePlannerLiveCompose config --quiet
docker compose @safePlannerLiveCompose up -d --no-build --pull never --no-deps api worker
```

由已配置供应商的正式Owner导出选定模型，经内存管道传给独立测试进程。`export`输出包含凭据，必须直接捕获后传递，禁止单独运行、打印或保存该变量。每一步检查退出码；配置导出失败时停止。以下命令在Yuxi目录执行，主服务沿用其默认Compose，`$healthCompose`必须指向独立槽位。

```powershell
$safePlannerWire = docker compose exec -T -e RUN_HEALTH_SAFE_PLANNER_REAL_MODEL=1 api uv run --no-sync --group test python -m test.support.health_safe_planner_live_runner export --spec '<configured-provider>:<fixed-chat-model>'
if ($LASTEXITCODE -ne 0) { $safePlannerWire = $null; throw '模型配置未就绪' }
try {
    $safePlannerWire | docker compose @safePlannerLiveCompose exec -T -e RUN_HEALTH_SAFE_PLANNER_REAL_MODEL=1 api uv run --no-sync --group test python -m test.support.health_safe_planner_live_runner run
    if ($LASTEXITCODE -ne 0) { throw '真实模型探针未通过，先核对合成诊断' }
} finally {
    $safePlannerWire = $null
}
```

入口要求显式开启、独立标记和实际数据库身份，并拒绝默认模型、本地回放、latest/preview浮动别名和无效端点。四个场景每例提交一次请求，不追加模型修复或备用调用。输出必须与同Run持久回执一致，独立手算换菜300→310、重生成300→305，预览前后正式业务事实深等。仅成功换菜额外明确确认保存并用原包原键恢复，回读唯一新修订和旧专业批准及采用失效。

结束后先核对Run终态、租约及清理释放，将`/tmp/health-safe-planner-live-evidence`复制到本地受控且被忽略的测试输出目录，再用原`$healthCompose`重建API与Worker，移除已无连接的本轮`health-live-egress`网络。fixture恢复空配置、删除本轮临时供应商及合成数据并精确清理运行事件；用独立连接核对PG与Redis残留，以及主槽配置摘要未变。失败场景的有界合成模型诊断在清理前保留，日志只输出ID与状态。主槽正式配餐用途须单独审批；生产专业资料、医学质量和长期性能仍需单独验收。

## 性能评测

性能工具位于 `backend/test/performance/`；参数、采样和探针的单测位于 `backend/test/unit/performance/`，由常规后端 unit 命令执行。仓库根目录使用同一个模块入口，Python 环境需要后端依赖：

```bash
python -m backend.test.performance --help
python -m backend.test.performance matrix --help
python -m backend.test.performance load --help
python -m backend.test.performance report tmp/load-tests/continuous/final-20260907/matrix.json
docker compose exec api uv run --group test pytest test/unit/performance -q
```

`matrix` 测不同用户、固定 Thread、完成后立即补位的闭环调度；`load` 保留通用对话与沙盒容量场景，协议不同，不能混算。两者执行采样会产生真实模型费用。默认矩阵为 3150 请求，小实验通过 `--workers`、`--concurrency`、`--rounds-per-thread` 显式缩减，不自动预热。认证变量、独立槽位与结果边界见[并发优化决策](decisions/archived/0.7.3/12-concurrency/2026-09-07-agent-concurrency-optimization.md)。

矩阵只在[隔离槽位](./parallel-worktree-environments.md)运行。先导出槽位变量、测试认证变量和 `MATRIX_FINE_TIMING`，用 `docker compose -f docker-compose.yml -f backend/test/performance/compose.yml up -d --no-deps api` 装配实验 API；矩阵命令按 `--workers` 重建实验 Worker。采样结束或中断后，用普通 Compose 的 `up -d --no-deps --force-recreate --scale worker=1 api worker` 恢复普通入口。探针属于实验装配，不进入 shipping 启动。

`report` 默认只读已有样本，在相同目录生成 `stages.json` 与 `report.md`，不访问容器或模型，不改原始样本；仅在实验容器仍运行时显式使用 `--refresh` 补齐日志，并另外保存 `complete.json`。本地派生报告不替代决策记录中的可审阅结果。

## 证据和报告

测试结果必须说明：

- 实际执行的完整命令；
- 通过、失败或未执行；
- 失败时的环境和影响；
- 外部服务、凭证或浏览器未覆盖的范围；
- 需要回读确认的最终状态、文件或协议结果。

`Passed` 只表示命令成功且结果已核对；`Not run` 必须说明原因。HTTP 200、任务完成提示、日志关键词、mock 调用次数和 Agent 自述都不能单独形成完成证据。

## 提交前检查

- 测试位于正确层级，且名称表达行为。
- 断言了业务结果和关键副作用，而不是只断言 HTTP 状态码。
- 新增 guard 有能恢复目标缺陷的负向案例。
- fixture 不依赖共享默认数据，测试数据会清理。
- skip 有明确的可选外部依赖或缺失环境变量原因。
- 真实 API、数据库、worker、文件、对象或浏览器语义已经按风险验证。
- expected output、fixture 和 snapshot 的更新经过人工审阅。
- PR 如实记录命令、结果和未验证范围。

相关规范：[参与贡献](./contributing.md)、[工程信任系统](./engineering-trust.md)、[Yuxi Spec Loop](./spec-loop.md)。
