# 参考餐单的已核实商城文案改动

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/reference_meal_plan_service.py

## 问题

已保存的每日参考餐单仍持有有效的 SKU、规格、配料与过敏原资料，但商城将演示商品名称中的“示例·”移除，并在详情前加入供货说明。保存时的商品事实哈希包含名称和完整详情，回读因此把三餐都判为商品变化；后续重新生成失败时用户无餐单可读。

## 决策

### 实现方案

参考餐单服务保留保存时严格的商品事实哈希校验。历史回读和已签发采购来源校验只有在旧名称、旧详情与当前商城内容完全符合这次固定的演示文案改写，且 SKU 身份、分类、规格、配料、过敏原、资料完整度、上架状态和库存均保持有效时，才接受旧商品快照。其他文字变化仍失效。公开餐单展示当前商城名称、详情和图片，不改写已发布回执或持久化快照。

## 替代方案

- 始终要求重新生成：能保持严格哈希，但这次文案调整会使旧餐单不可读，且新生成链路另有保存失败。
- 从事实哈希永久移除名称和详情：实现短，但可能放过改变食材身份或过敏提示的修改。

## 后果

这是限定于已核实改写的只读兼容规则，不改变新餐单保存时的严格来源校验。长详情截断或未来其他文案编辑不会自动通过，需单独核对，以免把真实配料与过敏提示变化当作展示调整。

## 验证

`uv run --group test pytest test/unit/services/test_reference_meal_plan.py -q -k "not real_tool_node_injects_runtime_into_reference_save and not model_json_cannot_forge_the_injected_reference_runtime"`：63 passed、2 deselected；新增用例曾在旧严格哈希下因 `reference_product_changed` 失败。固定文案通过，其他详情、商品身份、配料、过敏原、规格、类别、下架和库存变化仍拒绝。`ruff check` 与 `ruff format --check`、工程契约检查通过。

真实 HTTP 集成用例 `test_daily_plan_keeps_saved_meal_after_verified_demo_copy_edit` 已写入，但本机 Windows 缺少 `os.O_DIRECTORY`，Docker 引擎也未运行，故尚未执行；当前不能据此宣称线上餐单已恢复。新保存保持严格哈希的边界由既有 `test_changed_product_description_requires_fresh_selection` 覆盖，当前环境同样未能运行该集成用例。
