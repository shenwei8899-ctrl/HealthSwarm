# 食谱与份量营养计算

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_nutrition_service.py

## 问题

识图设计要求复合菜按照食材和净成品重量计算，碗勺份量使用有来源的版本表，油糖须区分已含、追加和替换。直接食品的每百克值不能表达这些输入，手工把食谱伪装为一个营养值缺少可回读的配方依据。

## 决策

管理员审核发布不可变食谱版本与份量参考。食谱保存所用食品版本、可食原料克数、成品净重量和油糖角色，营养由确定性服务计算；客户端不可自行提交食谱营养值。饮食项显式二选一选择食品或食谱，碗勺数量在服务端换算且标为估算，映射与数量改变使旧计算失效。直接食品及追加成分的配方估算属性一并汇总，称重主食品不能隐藏追加成分的估算标记。

油糖调整属于整盘已确认净重量。替换仅允许可辨识的配方油糖，先移除原配方相应成分再加入替换量；追加表示配方之外的额外量。服务端按最终净重扣除调整量、扣除被替换的配方角色计算基底份数，再应用个人比例。缺失量不补成零，不能确定原配方油糖时拒绝替换。所用食谱、食品和份量版本完整保存于计算快照。

迁移 health schema 2 只增加两张表，不改已有食品、草稿或正式记录。旧计算快照保持原计算版本可读；新增计算使用 recipe-portions-v2。真实食品、食谱授权及云识别效果依赖业务审批，计算和接口使用明确标记的合成数据验证。本决定补充[健康识图工作台](2026-10-04-health-vision-workbench.md)的营养计算语义，工作台的授权、私有存储和任务 Owner 保持不变。

## 替代方案

继续让用户把配方手工换成每百克数据不能回读食材、成品重量与油糖组成。由模型估算营养与数量不符合设计。未审批食品数据不自动导入或发布。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 配方按净成品克数和个人比例确定性计算 | 误用原料总重 | calculator、recipe version | 独立手算 unit 与真实 HTTP 回读 | 生熟产率差异、缺失营养、空比例与明确零比例 | 通过，食谱专属 19 项 unit |
| 碗勺使用匹配版本且保持估算来源 | 用户伪造克数或跨食品引用 | DTO、份量查询、calculator | unit、HTTP、Vue 表单、真实浏览器 | 跨映射、同时填克数、缺数量 | 通过；真实页面数量改动即时移除预览并禁用确认 |
| 油糖追加和替换不重复计入 | 保留原油又加入替换油 | calculator | 独立油糖 oracle、HTTP 确认回读 | 无可辨识配方油、调整重超净重、估算调整遗漏 | 通过；追加 250 kcal、替换 182.50 kcal、估算调整 390 kcal oracle |
| 历史、并发确认与权限保持 | 覆盖旧食谱或旧计算可确认 | PG、确认服务 | live HTTP、已有 health 回归 | 重复发布、非管理员、改量旧预览 | 4 条 HTTP 业务链路通过；新配方确认直接回读 PG 快照 |
| 增量迁移可重复执行 | 新表缺失或破坏旧数据 | storage-migrator | 真实 PG 迁移与 schema 回读 | health 1 升级及重复迁移 | 通过；旧食品版本和营养值保持，两次执行新增表 DDL 无误 |

`docker compose exec -T api uv run --no-sync --group test pytest test/integration/services/test_health_vision_http.py test/integration/services/test_health_vision_executor.py test/unit/services/test_health_vision_protocol.py test/unit/services/test_storage_migration.py` 完整执行 46 项通过；报告与饮食执行器仍只对外部模型响应使用合成替身。核心识图与食谱 unit 重新执行 39 项通过。独立 Reviewer 对估算调整修复重新执行食谱 unit 18 项通过，无剩余 P1/P2。

`docker compose exec -T web node --test test/healthMealReview.test.js test/healthVisionView.test.js test/healthVision.test.js` 11 项通过，`pnpm run lint:check` 与 `pnpm run build` 通过。真实浏览器完成发布食品、配方和份量参考、创建人工餐、数量纠错、预览失效及确认入账；独立 PG 回读确认 50.00 kcal、estimated=true、recipe-portions-v2，随后按精确 ID 清理合成资源，不修改账号。工程契约与脚本单元 62 项、docs build 均通过。完整前端 suite 未完成；既有 subagent 生命周期测试单独设置 60 秒上限仍未输出业务断言结果，超时取消，不记为完整回归通过。云端实样准确率、商业食品数据与小程序签名对接均为 Not run。

完整后端 unit 设置 300 秒上限仍未完成。独立执行既有 worker 文件时，超 24 小时任务默认值的子进程测试通过；后续 `test_process_subagent_run_restores_runtime_context` 长时间未结束，90 秒上限取消整文件。排除该文件后执行 `pytest test/unit -m 'not slow' --ignore=test/unit/services/test_run_worker.py`，2221 项通过、54 项跳过，耗时 207.46 秒。未改变无关 AgentRun 运行或测试逻辑；排除运行不构成完整回归通过。

## 后果

参考食谱不等于实拍菜的真实配方，计算保留估算标记。新增字段是原契约的可选扩展；旧客户端可继续使用直接食品克数。个人分食比例允许明确填写零，留空仍为未知，系统不自动补比例。份量参考未经实测审核不发布，发布人负责来源和许可。
