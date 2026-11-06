# 参考餐单食材规格不匹配的有限纠错

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/agents/toolkits/meal_planner.py

## 问题

参考餐单保存时，模型可能为原谱中带有加工状态要求的食材选择状态未证实的商品。完整草稿或最终保存校验仍可能返回 `reference_ingredient_mismatch`，错误需要进入当前 Run 的有限纠错路径。`read_selection` 装配时多余模型选品的确定性处理见[参考餐单剔除未对应菜谱的模型选品](2026-11-07-reference-unused-purchase-selection.md)。

## 决策

### 实现方案

`save_reference_meal_plan` 将仍由最终校验返回的 `reference_ingredient_mismatch` 作为当前请求可纠正的保存错误返回结构化工具回执；`MealPlanResultMiddleware` 识别回执后只允许一次再次调用保存工具。模型据已读菜谱的 `ingredient_matches` 重选 `matched` 的原谱商品，对 `needs_confirmation` 和 `missing_product` 保留真实缺口。原有食材匹配、采购覆盖、菜谱来源和最终保存校验继续由业务服务执行，纠错仍受同类保存错误的次数预算约束。

## 替代方案

放宽商品加工状态匹配可以让该请求直接保存，但会把未经证实的规格当成原谱食材。直接向用户返回失败保留了校验，却让可修正的模型选择错误终止整个 Run。当前方案沿用已有的一次纠错通道和业务校验。

## 后果

模型有一次根据真实工具回执修正采购选择的机会。没有合适规格时，最终餐单保留缺口；模型再次提交不匹配规格或其他校验失败时，请求仍会失败。已失败的 Run 不自动重跑。

## 验证

真实 SDK 与 ToolNode 的合成回放覆盖错误回执、强制单次保存重试和修正后的快照；真实原谱装配与食材匹配的合成用例覆盖加工状态未证实的商品拒绝、纠正后保留待确认缺口。负向案例覆盖同类错误不能被忽略或重复纠错。上线后的真实模型生成与持久化结果仍需单独核对。
