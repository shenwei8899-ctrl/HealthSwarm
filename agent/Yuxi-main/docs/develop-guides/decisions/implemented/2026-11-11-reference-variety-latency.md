# 参考配餐检索提速与家庭日期差异

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/reference_meal_plan_service.py

## 问题

固定前三名与顺序截断让不同家庭取得相同候选。重复解析、商品匹配和遗漏候选商品导致生成耗时。历史排除仅覆盖同账号当天。

## 决策

### 实现方案

`reference_recipe_index` 以实际分片内容缓存原谱解析，以完整商品快照缓存商品索引及食材匹配，有界淘汰；读取和保存仍核对实时来源。每个关键词最多八个候选，轮流合并最多二十四个，摘要缩短为三百二十字。共享缓存不保存家庭档案或最终餐单。

`reference_variety_repository` 只投影菜谱身份和日期，跨账号读取家庭历史。`reference_recipe_variety` 排除当天和相邻日期已用单菜，近十四天单菜历史与公共使用频率在来源、采购质量相同时降权，家庭口味参与相关性排序。保存与发布持有同一 PostgreSQL 事务锁，拒绝同家庭近十四天完整餐单复用、不同家庭同日完整餐单相同。菜名规范化和来源 ID 都参与判重，交换餐次或菜品顺序不能规避。分餐合并使用每日计划中当前账号的真实来源；没有每日索引的旧计划在发布时读取原有来源，不能跨账号拼接虚构组合。

保存成功且尚未发布的完整预览保留组合，防止并发穿过发布间隙；failed、cancelled、interrupted 任务释放预览保留。已发布组合仍由每日计划引用校验。当前 Run 自身预览不参与历史排除，保留重复保存的幂等性。

`reference_meal_selection_service` 只补齐当前目录与本轮已发出候选交集唯一的商品，多候选继续要求明确选择。`meal_planner` 对重复允许两次重新检索和选菜，第三次失败终止；这与原文、采购、译文修正预算分开，换菜后可修正新菜谱。任务和前端保留固定错误类型并停止轮询，提示重选次数耗尽，不把它误称为整个知识库候选耗尽。营养计算和专业复核不在本次范围。

## 替代方案

仅改变提示词无法约束固定候选；全站禁止复用单菜会耗尽候选；共享最终餐单缓存会破坏个性化，因此不采用。

## 后果

不同家庭可以使用同一道合适的菜，不能在同一天得到完全相同的三餐组合。十四天是本次历史窗口，不承诺无限期不重复。健康限制和来源有效性优先，不能为追求差异改写食材或放宽限制。

同日不同家庭及相邻日期并发保存使用同一全局事务锁；模型和商城网络请求在取得锁前执行，锁内只完成数据库校验与写入。使用量增长后需观察历史查询与锁等待。缓存为进程内共享、重启后为空，知识库或商品变化会重新计算。真实模型耗时另行测量，本地缓存测试不承诺一分钟端到端延迟。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 候选覆盖每个关键词，缓存随数据变化失效 | 第四词饥饿或库存陈旧 | reference_recipe_index | test_reference_variety / test_reference_search_latency | 内容、商品变化 | 通过 |
| 邻日单菜、家庭十四天整套与跨家庭同日整套验重 | 跨账号、分餐或并发绕过 | reference_recipe_variety / reference_meal_plan_service | test_reference_variety / test_reference_variety_pg / test_reference_meal_plan_http | 同菜不同文件、换餐次、虚构账号组合、旧版发布、失败保留释放 | 通过 |
| 唯一候选补齐且歧义保持显式 | 自动匹配越权 | reference_meal_selection_service | test_reference_meal_selection | 多候选及未发出候选 | 通过 |
| 重选可恢复且有上限，终态停止轮询 | 死循环、错误预算、通用错误覆盖原因 | meal_planner / health_task_service / App | test_reference_save_correction / test_run_worker / health-task-flow / today-meal-plan | 采购后重选、译文重选再纠正、第三次交替错误、失败终态 | 通过 |

2026-11-11 本地证据：

- 隔离镜像 `healthswarm-agent-verify:local`，后端挂载到 `/app`；独立 PostgreSQL 16 容器，没有连接生产数据库。相关 unit 328 项、`test/unit/services/test_run_worker.py` 99 项通过；真实 HTTP `test_reference_meal_plan_http.py` 62 项与 `test_reference_variety_pg.py` 6 项通过。入口命令是 `python -m pytest <上述测试文件> -q --disable-warnings --show-capture=no`，PG 测试使用 `FAMILY_TEST_POSTGRES_URL` 指向隔离库。
- `node --test App/tests/health-task-flow.test.mjs App/tests/today-meal-plan.test.mjs App/tests/chat-task-recovery.test.mjs`：172 项通过；`npm run build:h5`：通过。
- 合成 3687 份短原谱、四类食材和四个关键词，连续六次批量排名：冷调用 1.0971 秒，之后五次中位数 0.0981 秒，每词八个候选。仅验证解析与匹配缓存的本地 CPU 收益，不代表生产文档分布、数据库查询、模型耗时或总生成时长。
- `python scripts/verify_engineering_contracts.py`、`python -m unittest scripts.test_verify_engineering_contracts`（63 项）、`git diff --check` 通过。Ruff 改动无新增问题；`run_worker.py` 两处 UP038 在 HEAD 原版同样存在，未扩大范围修复。
- 独立 Reviewer 审查通过；没有执行真实供应商模型调用、真实 Worker/Redis/Milvus 全链路 E2E、线上性能验收或部署。数据库与 HTTP 证据不替代这些未执行项。
- 提交前在完整项目挂载环境运行 `python -m pytest test/unit -m "not slow" -q --disable-warnings --show-capture=no --maxfail=5`：5884 通过，3 个旧 unit fixture 因缺少 `session.execute` 失败。补齐空历史查询接口和合成家庭字段后，`test_reference_meal_completion.py` 与 `test_reference_meal_plan.py` 共 86 项复测通过，原正反向断言保留并经过独立审查。业务代码未因这些失败调整；未重复运行全量，不能将该次全量结果记为全部通过。
