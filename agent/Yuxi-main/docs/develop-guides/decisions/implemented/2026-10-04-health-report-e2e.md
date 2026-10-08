# 多页报告独立 worker 合成验收

状态：implemented
类型：testing
Owner：backend/test/e2e/test_health_report_e2e.py

## 问题

报告识图需要证明实际 PDF 私有上传、逐页 OCR 协议、字段模型、原文证据、失败页重新识别、版本复核及确认入档连接在 shipping HTTP 与独立 worker 上。局部执行器测试替换业务函数，不能证明外部认证、multipart、HTTPS 下载及页面归属的完整装配。本记录面向后台维护者；只校验合成数据流，真实供应商准确率、临床适用性和云处理批准不在本验收内。

## 决策

健康专用数据库、MinIO 和禁止外联网络复用现有隔离槽位，可选报告 Compose 覆盖层为 API 与 worker 挂载临时合成证书并指定信任文件。生产 TLS 校验保持启用。HTTPS 重放只接受人工定义的蓝、红两张纯色 PNG、固定 OCR 模型和脱敏后的固定指标块；假名及注入原文只出现在私有 OCR 原始结果。轮询要求合成 OCR 凭据，已登记的随机结果 receipt 下载不携带供应商凭据。

正式配置 API 临时审批合成端点；真实 PDF 上传生成两页私有处理图，独立 worker 处理第二页首次失败后由用户选择重识别。成功页人工修订保持不变，确认前正式指标为空，确认后回读 PG 指标、快照及两份原始对象。TLS 负控使用真实解析客户端，仅在测试 runner 临时改用公共 CA，必须拒绝合成证书且不创建外部 checkpoint 或成功协议事件。

## 替代方案

进程内 monkeypatch 解析器不能验证 multipart 和 TLS。允许结果下载 HTTP 或使用 verify=False 会改变真实信任边界。真实云 POC 仍需负责人批准供应商、数据及预算，不能替代零外联的确定性回归。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| PDF 两页经过实际协议生成带证据草稿 | 页丢失、图片未送达、字段绕过过滤 | report task / provider / private objects | 实际 HTTP、独立 Task lease、图片摘要、下载和字段协议、原始 JSON 回读 | 不同模型、图片、工具或身份内容拒绝；未同意零调用及无 Job | Passed |
| 失败页可选择重识别且不覆盖成功页修订 | 部分失败被当完整、页序或版本混淆 | reprocess / draft repository | 第二页新 OCR 标识、草稿 v3 和第一页日期回读 | 未解决失败页不能确认，旧版本确认拒绝 | Passed |
| 人工确认只追加一次当前成员指标 | 未确认入档、重复或跨成员读取 | confirmation / observation repository | 三次并发确认同响应，PG 恰好两条当前字段快照 | 未确认正式列表为空，陌生人和无授权管理员拒绝 | Passed |
| 合成验收维持隔离与 HTTPS 验证 | 启用原云环境或关闭 TLS | optional Compose / fixture | 真实解析客户端公共 CA 拒绝；普通槽位 skip；审批及 OCR 字段清空 | 不信任证书零 checkpoint、零成功事件；失败或残留 lease 保留诊断数据 | Passed |
| 终态清理包含重识别前的原始 receipt | 删除 Job 后旧对象失去归属 | health HTTP test fixture / MinIO | 本轮 Task 下尝试键和发布键删除后读回不存在 | 非终态、残留 owner/lease 不删；越出 Task 前缀的样本仍可读 | Passed |

报告、饮食、咨询与真实 HTTP 联合验收通过；合成槽位与 TLS 装配前置条件使普通槽位明确 skip。像素原文与归一化证据边界见[坐标验收决策](2026-10-04-health-report-coordinates.md)，HTML 表格行、内部列映射及联合结果见[表格验收决策](2026-10-04-health-report-tables.md)，精确命令由[测试规范](../../testing-guidelines.md#多页报告与健康链路联合合成-e2e)拥有。协议重放含 54 个独立正反例，独立 Reviewer 对实际装配、负控和清理边界复核。真实供应商质量和厂商兼容探针为 Not run，缺少获批的云供应商、样本与预算。

## 后果

证书和私钥只属于隔离槽位运行数据，不提交。测试 OCR 返回值来自合成常量，不能用于报告精度或 OCR 厂商兼容性承诺；真实服务仍需单独验证。重放控制使用专用合成凭据并严格限定输入，不接收用户报告，不外联。异常清理先取消本轮任务并等终态；不能收敛则保留 PG 与私有对象，合成审批关闭，原槽位配置不变。

通用配置更新是字段合并，fixture 显式清空 OCR 地址和占位凭据并从 PG 回读。终态测试资源清理收集本轮 Job 的全部尝试与已发布原始对象，只删除所属 Task 的结果前缀；重识别前的 receipt 不随 Job 删除留下孤立对象。测试构造任务状态直接修改当前事务的 TaskRecord，状态、owner 与 lease 在负控执行前从 PG 回读，避免只修改服务返回 DTO。
