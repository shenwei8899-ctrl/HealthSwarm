# 健康报告与饮食识图工作台

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_vision_service.py

## 问题

家庭营养后台需要在数据总览下方提供识图入口。用户需要私有上传报告或同餐照片，复核识别结果后形成可重读的指标或饮食日记。现有平台只有知识库解析与聊天附件，不能把个人健康资料投入公共知识库，也不能把模型猜测当成营养数据。

## 决策

新增登录用户可用的健康识图工作台和 `/api/health/v1` 薄路由。业务持久化、授权和确认分别由 health repository、service 与 PostgreSQL 约束拥有；任务复用 Durable Task 的 lease 与 success/failure hooks，先提交再投递。health schema 由 storage-migrator 幂等创建。菜单位于数据总览之后、最近会话之前。

报告保留页码、证据和原始候选，人工修改与确认分离；照片只识别食物候选，份量及个人比例由用户确认，营养使用经管理员录入的带来源与许可的食品版本和 Decimal 确定性计算。[食谱与份量计算](2026-10-04-health-recipe-portions.md)拥有配方净成品重、碗勺参考和油糖调整的当前语义与证据。未配置供应商时保留手工录入路径，明确说明无法自动识别。当前交付不包含小程序验签、商城迁移、医学建议或自动配餐计划，也不凭空导入未授权食品数据。

成员初始授权只授予建档账号。其他账号需要成员授权记录，后台管理员角色本身不授予报告访问权。云处理默认关闭；管理员显式选择已配置的固定模型、批准处理政策和限额后，用户按成员及用途同意才允许外呼。供应商契约通过确定性协议测试验证；真实模型效果和商用数据授权仍需负责人确认。通用任务管理不得成为健康任务越权读取或取消入口。

处理方审批绑定实际端点和请求配置，不只绑定显示名称。OCR 后只向字段模型发送以已支持指标名及数值开头的指标行，分块身份值和无法证明属于指标行的文本不外发；原始 OCR 在私有对象保存，无法自动提取的指标走人工复核。解析结果对象在上传前持久登记归属，任务结束后清理未绑定对象；标记删除的原图及页由周期调度重试精确键删除。此恢复过程接受短期物理删除延迟，逻辑访问立即失效。

## 替代方案

直接在聊天页发送图片会混淆候选和正式数据，难以保证原文证据及版本确认。单独建立后台队列会复制已有恢复与租约机制。只做静态页面无法向小程序提供可用业务接口。这些方案不采用。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 指定位置出现识图入口，刷新恢复工作台 | 仅静态占位 | web layout、router、HealthVisionView | `pnpm lint:check`、`pnpm build`、healthVision 两个 test 文件，浏览器回读菜单、报告、饮食及配置页面 | 在途响应和确认期间切换标签、食品查询参数 | lint/build 和专属前端 6 项通过，真实页面通过 |
| 私有文件及结果按成员授权隔离 | 管理员或跨成员绕过 | health repository、私有 MinIO、HTTP 依赖 | `pytest test/integration/services/test_health_vision_http.py`，PG 与对象回读 | 双账号、管理员、撤回、匿名对象、通用任务绕过 | 真实 HTTP 3 个业务链路通过 |
| 异步候选仅由当前任务 owner 提交 | 取消或过期 worker 迟到写入 | Durable Task success hook | `test_health_vision_executor.py`、`test_durable_task_repository.py`，PG/MinIO 回读 | 取消、撤权、旧 lease、删源、存储删除失败后重试、健康任务并发上限 | 实际 worker 无同意拒绝通过；独立 Schema 报告和饮食各 6 情形，共 12 项及 durable 20 项通过；外部 OCR / 模型响应为合成替身 |
| 确认一次入档且旧版本拒绝 | 并发重复、草稿自动入档 | 草稿行锁、confirmation 唯一约束 | 同上 HTTP integration 回读正式记录 | 并发重放、异载荷、改量后旧计算 | 通过 |
| 营养计算缺失不当零且有来源版本 | 模型热量、未知食用比例 | nutrition calculator、food record | `pytest test/unit/services/test_health_vision.py`，独立手算与 HTTP | 空数据、缺营养、无比例、非有限数 | 核心 20 项通过 |

迁移与 schema 单元 30 项通过；重新执行 storage-migrator 退出 0，API readiness HTTP 200。`ruff check` 健康功能范围通过。供应商 HTTP 协议 replay 与分块身份脱敏 15 项通过，使用合成内容；它们验证请求/结果契约，不代表真实识别准确率。工程契约验证与脚本单元 62 项通过，docs build 通过。完整后端 unit 在既有 worker 测试长时间停滞后中止，结果为 1751 passed、54 skipped；完整前端 unit 在既有 subagentThreadLifecycle 测试长时间停滞后中止，为 297 passed、10 cancelled。这两次中止不能视为完整回归通过，取消也不作为业务断言失败；专属及相关测试另行完整执行。

受影响的 Tasker / registry 单元另行完整执行 18 项通过。验证运行槽位为 HealthSwarm 本地实例，Web 15173、API 15050，不触碰占用默认端口的其他项目。Windows 挂载造成 ARQ 探针导入超过原 10 秒，而 worker 心跳及业务任务正常；本地忽略目录下 `docker/volumes/health-vision-verification/local-healthcheck.yml` 只把 worker 探针超时调到 60 秒、间隔调到 30 秒，仍检查原 ARQ 健康契约。重建本地 worker 时使用 `docker compose -f docker-compose.yml -f docker/volumes/health-vision-verification/local-healthcheck.yml up -d --no-deps worker`；此运行环境调整不改变仓库的生产 Compose 默认值。

## 后果

无供应商凭据时无法验证真实识别效果、时延和账单；协议回放不冒充实测。没有获授权食品与食谱数据时营养结果保持不可计算或部分已知。云端处理合同、跨账号成人授权签发及生产预算由团队审批；工作台的建档与同意操作不能替代法律授权。部署迁移只作用于当前 HealthSwarm 槽位，保留已有平台数据。
