# 健康报告 OCR 任务恢复

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/health_vision_tasks.py

## 问题

报告任务持久化外部 OCR 标识，却没有在恢复或显式重试时读取它。已上传并提交的页因此可能再次提交，增加重复外发和计费风险。外部标识来自不可信供应商响应，不能直接拼接任意路径。

## 决策

报告页 checkpoint 绑定上传 ID、原页序、处理页序、供应商任务 ID 与是否已明确失败。当前 attempt 及显式重试仅复用同账号、同成员、同文件、同处理方、政策及模型的 checkpoint。恢复时只轮询原任务，不再次 POST；明确失败的页允许显式重试新建供应商任务。查不到或过期的供应商任务显式失败，不自动创建第二个付费请求。checkpoint 写入仍属于有效 lease 的短事务，并再次验证成员授权与用途同意。

供应商适配器在每次 POST、轮询 GET 及结果下载之前检查取消、租约并执行必传授权回调。执行器回调在短 PostgreSQL 事务中检查当前 grant、用途同意、源文件及政策，事务结束后才外呼；pending 或 done 响应期间的撤回和失去执行归属会停止下一步访问。此决定补充[健康识图工作台](2026-10-04-health-vision-workbench.md)的报告执行恢复语义，不把报告输入到普通聊天或记忆。

## 替代方案

始终重新上传无法利用持久化标识。由客户端提供外部 ID 缺少页归属与处理方依据。保存完整 OCR 响应缓存需要额外私有对象生命周期；本范围只复用供应商任务，不缓存模型结果。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 恢复页不重复上传 | 已计费页重复 POST | provider、页 checkpoint | HTTP 协议回放、真实 PG 执行器 | 任务不存在、失效 ID | Passed |
| 页归属及处理同意保持 | 跨页或变更处理方复用 | task service、executor | 独立绑定 oracle、真实 PG | 变更政策、错页、撤权、明确失败页 | Passed |
| 供应商标识不能改变请求路径 | 外部响应任意 URL | provider parser | 协议负向测试 | 路径、查询、过长 ID、非字符串 ID | Passed |
| 撤回与旧 lease 阻止下一次外部请求 | 持续轮询或下载撤回后的健康结果 | 必传授权回调、TaskContext、repository | 真实 PG 与真实 provider 的 HTTP 回放 | pending 后撤回 grant、用途同意；done 后 lease 过期 | Passed |

`test_health_ocr_resume.py` 与 `test_health_vision_protocol.py` 合计 39 项通过，使用合成 HTTP 协议回放。`test_health_vision_executor.py` 完整执行 22 项通过、耗时 142.48 秒，包含真实 PostgreSQL 重试快照回读、MinIO 回收及撤回/租约中断；真实 HTTP 业务回归 4 项通过。独立 Reviewer 复测初始授权拒绝及三个真实 PostgreSQL 中断场景 4 项通过、已有供应商主路径 4 项通过，复核范围无剩余 P1/P2。HTTP 回放只证明协议与执行边界，不证明真实 OCR 准确率。真实云服务与计费为 Not run。

## 后果

供应商接受请求后、checkpoint 提交前仍存在无法证明是否计费的网络窗口，不能承诺 exactly-once 外部计费。模型调用和真实 OCR 到期策略未验证；所有回放只证明协议行为，不证明实样识别效果。旧无页归属 checkpoint 不复用。
