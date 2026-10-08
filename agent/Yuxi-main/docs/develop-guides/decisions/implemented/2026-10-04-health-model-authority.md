# 健康外呼核对持久模型配置

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/health_vision_service.py

## 问题

面向健康接口维护者。排队任务已获得成员授权与用途同意后，供应商停用、模型移除或凭据清除必须阻止后续外呼。仅依据进程 TTL 或发布失败后保留的 Redis 投影授权，数据库撤销就无法阻止后续外呼。[显式刷新决定](./2026-10-04-health-provider-cache-refresh.md)只覆盖 Redis 读取，数据库是配置事实 Owner。范围限定于健康处理边界，不调整通用队列、模型消费者、数据库 schema 或云质量验收。

## 决策

健康配置探测、审批与 worker 外呼检查读取当前 PostgreSQL 供应商记录，并与显式刷新的运行时模型投影核对。共享同一个供应商到 ModelInfo 的映射，避免端点覆盖、凭据与请求参数出现两种解释。停用、缺少凭据、非兼容聊天类型、缺少模型或投影不同均拒绝使用。实际外呼仍在短事务退出后发生。

咨询 middleware 绑定构图时实际使用的 ModelInfo，每轮重查授权后拒绝与新投影不同的旧实例。报告提交、轮询和下载重查时核对实际 OCR kwargs；非空凭据轮换也会停止沿用旧参数。这些绑定只存在于运行内存，凭据不进入公开 processor、健康快照、日志或响应。凭据轮换不改变用途同意的公开指纹，新任务可在投影同步后使用新凭据，旧实例停止。

## 替代方案

仅刷新 Redis 可以消除本地 TTL，但无法识别数据库提交后投影发布失败。让健康模块静默重建全部 Redis 投影扩大写入与恢复职责。改动全部模型加载者会扩大与健康功能无关的兼容面。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| worker 不沿用旧进程投影 | 停用后仍外呼 | health tasks / model cache | freshness unit 31 项；相关 unit 69 项 | 预热后移除模型、改端点或 Redis 故障 | Passed |
| 数据库撤销覆盖旧 Redis | 发布失败后仍可审批或执行 | health service / provider repository | 真实 PG executor 31 项；健康联合 E2E / HTTP / unit 93 项 | 数据库停用、清空凭据、改端点或类型，保留旧投影 | Passed |
| 实际实例参数参与外呼核对 | 新投影通过检查，旧实例继续请求 | health consultation graph / health tasks | 真实模型构造单测与独立无外呼探针 | PG 与投影同步后，旧模型或 OCR kwargs 必须拒绝 | Passed |
| 正常审批与执行继续可用 | 共用映射或事务变更破坏识图与咨询 | health service / provider cache | 模型缓存 unit；报告、饮食、咨询联合 E2E | 端点覆盖及字段请求的独立 oracle | Passed |

相关 unit 69 passed，26.35 秒；独立 Reviewer 复跑 69 passed，21.78 秒。真实 PG executor 31 passed，223.62 秒；独立 worker 联合验证 93 passed，114.61 秒。运行命令及隔离前置由[测试规范](../../testing-guidelines.md#健康模型配置撤销验证)维护。

扩大报告、坐标、变换、重识别、OCR 恢复、份量与咨询相关回归：359 passed、1 skipped，69.54 秒。skip 是普通槽位未装配专用 TLS / 合成隔离的报告 E2E；该报告链路在上述专用 worker 联合验证中通过。

独立进程内负控将 PG 核对替换为仅缓存读取，8 条回归因 `DID NOT RAISE` 变红；分别删除 OCR 参数绑定和咨询实例比较，2 条新回归同样变红。旧实例探针使用真实模型构造与真实报告调用适配，HTTP transport 完全拦截；修复后在进入 transport 前拒绝。生产源码未为负控改写。

排队负向 E2E 在同一 PG 事务提交供应商改动与旧 Task / VisionJob 快照，再通过真实 ARQ 发布。正向识图仍从 HTTP 上传、同意和任务入口经过独立 worker。负向用例回读旧 Redis 仍存在、HTTP 关闭能力并拒绝再次审批、Task 失败且 lease 清空、成员无草稿及日记、本地重放调用列表不增加。错误代码等待最终投影收敛；任务进度阶段保留实际拒绝位置，不把它误当成 Task 终态。

## 后果

每次健康边界新增供应商数据库读取，投影不可读或与数据库不一致时明确关闭能力，需要管理侧恢复发布。现有咨询实例与 OCR 参数轮换触发 `policy_changed`，用户需要重新提交或重试。核对后的并发撤销不承诺中断已发出的请求。真实云、临床字典与识别质量尚未验收，合成验证不构成真实云处理批准。
