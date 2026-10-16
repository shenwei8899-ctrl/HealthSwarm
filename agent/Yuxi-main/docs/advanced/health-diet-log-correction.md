# 更正已确认饮食记录

供客户端集成者使用。已登录账号需持有成员当前 `diet_edit` 授权，原识图来源也须有效。接口只做确定性计算，不需要模型或 AI 用途审批。正式 App 的实际饮食记录页提供克数更正、版本冲突重读与原键重试；生产迁移和发布仍待验收。

## 提交更正

先从[饮食列表](./health-diet-log-pagination.md)取得记录 `id`、`source_version` 和当前 `snapshot.meal`，调用 `PATCH /api/health/v1/diet-logs/{id}`。正文包含 `expected_version`、UUID `client_request_id`、更正原因 `reason`、完整 `meal`，以及是否明确接受缺失营养的 `accept_incomplete`。同时传 `If-Match: "<expected_version>"`（包含双引号）及与请求 ID 相同的 `Idempotency-Key`。

`meal` 沿用现有草稿输入类型，仅提交食物映射、进食时间和实际份量。照片来源及模型位置必须与原始识别一致；新增人工食物不得伪造位置。不能提交营养总数。具体字段由 `backend/package/yuxi/services/health_diet_correction_types.py` 与 `backend/server/routers/health_vision_router.py` 维护。

成功返回同一 `id`、递增后的 `source_version`、`status=recalculated`、当前 `snapshot` 和即时单餐事实 `analysis`。服务在同一事务内保存新计算、不可变修订、当前快照和反馈失效状态。旧草稿、原确认及旧计算保留。新计算的 `draft_id/draft_version` 表示原确认来源，当前业务版本由 DietLog 和 DietLogRevision 拥有。

版本冲突返回409 `version_conflict`，刷新记录后由用户重新核对修改。网络结果未知时原样重试原幂等键；重复提交不再递增。旧请求在后续更正后重放，`applied_version` 表示当时提交的版本，`source_version` 与结果始终是现在的版本；客户端不能用旧本地快照覆盖响应。同键不同内容返回409 `idempotency_conflict`。

计算存在缺失且没有明确接受时返回422 `nutrition_incomplete`；计算或提交失败全部回滚，原事实仍是有效当前版本，没有发布半成品。页面应保留编辑输入并提示本次未保存。服务同步计算，没有后台重算队列或需要轮询的处理中状态。

## 旧结果与修订历史

所有账号在该餐次上的有效反馈变为 `invalidated` 并递增反馈版本，当前反馈正文为空。再次填写需要刷新后的反馈版本和新请求 ID。旧单餐、周期分析和选餐反馈会话不能沿用旧来源版本；普通咨询的历史、摘要及模型调用边界也核对饮食工具来源，旧建议不能继续充当当前结果。只支持通用事实重新计算，AI 建议不会自动重新生成。

`GET /api/health/v1/diet-logs/{id}/revisions` 返回不可变审计快照；首次更正时归档原确认快照，其后追加每次更正。尚未更正的记录修订列表为空，当前快照仍从饮食列表读取。历史数据仅供追溯，不能作为当前分析来源。权限撤回返回404，原图删除或原确认来源失效返回410；成功响应禁止缓存。

## 发布与验收边界

健康 Schema 25 增加记录版本和修订表。正式迁移使用项目既有 storage-migrator 流程；升级前停写并备份数据库，API 与 Worker 使用同版代码。旧记录按原确认版本初始化，重复迁移不重置已更正版本；空版本仅兼容历史写入，读取时回退原确认版本。

更正后的数据库不可交给不识别记录版本的旧 API 写入。回滚需要恢复升级前备份并处理升级后的新增业务事实，不能只回滚镜像。生产发布还需保留现有身份整合代码并完成备份验证。

隔离验证入口：`backend/test/integration/services/test_health_diet_correction_http.py`，覆盖真实 TCP、认证、PG 事务、并发、升级、历史失效。正式 App H5 已通过合成数据的真实 HTTP 保存及独立 PG 核验；生产与真实模型尚未验收。
