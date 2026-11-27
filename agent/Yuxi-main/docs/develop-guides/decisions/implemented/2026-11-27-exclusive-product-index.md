# 专属计划按固定商品快照复用索引

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/exclusive_plan_tasks.py

## 问题

专属计划参考菜单按候选原谱估算食材费用。每次估价都进入采购计算并重建全量商品身份、别名与匹配规则，固定目录的准备成本随候选菜数重复支付。菜谱费用缓存只能避免同一原谱再次估价，无法消除不同原谱的重复索引构建。

## 决策

### 实现方案

任务层为本次执行的固定商品快照建立一个 `ReferenceProductIndex`，通过 `asyncio.to_thread` 完成准备，随后顺序传给三档逐日生成。生成层把同一索引传给候选费用估算、候选菜单合并采购比较和选定菜单采购。逐日保存前的原谱复核与采购重算也接收同一索引，来源验证和计价仍完整执行。独立单日生成在未传入索引时建立一个局部索引；独立采购和费用计算继续支持原调用方式。各层实现见[任务生成](../../../../backend/package/yuxi/services/exclusive_plan_tasks.py)和[参考计价](../../../../backend/package/yuxi/services/exclusive_reference_plan.py)。

索引与菜谱费用缓存只属于本次执行。恢复执行读取已持久化的原商品快照并重建索引，已保存天序沿用原恢复流程。索引的食材文字解析缓存只记录食材身份；价格、库存、限制、用量和包装计算仍在每次采购调用中执行。索引不写入数据库、不使用全局缓存、不跨任务共享，也不改变下单时的商品核对。

修复直接保留既有函数与计价规则，使用一个内部可选参数传递已准备索引；没有需要单独裁决的持久化、协议或任务生命周期变化，采用直接 implemented 记录。

## 替代方案

逐菜重建维持相同结果但保留重复成本。跨请求全局缓存需要额外处理目录版本、账号与失效，不适合固定任务快照的局部优化。仅在单日内复用可以减少逐菜准备，但三档七天仍重复准备；任务层持有索引可以覆盖整个生成循环。

## 后果

同一执行内索引保留至三档生成循环结束，食材解析缓存随任务释放。任务内的异步线程调用按原有顺序等待完成，索引无需新增并发写入机制。不同快照分别构建，包含相同版本字符串的独立快照也不共享索引。金额、采购缺口和菜单结果保持原语义。

## 验证

回归入口：[索引复用测试](../../../../backend/test/unit/services/test_exclusive_product_index.py)、[计价边界](../../../../backend/test/unit/services/test_exclusive_plan_prices.py)和[预算与整期包装](../../../../backend/test/unit/services/test_exclusive_reference_budget.py)。在 backend 目录执行 `python -m pytest test/unit/services/test_exclusive_product_index.py test/unit/services/test_exclusive_plan_prices.py test/unit/services/test_exclusive_reference_budget.py -q --timeout=40`。

相关45项单元测试通过，覆盖首次估价构建一次、同快照费用及缺口等价、零价、库存缺失、未知用量、限制独立核对、不可用目录和不同快照价格隔离。任务装配单元测试执行真实三档七天生成、来源复核、采购重算与逐日保存回调，用合成持久化替身及对象存储原谱模拟首日中断及恢复，并核对索引重建与已保存首日不变；它不替代真实数据库或 Worker 集成证据。恢复修改前的真实单日实现，构建次数断言以44次对1次失败。905个合成规格与40份合成原谱的单日对照中，完整结果相等且目录未变；该探针不能代替生产整期性能验收。

真实 HTTP/PostgreSQL/Worker 全链路及生产整期耗时未运行，本地 Docker daemon 不可用。工程契约检查另有既存文档错误，契约验证器测试存在 Windows 符号链接权限限制；这些结果不能计为通过。
