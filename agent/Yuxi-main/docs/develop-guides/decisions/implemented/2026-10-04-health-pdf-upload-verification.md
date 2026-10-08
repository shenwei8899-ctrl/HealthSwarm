# 多页报告 PDF 上传链路验证

状态：implemented
类型：testing
Owner：backend/test/integration/services/test_health_vision_http.py

## 问题

多页 PDF 的页序、文档方向和处理坐标涉及 HTTP、PostgreSQL 元数据和 MinIO 字节三个边界。单页图片与处理器 unit 不拥有联合回读证据。本文面向后端贡献者和 Reviewer，目标是证明现有上传与预览契约，不调整云服务、正式数据留存或识别准确率。

## 决策

真实 HTTP fixture 生成无患者信息的三页 PDF，以红、绿、蓝的中心像素区分原始页序，分别带 0/90/270 度文档方向；原 PDF 左下固定位置的黑色标记区分非对称方向。上传接口应用固定人工旋转与去倾斜，回读原件字节、鉴权 PNG 和持久化的渲染源像素及仿射元数据。已知颜色、源宽高、画布尺寸、六系数常数及三个固定目标标记像素构成独立 oracle，不使用被测处理器生成期望值。陌生账号、管理员及匿名访问均有拒绝断言；业务删除后回读精确四个对象。

另经相同接口提交空页、超过 20 页、加密、损坏、饮食用途 PDF、过大页面和超过字节额度的输入；分别核对受控错误与零上传、零任务、零云同意记录。所有数据只属于本次唯一测试账号，测试不修改系统模型配置或调用供应商。

## 替代方案

只复跑处理器 unit 无法验证接口认证、原件响应或数据库绑定。开启真实 OCR 增加外发与费用，同时不能单独证明本地页序、坐标或删除。真实上传与对象回读覆盖本地数据边界，真实供应商效果由另获批准的样本测试负责。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 多页原件与处理 PNG 保持页序和方向 | 页交换、错误源坐标、原件被改写 | media service / upload service | shipping HTTP、PG、MinIO 回读；四色、固定标记/矩阵与尺寸 oracle | 文档方向混合、不同页颜色、声明 MIME 与实际内容不符 | Passed |
| 无授权访问不能下载 PDF 或任一页 | 管理员绕过成员授权、页号越界 | preview / repository | 真实认证请求与错误码 | 陌生账号、管理员、匿名、越界页 | Passed |
| 无效 PDF 不持久化有效文件或任务 | 超限继续渲染、隐藏成功 | upload service | HTTP 错误与 PG 零行 | 空页、超页数、加密、损坏、饮食用途、像素/字节超限 | Passed |
| 删除上传失效全部 PDF 副本 | 仅删原件、私有页仍可读 | delete_upload | 业务删除后 HTTP 404 与四个对象 stat 为空 | 删除后原件及三个处理页再次请求 | Passed |

`docker compose exec -T api timeout -k 5s 180s uv run --no-sync --group test pytest test/unit/services/test_health_vision.py test/unit/services/test_health_vision_protocol.py test/unit/services/test_health_ocr_resume.py test/unit/services/test_health_recipe_portions.py test/unit/services/test_health_report_reprocess.py test/unit/services/test_health_report_transforms.py test/integration/services/test_health_vision_http.py -q --tb=short --show-capture=no`：214 passed，29.73s，包含 205 项 unit 与 9 项真实 HTTP。新增的两项 PDF HTTP 验证原件、逐页 PNG、PostgreSQL 元数据、拒绝后的零行与删除后的四个 MinIO 对象。Ruff check / format 均 Passed。

全新独立 Reviewer 手算黑标几何、核对 HTTP 实际对象读取与精确清理，并以 `-k 'pdf'` 独立复跑：2 passed，7 deselected，7.99s，代码无未解决的 P1/P2/P3。`scripts/verify_engineering_contracts.py` Passed：117 decisions / 5 workflows / 4 AGENTS / 166 docs / 27 routers / 255 web sources；配套 unittest 62 passed。文档构建 Passed，23.08s；`git diff --check` Passed。

## 后果

该证据不证明 PDF 中的报告字段已被真实 OCR 提取，也不证明医学准确率、小程序身份签发、成本预算或生产留存批准。多页自动页序异常检测仍需实际困难样本；这里只核验上传既有页序。中心色块不区分相反文档方向，固定非对称标记与独立矩阵共同约束方向。报告处理变换的运行契约由[处理页旋转与去倾斜](2026-10-04-health-report-transforms.md)记录。
