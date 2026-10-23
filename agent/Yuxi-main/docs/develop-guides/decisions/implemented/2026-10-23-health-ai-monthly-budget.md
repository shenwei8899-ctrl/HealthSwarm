# 健康 AI 项目月预算

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_ai_budget_service.py

## 问题

所有账号的一般科普、三指标回顾、饮食解释、食物识别和报告识别共用人民币 40 元自然月额度。现有次数额度、执行时限和成功尝试 token 汇总不能阻止并发超支，也不能证明失败调用免费。

## 决策

PostgreSQL 保存不可变价格批准、月额度和逐次外呼账本；服务在外呼前锁定月额度并提交预留，供应商调用不持有数据库事务。月份按 Asia/Shanghai 的调用预留时刻确定。价格必须绑定实际处理端点和模型，包含有效期、核验依据及单次全部费用上界；未配置价格时拒绝付费调用，不填入虚构供应商价格。

健康 Agent 的共同模型 middleware、食物与报告字段模型及报告 OCR 提交使用同一预算服务。SDK 自动重试关闭。每个实际新尝试单独预留；同一调用标识重复请求不再次执行。OCR 已持久化任务的轮询不创建第二次提交费用。模型回执完整时按已批准的人民币单价结算；缺失、不一致、超界或异常保留全部预留。未决预留无自动释放期限，跨月结算仍归原月份。

管理员接口读取余额、未决账本并登记价格及一次性期初占用，不改变已有用途审批、成员授权或生产配置。启用当月已花费和未决费用必须先核对入账，重复登记不能清零。模型实例绑定预留的不可变配置，等待后检查配置及成员授权。工程在无外网的隔离 PostgreSQL 与合成供应商中验证；真实定价、凭据、处理政策和上线另行验收。

## 替代方案

只在请求入口计数不能覆盖模型工具循环及 OCR 多页。Redis 计数不拥有持久财务事实。调用后累计金额不能防止并发穿透；异常即释放不能证明供应商没有收费。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 所有用途共用 40 元 | 并发与重试 | 预算 service/repository | test_health_ai_budget_pg.py | 40 并发仅 4 个十元预留成功，重复标识拒绝 | Passed |
| 未知费用保留占用 | 超时、缺回执、重试 | 外呼账本 | PG 独立连接回读及 SDK 503 | 未知保留十元占用，自动重试只有一次请求 | Passed |
| 每轮外呼受控 | Agent/识图/OCR | middleware/provider | compiled agent、真实 SDK 合成 HTTP、OCR 恢复 | 换凭据或撤权零请求，恢复无第二次 POST | Passed |
| 增量建表保留旧事实 | Schema | PostgresManager | PG create_business_tables/create_health_tables | 重复执行不清空既有账本 | Passed |
| 管理接口及期初保护 | 权限、已有费用 | route/service | ASGI HTTP + 独立 PG | 普通账号 403，未确认期初拒绝，重复确认不能重置 | Passed |

定向命令：在独立 PostgreSQL 16 和 healthswarm-api:0.7.3 测试镜像中执行 `python -m pytest test/unit/services/test_health_ai_budget.py test/integration/services/test_health_ai_budget_pg.py -q --tb=short`，31 项通过。网络为 Docker internal，使用合成身份、金额和 HTTP 传输，无真实供应商请求。路由权限测试仅替代登录身份与模型配置来源，保留管理员依赖、业务服务、事务及数据库。编译 Agent 测试不等于完整 Worker/恢复 E2E，迁移测试不等于生产迁移。源码由独立 Reviewer 静态复审，发现的模型配置竞态与预留后授权竞态已修复并有负向回归。

## 管理与启用

- `POST /api/health/v1/budget/opening`：管理员提交 `occupied_cny`、核账 `evidence` 及 `verified:true`，当月已有支出和未决费用都计入。仅可初始化一次；相同内容重放不改变余额。
- `POST /api/health/v1/budget/prices`：管理员登记 `kind:model` 或 `kind:ocr`、CNY 价格、带时区的有效期、核验依据及 `upper_bound_verified:true`，模型价格绑定当前模型/端点/凭据，OCR 绑定端点/凭据。旧批准禁用但历史版本保留。
- 模型价格字段为 `model_spec`、`input_cny_per_million`、`output_cny_per_million`、`max_input_tokens`、`max_output_tokens`。输入上界须为供应商保证的硬上界，覆盖图片、历史、工具等所有计费用量；输出配置随请求发送。单价须覆盖缓存、推理、附加费与人民币结算口径。仅填 `upper_bound_verified` 不能替代真实核验。
- OCR 字段为 `ocr_endpoint`、`fixed_cny_per_page`，仅适用于单页固定计费且恢复查询/结果下载免费、无客户端透明重试的合同。不能确认费用上界的供应商不启用。
- `GET /api/health/v1/budget`：管理员读取当前北京时间月份、40 元限额、占用/剩余金额、初始化/冻结状态及最近 100 次调用。占用包括已结算与未决，不等同供应商正式账单。
- Schema 由 29 增量到 30；新表不自动登记价格/期初或启用用途。部署后仍需沿用用途模型审批、处理政策及成员同意。合成测试价格不得用于生产。

## 后果

费用硬限额依赖经过核验的供应商单次计费上界。缺少可信上界时停止调用；保守预留可能让可用预算低于实际余额。进程崩溃、取消或网络错误的预留不会自动释放，即使请求实际未到供应商也保守占用；本轮不提供未知账单的人工冲正入口。若用量超过批准上界，保留占用、冻结当月并禁用该价格，不能据此保证违规供应商已产生的金额。账本记录用量和运行标识，不保存健康正文、图片或凭据。只覆盖已确认的五类用途，配餐等其他角色不在本轮范围。生产定价与正式政策尚未登记，不启用生产用途。
