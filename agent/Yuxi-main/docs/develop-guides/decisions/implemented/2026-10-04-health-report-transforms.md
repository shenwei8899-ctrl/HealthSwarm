# 健康报告处理页旋转与去倾斜

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_media_service.py

## 问题

侧拍、镜像 EXIF 或方向不正确的报告需要可核验的处理副本，并保留原件作为复核依据。角度与处理页之间的坐标关系影响证据定位；处理参数、原件和处理副本需要明确的所有权。本文供 API、上传页面和 Reviewer 核验私有处理页，不解释临床准确率或云服务审批。

## 决策

上传接口接受报告用途的顺时针 0/90/180/270 度旋转与 -10 至 10 度人工倾斜校正，不自动判断倾斜角。原始上传字节、摘要和私有权限保持不变，处理副本先纠正 EXIF 再应用用户角度；扩大画布、不裁切，空白使用白色。存储源坐标空间、源宽高、EXIF 方向、用户角度与六系数源到处理页仿射矩阵。图像源为编码图像像素；PDF 源为既有文档方向、2 倍渲染页像素，明确不把它冒充 PDF 点坐标。证据 bbox 和鉴权预览继续使用相同处理页。

参数在 DTO / service 信任边界验证；饮食上传拒绝非零报告变换。已有页快照缺少变换字段时保持可读。草稿的页面元数据仍由服务端拥有，人工编辑不能改变变换或证据所属页。上传参数固定于私有文件，重识别复用同一处理副本。界面在上传前选择角度，上传后鉴权预览处理页；预处理不签署云处理同意，也不创建识别任务。已上传文件锁定参数，重新选择同一文件可调整角度生成另一副本；未提交任务的迟到上传尝试清理，权限不足或删除失败时不回填视图、不创建云任务，私有文件仍留存。迟到预览不展示到另一成员。

## 替代方案

前端直接改原文件会丢失服务器可核验的原始字节和处理版本。自动判断方向或倾斜需要困难样本验证，不能用未经校准的阈值代替。仅存角度不足以定位镜像 EXIF 与扩展画布的平移；保存明确源坐标空间和仿射矩阵使转换可重算。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| EXIF 与人工变换保持原始字节且坐标可重算 | 方向或矩阵错误、裁切 | media service | `test_health_report_transforms.py` 的独立角点/颜色与 PDF oracle、`test_health_vision_http.py` 的真实私有对象回读 | 八种 EXIF、正负校正、90/180/270、尺寸超限 | Passed；包括多页 PDF shipping HTTP / PostgreSQL / MinIO |
| 受控上传参数不影响饮食或隐私边界 | 任意参数、跨成员读取 | upload service、HTTP | DTO unit、shipping HTTP / PostgreSQL / MinIO | 非有限、超限角度、饮食用途、无授权 | Passed |
| 同一处理页贯穿预览、Task 和复核 | OCR 页和 UI 坐标分离 | executor、ReportPage | shipping HTTP 回读页元数据与对象；executor / 重识别源码审查 | 篡改矩阵、旧页默认字段 | HTTP Passed，执行器装配 Inspected；真实 OCR Not run |
| 上传前调整与预览不发起云调用 | 自动收费、参数未知 | upload workbench | `healthVisionView.test.js` 的真实 Vue 脚本状态、实际 DOM 与合成 PNG 弹窗截图、lint/build | 云配置关闭、切换成员、迟到上传/预览、同文件重选 | unit / 实际上传与预览 DOM Passed |

`docker compose exec -T api timeout -k 5s 180s uv run --no-sync --group test pytest test/unit/services/test_health_report_transforms.py test/unit/services/test_health_vision.py test/unit/services/test_health_vision_protocol.py test/unit/services/test_health_ocr_resume.py test/unit/services/test_health_recipe_portions.py test/unit/services/test_health_report_reprocess.py test/integration/services/test_health_vision_http.py -q --tb=short --show-capture=no`：212 passed，34.59s。其中 109 项变换 unit 与 7 项 shipping HTTP；HTTP 回读原件、处理 PNG、页矩阵、空任务和空云同意记录。

`docker compose exec -T web node --test test/healthVisionView.test.js test/healthVision.test.js test/healthReportReview.test.js test/healthMealReview.test.js`：22 passed，392.92ms。`pnpm run lint:check` 与 `pnpm run build` 均 Passed，最终前端构建 12.24s。用户明确批准后，实际浏览器上传 1200×1600 的非医疗合成图，先按 90 / -2.5 度预览，原生重新选择同一文件后按 270 / +2.5 度再预览；两次 PNG 均已加载为 1651×1269，画布边框完整、象限位置符合方向，上传后参数禁用、重新选择后启用。截图保留在本地验证产物中。

本地真实 PostgreSQL / MinIO 回读两份原件字节完全一致、两个处理页的方向及矩阵元数据、PNG 尺寸与无 EXIF；合成成员没有 Task、草稿或云处理同意。使用业务删除入口清理这两份测试上传，再删除精确合成成员及关联行，四个对象的 stat 均为空。浏览器重新加载后返回无成员、无任务空态，账号和服务配置保留。该联调不调用真实 OCR 或模型。

`docker compose exec -T api timeout -k 5s 420s uv run --no-sync --group test pytest test/integration/services/test_health_vision_executor.py test/integration/services/test_health_report_reprocess.py -q --tb=short --show-capture=no`：41 passed，281.50s。真实 PostgreSQL / MinIO 回读任务、草稿、重识别和原始结果；供应商仅使用合成替身，不证明真实 OCR 成功。

全新独立 Reviewer 复核像素/坐标探针、带文档方向的 PDF、两项独立 shipping HTTP 与页面脚本测试，无未解决的 P1/P2/P3。真实 OCR、模型费用和医学准确率未执行，云服务保持关闭且没有真实患者样本外发批准。多页 PDF 的真实上传、渲染方向、原件与处理 PNG、鉴权、无效输入和精确删除已由[PDF 上传链路验证](2026-10-04-health-pdf-upload-verification.md)提供 HTTP / PostgreSQL / MinIO 证据；该记录不扩张真实 OCR 与临床验收范围。

## 后果

人工角度不证明报告可识别；模糊、截断、反光和页序自动检测仍需后续样本验证。PDF 点坐标转换不在此像素变换契约中。扩展画布仍受像素及处理文件大小限制。用户重新选择文件不会删除先前的私有上传；原件留存与自动清理周期需要明确隐私政策，不能为清理未绑定副本误删已提交或已确认的来源。真实云与生产留存批准保持未完成。
