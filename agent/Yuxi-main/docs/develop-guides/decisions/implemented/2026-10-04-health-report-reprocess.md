# 健康报告失败页重识别

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_vision_service.py

## 问题

部分失败草稿支持人工排除，但重识别仍需整份重新提交。成功页再次处理增加外发及费用；后台返回又需要保护用户已保存的修改和确认历史。本文供后端、前端及 Reviewer 验证选择页处理，不涵盖真实云准确率或上线审批。

## 决策

版本化失败页任务输入仅接受草稿 ID、严格正整数版本、唯一失败页索引与请求键；HTTP 入口要求匹配的 If-Match 与 Idempotency-Key。服务在现有 Task 创建事务内校验草稿、源文件、授权、同意、配置与额度，且同草稿仅允许一个活动重识别。新 Task 关联前一 attempt；worker 只下载并外发选择页，页码保持原全报告索引。每次外呼前重查草稿仍未确认且版本未变；最终 owning transaction 合并选择页候选与页状态，保留其他页及人工字段、修改和排除选择，增加草稿版本与审计修订。用户期间修改、确认或撤回均阻止迟到结果覆盖。选择页全部失败时原草稿保持不变；显式 retry 仍建立新 attempt，继承选择页和原版本，不自动与后续人工编辑合并。

发布 receipt 在每个成功 attempt 的私有 input_snapshot 记录所绑定结果对象和版本；清理以各 attempt 发布 receipt 保留原始结果，不从当前草稿指针猜测历史结果归属。未发布及失去租约的对象仍精确回收。已确认草稿不接受重识别。重新识别仍保留用户明确的排除决定，不自动恢复入档。

同请求重放返回既有 Task，草稿完成后版本变化不导致重复创建。已保存草稿、用途同意、服务就绪和当前权限共同决定页面按钮可用；未知响应保留请求键，页面轮询只更新列表，完成后用户重新打开草稿复核。本记录补充[逐页复核](2026-10-04-health-report-pages.md)；真实配置未启用时按钮禁用，人工复核和排除仍可使用。

## 替代方案

整份重跑重复外发成功页，且不能直接保留同一草稿的修订。每次生成独立草稿使用户自行拼接报告，缺少同草稿版本冲突语义。worker 自动合并最新编辑需要字段级冲突协议；本方案选择显式版本冲突与刷新，避免自动覆盖人工判断。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 只处理选中失败页且保留全局页序 | 重跑成功页、证据错页 | executor | 真实 PG、MinIO、协议替身 | 第二页、无效页、成功页、连续处理第三页 | Passed |
| 保留人工修改且版本化合并 | 后台覆盖新编辑或确认 | service、finish hook | 真实 PG 回读版本、修订与 Task | 编辑、确认、撤权、旧 lease、重复任务 | Passed |
| 同请求重放不新增 attempt | 网络不确定造成重复提交 | 创建事务、请求指纹 | PG 回读 Job 数、前端请求封装、真实 HTTP 拒绝边界 | 变更页集合、重复活动任务、失败后 retry | Passed；shipping 正向 202 Not run |
| 发布 receipt 保留历史原始结果且回收迟到对象 | 合并后原始 OCR 丢失 | result cleanup | MinIO 精确键回读 | 三个成功 attempt、旧快照、取消、失去 lease | Passed |
| 处理配置与 actor 隔离 | 沿用其他操作人或已过期配置的 checkpoint | 创建事务 | PG Job 快照与执行协议 | 处理方、模型、政策变化，跨 actor 的 submitted ID | Passed |
| 页按钮按保存、同意和服务状态可用 | 未授权外发、未保存修改丢失 | ReportReview、workbench | Vue unit、lint、build、实际 DOM | 未保存、确认快照、服务未配、未知响应 | Passed；当前截图 Not run |

执行命令与层级证据：`docker compose exec -T api uv run --no-sync --group test pytest test/unit/services/test_health_vision.py test/unit/services/test_health_vision_protocol.py test/unit/services/test_health_ocr_resume.py test/unit/services/test_health_recipe_portions.py test/unit/services/test_health_report_reprocess.py test/integration/services/test_health_vision_http.py -q`：102 项通过（96 单元、6 shipping HTTP），27.48 秒。`pytest test/integration/services/test_health_vision_executor.py test/integration/services/test_health_report_reprocess.py -q`：36 项通过，248.10 秒，其中重识别为扩展前的 9 组；独立扩展的 `pytest test/integration/services/test_health_report_reprocess.py -q`：14 项通过，105.50 秒。上述 pytest 均在同一 API 容器通过 `uv run --no-sync --group test` 执行，缓存目录使用临时路径。

前端 `node --test test/healthReportReview.test.js test/healthVisionView.test.js test/healthVision.test.js test/healthMealReview.test.js`：18 项通过；`pnpm --dir web run lint:check` 与 `pnpm --dir web run build` 通过，build 4.75 秒。Ruff、工程契约检查和其 62 项单元通过。独立 Reviewer 无剩余可确定 P1/P2/P3，并单独复跑选择页 unit 13 项通过。浏览器实际 DOM 验证侧栏位置、失败页按钮和未配置时禁用；截图接口无法捕获，不声称已有当前视觉验收。仅本次合成成员、草稿、两次上传和四个对象被精确清理，账号及配置保持不变。所有外部识别响应是明确合成协议替身。

## 后果

同一图片重新提交仍可能再次计费；同 actor、成员、上传页序及处理配置的在途 OCR 标识优先复用，无法承诺供应商计费 exactly-once。处理方、政策或模型已变化时拒绝重识别原草稿；更换处理方案须重新建任务和复核。已确认数据保持不可变，重识别不自动撤销人工排除。完整设计的其它未实现事项仍保持未完成。

真实云准确率、实样 POC 和上线审批为 Not run。shipping 云配置未启用，新入口正向 HTTP 202 及重复 202 为 Not run；真实 service 创建/执行、私有对象和数据库回读、真实 HTTP 拒绝边界及前端请求封装分别验证相应层级，不替代启用后的端到端云验收。当前执行额度按任务数限制，货币费用预算仍需后续实现。
