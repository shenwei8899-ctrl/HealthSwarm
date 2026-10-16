# 实际记餐与指标回顾接口

供正式客户端和资料管理员对接。人工记餐、记录更正、指标事实统计和候选导入使用普通业务接口；进入咨询仍独立校验成员授权、模型配置和数据处理同意。健康 Schema 26 增加指标会话选择和候选批次，发布时沿用 storage-migrator。

## 实际记餐

`POST /api/health/v1/meal-recordings` 接收 `member_id`、UUID `client_request_id`、`meal` 和 `accept_incomplete`；`Idempotency-Key` 与请求 ID 一致。`meal` 沿用饮食输入，人工实际摄入要求每项明确个人可食克数或已发布份量参考，`share_ratio=1`。食物和菜谱引用已发布 ID，缺失营养保留未知，明确接受后才能保存。照片、位置和排除项不属于这个人工入口。

`POST /api/health/v1/family-meal-recordings` 接收 UUID `group_id` 和最多20个不同成员的单人输入，幂等头等于组 ID。每人独立事务与 `diet_edit` 授权；未吃者不提交。返回 `results` 的逐成员 `saved/failed`、记录 ID 或错误，允许部分成功。失败重试保留组 ID、成员请求 ID 和原始正文，只提交失败项；成功者不会再次建餐。服务使用组 ID 与成员生成稳定确认身份，同身份换正文返回409。

单人成功响应包含 `id`、`source_version`、`snapshot` 和 `replayed`。草稿、计算、确认和日记同事务提交；网络响应未知时原样重放。`GET /api/health/v1/members/{member_id}/diet-logs/{record_id}/detail` 读取当前版本。更正使用[既有版本接口](./health-diet-log-correction.md)。

正式 App 的账号页进入“记录实际饮食与更正”，选择成员、已发布菜谱及个人克数，一次提交实际吃过的成员。当前页面保留未确认请求以便重试；离开页面会清除私有输入，结果未知时应留在原页完成核对。保存并聊聊绑定保存响应中的记录 ID 和版本，通过既有反馈会话入口创建线程；导航或线程创建失败只恢复该线程，不重新记餐。模型和政策未就绪时保留已保存事实并展示服务未就绪。

服务端明确返回未保存时，可选择“修改未保存项”调整输入并用新请求提交；已成功成员保持锁定，不再次提交。请求结果未知或幂等冲突时保持原请求供核对。饮食列表按北京时间显示餐次日期。

## 指标事实回顾

`POST /api/health/v1/members/{member_id}/indicator-reviews/{kind}` 支持 `blood_glucose`、`blood_lipids`、`blood_pressure`。正文为 `start_date`、`end_date` 和可选 `records=[{record_id,version}]`，日期为北京时间闭区间，最多366天、100个不同记录。未选择记录时返回该范围最近100条及总数/截断标志；旧咨询默认近30天20条保持不变。

当前来源仍限本人健康成员及有效家庭实测关联，服务核对字段授权。显式记录必须同时满足成员、类别、日期和版本，变化返回409。原值、单位、时间、来源、ID及版本保留；血糖按条件分组，血压成对，血脂同条四项。`review` 独立返回程序统计、缺失背景和追问；无记录时统计为空。审核解释与引用当前为空且 `evidence_status=not_requested`，没有个体化建议。

指标任务入口的 `selection` 可携带同一选择，服务创建咨询时校验并持久化，历史和模型调用边界重读相同来源。App 和后台组件均支持日期/记录选择；进入 Agent 前的用途授权与正式引用检查继续生效。

## 候选营养资料导入

管理员调用 `POST /api/health/v1/nutrition-imports`，正文为 UUID `client_request_id`、`kind=food|recipe`、最多500行的 `rows`，正文上限1MB；幂等头与请求 ID 一致。食品营养使用每100克，能量 kcal、钠 mg、其余 g，缺失为 null。行结构复用现有食品/菜谱输入校验。

响应保留候选原文、规范化有效数据、逐行异常、批内重复和已发布版本冲突，以及待补来源/许可/版本/适用范围/专业审核事项。同键异参409，原样重放返回同批次；`GET /api/health/v1/nutrition-imports/{id}` 仅创建该批次的管理员可读。候选不写入正式食品或菜谱，`published_count=0`。后台“服务与食品数据”中的导入准备区域提供 JSON 输入与错误报告。分权审核、批量批准和真实数据运营交付另行验收。

## 验证范围

真实 HTTP/隔离 PostgreSQL 测试由 `backend/test/integration/services/test_health_independent_workflows_http.py` 覆盖并发幂等、逐人成败、权限、候选隔离和三类统计；更正与迁移见对应更正测试。App H5 与后台组件通过合成数据的浏览器操作及独立数据库结果核验。后台完整页面启动、生产发布、微信真机、真实模型和专业资料质量不由这些结果替代。
