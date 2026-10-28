# 知识文档新增的全局身份与冲突隔离

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/knowledge/base.py

## 问题

知识文档的 `file_id` 是 PostgreSQL 的全局唯一键，同时被解析产物和 Chunk 引用。来源路径与时间生成的六位十六进制摘要只有 24 位空间；新增记录通过按 `file_id` 查找的 upsert 写入时，碰撞会将已有文档的归属、来源和解析元数据替换为新文档内容。

## 决策

新增文档使用 `file_` 加 UUID4 的 32 位十六进制表示，并由数据库唯一约束原子拒绝任何重复 ID。现存六位 ID 保持有效，无需迁移文档身份或引用。

### 实现方案

[元数据准备](https://github.com/xerrors/Yuxi/blob/main/backend/package/yuxi/knowledge/utils/kb_utils.py)的普通文件与预处理文件两个入口生成相同形式的长 ID。[文档新增](https://github.com/xerrors/Yuxi/blob/main/backend/package/yuxi/knowledge/base.py)将准备好的元数据交给 [repository 的 create](https://github.com/xerrors/Yuxi/blob/main/backend/package/yuxi/repositories/knowledge_file_repository.py)，在 owning transaction 中执行 INSERT 和 flush，提交完成后返回新增结果。唯一冲突由数据库抛出并回滚，已有文件和 Chunk 保持原值；文档添加 HTTP 入口沿用逐项失败响应，不自动换 ID 重试。

repository 的 upsert、update_fields 和任务拥有者检查保持原有更新语义，继续服务目录创建和解析、索引等合法更新。字段容量由 PostgreSQL 的 `String(64)` 与 Milvus 的 `file_id` 长度 100 约束，37 字符的新 ID 均可容纳。

## 替代方案

仅延长随机 ID 可以降低碰撞概率，仍缺少新增动作对已有身份的保护。先查询再写入存在并发窗口；在客户端串行、延时或改变文件名也不能替代全局唯一约束。将通用 upsert 改为只插入会破坏既有合法更新，因此新增动作使用独立 create。

## 后果

新增动作遇到身份冲突时显式失败，用户或任务可依据现有失败响应处理。提交失败之前上传的原始对象仍遵循既有对象生命周期，本决定不引入对象清理或自动恢复。已发生覆盖的数据需要独立核验与恢复，部署该修复不会自动还原历史记录。

## 验证

`test/unit/knowledge/test_kb_utils.py` 冻结旧时间与短摘要，覆盖普通及预处理入口的 32 次同名并发；旧实现两项均因只有一个 `file_aaaaaa` 失败，UUID 实现通过。相关元数据、大小回退及合法更新 unit 共 21 项通过。

隔离 Linux 运行时的后端全量 unit 共 4,822 项通过，无跳过，303 个测试文件完整覆盖。测试数据目录使用隔离可写路径；餐次来源测试替身补齐真实 `DietLog` 已有的 `version` 字段，正文篡改及来源失效断言保持不变。

`test/integration/services/test_knowledge_document_identity.py` 在隔离 Linux 实例及真实 PostgreSQL 上执行，9 项全部通过，无跳过。测试使用独立 Schema，断言同名并发新增得到独立记录、同库与跨库强制冲突保持文件全字段和 Chunk 全字段不变、同 ID 并发 INSERT 仅一个事务成功，以及六位和长 ID 的合法 upsert 与解析、索引状态更新。

其中 3 项通过实际 Uvicorn loopback HTTP、原有路由、管理器和 repository 执行文档添加，验证正常新增及同库、跨库冲突的逐项失败响应；认证使用合成依赖，Milvus 连接和 Redis 缓存隔离，因此不将这些用例计为真实 RBAC 或完整解析、索引链路验证。运行使用现网不可变镜像叠加三个修复文件，其余运行时代码保持；生产服务与业务数据未参与测试。
