# 日常参考配餐优先召回完整烹饪资料

状态：proposed
类型：bug-fix
Owner：backend/package/yuxi/services/reference_meal_plan_service.py

## 问题

日常参考配餐的标题检索只要有命中就跳过其余召回。目录和疾病食养资料可占满结果，完整烹饪文档正文中的食材和做法无法被找到；提示词只允许换一次关键词，导致普通已建档用户无法保存三餐。

## 提案

### 实现方案

实现代码与回归用例已落地，发布与真实链路验收仍待完成，状态保留 proposed。服务保留成员授权、固定知识库和当前 Run 回执，先查完整烹饪与 USDA 家庭菜谱的标题，再用同类文档正文补充候选。每个文件仅返回首个实际命中分片，结果最多四项；没有普通菜谱命中时使用既有语义检索 Owner。模型读取实际分片后，按照明确偏好尝试替代菜谱，保存仍逐字核验菜名、食材和步骤。服务不新增数据库或配置，也不修改专业批准、营养计算或保存权限。

## 替代方案

保留任意标题命中短路会重现目录抢占；仅增加结果数会继续消耗预算读取无做法资料。直接放宽引文和偏好要求会产生无法核对或不符合档案的结果，故不采用。

## 验收标准

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 完整普通菜谱优于目录和疾病资料 | 目录标题占满候选 | search_reference_recipes | 真实 PG 检索 integration | 目录命中而普通菜谱仅正文命中 | Passed |
| 同一文档仅返回一个实际命中分片 | 长文重复候选 | search_reference_recipes | 真实 PG 检索 integration | 多分片同词占满结果 | Passed |
| 固定库、当前 Run 和引文边界保留 | 来源伪造 | read_reference_recipe / checked_reference_meals | 相关 unit 与 integration | 未检索读取及伪造引文继续被拒绝 | Passed |
| 真实用户流程完成保存与单餐调整 | 模型未保存 | Worker / daily plan service | 普通合成档案真实 E2E 与回读 | 不以问题正文或 completed 状态替代保存事实 | Not run |

候选镜像已实际执行 `pytest test/unit -m "not slow"`：5294 passed，收集错误和跳过均为零。真实隔离 PostgreSQL 上执行 `pytest test/integration/services/test_reference_meal_plan_http.py test/integration/services/test_onboarding_preparation_http.py`：34 passed，覆盖两个完整文件，包括新档案幂等别名回归；实际运行源码与冻结候选一致。工程契约检查及其 63 项 unittest、标准文档构建均已通过。

整体数据库验证流程仍为 failed：业务测试通过后，关闭隔离 PostgreSQL 的步骤返回 `command_failed_docker`，未取得原数据库进程的退出码。后续只读检查确认测试容器已不存在、线上服务健康；这些观察不能将清理步骤改记为通过。正式发布仍须完成正常清理及完整发布门槛，真实 Worker 三餐保存和单餐调整尚未验证。

此前 Windows 局部测试为 23 passed、2 deselected，另有 Linux `os.O_DIRECTORY` 导致的收集失败；以上 Linux 实际结果单独保留，未改写历史失败记录。新增 ORM 查询的 PostgreSQL 方言编译、Ruff check、format check 和 diff check 也已通过。

## 风险

正文匹配增加固定菜谱库中的扫描；最多返回四项，扫描量不受此返回条数限制，真实 PostgreSQL 验证应记录耗时。正文仍由既有原文 Owner 回读。普通标题的来源标签仅用于排序与召回，不授予专业批准；模型仍可能找不到符合限制的真实做法，必须明确返回缺口。真实 Worker 验证由发布主流程执行。
