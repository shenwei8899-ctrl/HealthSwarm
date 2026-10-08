# 健康 checkpoint 的原始投影一致性

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/repositories/health_family_profile_repository.py

## 问题

本人确认档案使用 Python 字典相等判断 checkpoint 正文，整数、同值浮点数与布尔值的 JSON 表示变化可保留旧摘要并通过。成员记忆历史只核对标识、版本及有效状态，同版本伪造正文或类型也可进入模型；账号内其他成员的记忆尚未在该边界按当前绑定校验。已确认报告、饮食和审核知识的 checkpoint 也只核对来源标识与有效性，未将收到的指标、营养和引用正文与原始事实比较。

## 决策

### 实现方案

档案 repository（`backend/package/yuxi/repositories/health_family_profile_repository.py`） 在查询真实线程使用回执前重新计算收到投影的摘要，并与当前服务器投影摘要一致。成员记忆 service（`backend/package/yuxi/services/health_memory_service.py`） 在模型输入过滤处，将有效引用绑定至当前咨询成员，并按 JSON 类型核对服务端公开投影中的全部正文、类型及来源标签。读取结果的外层只包含 `memories` 和布尔 `truncated`；写入结果只允许整数 `written_version` 和布尔 `replayed`，同请求替换只允许固定为真的 `superseded_by_same_request`。未知字段、顶层附加正文和错误状态的记忆工具消息返回 `memory_history_invalid`。同请求更新由真实修订收据决定，新版本替换后同样验证当前投影。撤回或外部改版继续排除旧轮次或拒绝当前轮次。

确认报告和饮食工具历史由 consultation service（`backend/package/yuxi/services/health_consultation_service.py`） 逐条使用 PostgreSQL 已确认记录重建原投影，审核知识 repository（`backend/package/yuxi/repositories/health_evidence_repository.py`） 根据真实引用归属及有效证据重建公开引用片段。审核证据的检索生产与历史验证共用公开片段投影。实际 `HealthAuthorizationMiddleware.abefore_model` 在模型调用前按 JSON 精确核对这些工具结果的全部公开正文和外层；附加正文、标志类型变化及错误状态消息返回 `source_invalidated`。确认状态、授权、来源有效期和内容摘要校验保留。

记忆、确认记录、审核证据、绑定和版本由 PostgreSQL 拥有，checkpoint 是待校验输入。修复保持既有 schema、普通接口、引用结构和持久化事实。

## 替代方案

仅核对标识和版本无法证明正文；仅采用 Python 相等无法区分 JSON 数值与布尔值。删除整个咨询历史会破坏已验证的同轮更新与对话恢复。复用现有摘要和公开投影可以在实际模型输入边界直接拒绝这些缺陷。

## 后果

历史不完整或被篡改的有效来源收据明确拒绝，错误工具正文不会再直接进入模型。真实工具产生的公开投影完整；合法读取、写入和同轮更新继续兼容。错误工具历史会终止当前咨询并要求重新提交，模型不能把任意失败正文作为健康事实继续推理。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 | 负向案例 | 结果 |
|---|---|---|---|---|---|
| 档案 JSON 内容匹配真实摘要 | checkpoint / 模型输入 | profile repository | publication unit（`backend/test/unit/services/test_health_family_profile_publication.py`）、HTTP/PG 来源（`backend/test/integration/services/test_health_family_profile_http.py`） | 原摘要保留，版本改为布尔或同值浮点数、档案浮点改为同值整数 | Passed |
| 记忆正文、类型和成员归属匹配真实事实 | checkpoint / 模型输入 | memory service | memory unit（`backend/test/unit/services/test_health_memory_daily.py`）、独立 HTTP/PG 读取（`backend/test/integration/services/test_health_memory_daily_http.py`） | active ID/version 保留，伪造正文、kind、来源标签、JSON 类型、其他成员、附加字段、错误状态 | Passed |
| 正版记忆与同轮更新、撤回行为保持 | 历史过滤 / 依赖提交 | memory service | memory unit 与独立 PG 正控 | 外部改版和撤回不能冒充同请求更新 | Passed；本轮未重跑既有每日入口全量 integration |
| 报告、饮食及引用正文匹配真实来源 | 实际模型调用前 checkpoint | consultation service、evidence repository | shipping middleware unit（`backend/test/unit/services/test_health_checkpoint_sources.py`）、独立 PostgreSQL 模型入口（`backend/test/integration/services/test_health_checkpoint_sources_http.py`） | 真实 ID 保留，伪造指标、营养、证据正文、record/顶层附加正文、旗标 JSON 类型和 error 状态；查询后独立回读原事实 | Passed |

档案与记忆的 13 个新增负控在修复前全部因 `DID NOT RAISE` 失败；实际 `abefore_model` 的报告、饮食和审核引用三个正文负控同样先因 `DID NOT RAISE` 失败。记忆实际 `awrap_model_call` 的合法读写正控到达模型 handler，附加字段及 error 负控以 `memory_history_invalid` 拒绝且 handler 未调用。

执行命令位于 Yuxi 项目目录，使用 API 容器现有 Python 运行环境：

```bash
docker compose exec -T api python -m pytest -p no:cacheprovider test/unit/services/test_health_family_profile_publication.py test/unit/services/test_health_memory_daily.py test/unit/services/test_health_checkpoint_sources.py test/unit/services/test_health_consultation.py -q
# 55 passed，85.06 秒
docker compose exec -T api python -m pytest -p no:cacheprovider test/integration/services/test_health_family_profile_http.py test/integration/services/test_health_memory_daily_http.py -q -k 'history_rechecks_profile_version or checkpoint_memory_projection'
# 2 passed，12 deselected，152.40 秒
docker compose exec -T api python -m pytest -p no:cacheprovider test/integration/services/test_health_checkpoint_sources_http.py -q
# 1 passed，110.62 秒
docker compose exec -T api python -m pytest -p no:cacheprovider test/unit/services/test_health_checkpoint_sources.py -q
# 最新模型入口负控 9 passed，50.51 秒；包括本人档案 error 状态的 service 入口
```

受影响五个生产文件和六个测试文件的 Ruff 检查通过。独立 PostgreSQL 模型入口测试仅隔离部署审批配置与模型缓存，真实成员用途权限、运行 lease、草稿确认状态、来源内容和引用生产／读取使用 PostgreSQL；该测试没有修改共享模型配置，也没有发出模型外呼。真实模型质量、生产资料迁移、全量 Worker E2E 和全 backend unit 不属于上述直接证据，单独由对应交付 gate 核对。
