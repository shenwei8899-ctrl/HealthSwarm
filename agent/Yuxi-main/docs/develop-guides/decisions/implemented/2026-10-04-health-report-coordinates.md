# 报告 OCR 像素证据坐标

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/health_vision_provider.py

## 问题

报告复核需要将供应商内容块定位到同一份私有处理页。PaddleOCR-VL 的结构化结果使用像素边框，并提供输入宽高和预处理设置；只接受 0 到 1 的值会舍弃常见有效框，也会将靠近原点的一个像素框误当成覆盖整页的归一化框。本记录供报告适配器与复核维护者使用，不证明厂商云端兼容或临床精度。

## 决策

适配器按 PaddleOCR-VL 的像素协议处理 `block_bbox`，不根据数值大小猜测坐标单位。一条结果仅包含一份页面布局；输入整型宽高严格匹配当前处理页；`use_doc_preprocessor` 为布尔 false 且 `doc_preprocessor_res` 键缺失；来源页码为空或本次单图的 0、页数为空或 1。满足这些条件后，有序、非空、有限且未越出图像边界的像素框按横纵宽高分别归一化。缺失或不一致信息、非法框保留文本和块 ID，bbox 为 null。既有已保存的归一化证据不重写。

私有 OCR 原文保留像素框和来源元数据；字段模型与复核页使用归一化结果。报告 HTTPS 重放返回独立定义的 1200×1600 输入元数据和像素框，经真实 worker 转换后，字段协议、草稿和正式快照分别回读为预定 0 到 1 框。上传旋转和去倾斜仍由[处理页变换](2026-10-04-health-report-transforms.md)的现有 Owner 负责；供应商缺少明确无预处理声明时使用整页定位。

## 替代方案

所有框继续置空会丢失可校验的复核能力。按最大坐标是否大于 1 推断单位，会把一个像素区域错误放大。仅凭页尺寸换算不能排除 180 度旋转或相同尺寸的形变；必须核对预处理声明。引入供应商坐标选项会增加用户可配置协议与新审批表面，本适配器维持固定协议。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 可验证像素框映射到同一处理页 | 丢框、一个像素放大、横纵尺寸混用 | normalize_report_blocks | 人工独立矩形与非方形尺寸 oracle | 一个像素及小于一个像素的框均按页尺寸缩放 | Passed |
| 未知或矛盾坐标不伪造定位 | 错页、旋转、尺寸或框非法 | OCR 解析边界 | 保留相同原文及 ID，bbox null | 缺元数据、尺寸不符、多页面、预处理键任意值、布尔值、非有限、越界及零面积 | Passed |
| 像素原文、规范证据及入档一致 | 仅 helper 通过、模型和页面消费另一份框 | report HTTPS replay / worker / PG | 两页 PDF 的像素原始对象、归一化字段协议、草稿及确认快照 | 未同意无 Job、失败页未解决不能确认、跨账号拒绝 | Passed |

独立 Reviewer 执行 `docker compose exec -T api uv run --no-sync --group test pytest test/unit/services/test_health_report_coordinates.py -q --tb=short -p no:cacheprovider`：47 passed，3.67s。仅在独立测试进程内将 y 轴非空条件放宽，零高度负控失败；恢复 truthiness 判断时，空 dict、list、false、0、空字符串和 null 六项负控失败。最终源码复核没有未解决的 Review 问题。

报告、饮食、咨询、协议、坐标和真实 HTTP 联合验收通过，扩展 HTML 表格后的联合结果见[表格验收决策](2026-10-04-health-report-tables.md)。原开发槽位明确跳过需要合成隔离与 TLS 装配的 E2E；准确命令由[测试规范](../../testing-guidelines.md#多页报告与健康链路联合合成-e2e)拥有。云供应商契约和 OCR 精度为 Not run，需要获批供应商、样本与预算。

## 后果

官方开源结果不能替代具体云供应商契约探针；云结果若省略尺寸或预处理声明，使用整页定位。返回归一化 `block_bbox` 的非标准端点需要自己的批准协议，不能以默认 fallback 混用。仅有整块坐标仍定位整块，不表示字段级框。私有页宽高、权限和人工修订沿用当前服务端 Owner，不改 Schema，不重写历史指标。

来源为 [PaddleX 3.7 结构化结果](https://paddlepaddle.github.io/PaddleX/3.7/pipeline_usage/tutorials/ocr_pipelines/PaddleOCR-VL.html) 与[结果序列化源码](https://github.com/PaddlePaddle/PaddleX/blob/release/3.7/paddlex/inference/pipelines/paddleocr_vl/result.py)。
