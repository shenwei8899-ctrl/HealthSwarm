# 餐单按商品匹配、购买时选择规格 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 本地实现参考餐单绑定商城商品、返回全部有效规格，并把 SKU 选择和交易校验延后到用户购买阶段。

**Architecture:** 商城继续拥有版本化目录和 SKU 事实，Agent 在商品层匹配并保存 `product_matches`，小程序在现有详情与采购组件中展示规格并要求用户选择。历史 `purchase_items` 快照保持可读，新餐单不生成固定 SKU。

**Tech Stack:** ThinkPHP/PHP、FastAPI/Pydantic/Python、Vue 3/uni-app/Node test、PostgreSQL/Redis 既有拓扑。

**Spec:** `agent/docs/2026-11-10-product-level-meal-commerce-design.md`

## Global Constraints

- 只修改本地代码，不发布线上或操作真实订单。
- 不重做三方页面视觉，不写死用户 ID 12。
- 餐单阶段不因 SKU 库存、价格或包装数量失败。
- 营养、健康和商品事实不得由模型编造。
- 新行为测试先红后绿，历史快照保持可读。

## Review Focus

- 同一商品多个 SKU 含有货和缺货时，全部有效规格返回且只有有货规格可进入交易。
- 商品目录在餐单保存后变价或售罄时，餐单仍可读且交易使用当前事实。
- 两个商品存在相似名称时，只接受标准名、明确别名或候选签发的 product_id。
- 一份菜谱存在未匹配食材时，其余菜品和商品仍保存。
- 两个认证用户同时生成同日同餐次时，不共享档案、近期排除或餐单结果。

---

### Task 1: 商城商品级目录契约

**Files:**
- Modify: `shop/addons/shop/library/v5/CatalogService.php`
- Test: `shop/tests/integration/IngredientCatalogServiceTest.php`

**Interfaces:**
- Produces: 现有目录在 `available_only=0` 时返回已发布商品的全部规格；Agent 以 `product_id` 聚合。

- [x] 增加测试：`available_only=0` 返回已发布但当前不可售的规格，默认查询仍只返回可售规格。
- [x] 复用现有目录接口，避免新增重复路由。
- [x] 在独立 Docker/PostgreSQL 测试库运行 PHP 语法检查和商城集成测试，确认通过。

### Task 2: Agent 目录缓存与商品候选

**Files:**
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/daily_commerce_service.py`
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/reference_recipe_matching.py`
- Test: `agent/Yuxi-main/backend/test/unit/services/test_dynamic_commerce_catalog.py`
- Test: `agent/Yuxi-main/backend/test/unit/services/test_reference_meal_selection.py`

**Interfaces:**
- Consumes: Task 1 商品级目录。
- Produces: `current_product_catalog()` 与 `candidate_products`，候选按 `product_id` 聚合并携带 `skus`。

- [x] 写失败测试：版本未变复用缓存、版本变化刷新；同名商品的全部规格归为一个候选，缺货规格不阻断匹配。
- [x] 实现商品级缓存读取与确定性商品候选。
- [x] 运行相关单元测试确认通过。

### Task 3: Agent 餐单保存商品关联

**Files:**
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/reference_meal_plan_types.py`
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/reference_meal_selection_service.py`
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/reference_meal_plan_service.py`
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/reference_recipe_presentation.py`
- Modify: `agent/Yuxi-main/backend/package/yuxi/agents/toolkits/meal_planner.py`
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/health_consultation_service.py`
- Modify: `agent/Yuxi-main/backend/package/yuxi/agents/buildin/health_meal_planner/graph.py`
- Test: `agent/Yuxi-main/backend/test/unit/services/test_reference_meal_selection.py`
- Test: `agent/Yuxi-main/backend/test/unit/services/test_reference_meal_plan.py`
- Test: `agent/Yuxi-main/backend/test/unit/toolkits/test_reference_save_validation_feedback.py`

**Interfaces:**
- Consumes: Task 2 `candidate_products`。
- Produces: 新餐单 `product_matches`；历史 `purchase_items` 保持可读。

- [x] 写失败测试：保存工具只接受候选 product_id；未匹配食材形成缺口；SKU 变价、售罄不影响新餐单保存和读取。
- [x] 实现产品选择 DTO、服务端装配、快照和展示投影。
- [x] 更新提示和可恢复错误，使餐次缺失或候选结构错误进行一次内部纠错。
- [x] 运行相关单元测试确认通过。

### Task 4: 小程序规格展示与购买选择

**Files:**
- Modify: `App/src/utils/dish-commerce-presentation.js`
- Modify: `App/src/components/ReferenceMealPlanCard.vue`
- Modify: `App/src/components/MealDetailSheet.vue`
- Modify: `App/src/components/CloudMealPurchase.vue`
- Test: `App/tests/reference-meal-plan.test.mjs`
- Test: `App/tests/meal-detail-sheet.test.mjs`
- Test: `App/tests/cloud-meal-purchase.test.mjs`

**Interfaces:**
- Consumes: Task 3 `product_matches[].skus[]`。
- Produces: 菜品详情的商品规格列表和用户明确选择后的 SKU 交易请求。

- [x] 写失败测试：菜品详情保留商品全部规格，同一商品一次只选一个规格，采购只发送用户选中的规格。
- [x] 在不改变页面风格的前提下适配商品级数据和规格选择。
- [x] 运行相关 Node 测试和微信构建确认通过。

### Task 5: 兼容、文档与整链路验证

**Files:**
- Modify: `agent/Yuxi-main/docs/develop-guides/decisions/implemented/2026-11-10-reference-meal-product-level-selection.md`
- Modify: 受影响契约测试与接口说明。

**Interfaces:**
- Consumes: Tasks 1-4 完整契约。
- Produces: 可审计的本地验证记录和已实现决策。

- [x] 保留历史 `purchase_items` 快照读取测试，并检查改动路径没有硬编码用户 ID。
- [x] Agent 全量 unit 及新增边界定向复验、App 全量 1537 项、H5/微信构建和变更文件 Ruff 检查通过。具体运行边界见已实现决策记录。
- [x] 回读餐单、商品规格和交易请求：只有用户明确购买才创建推荐包，不自动写购物车或订单。
- [x] 决策记录移入 `implemented`。
- [x] 商城 PHP 集成测试、完整工程契约检查及契约检查器 63 项单元测试通过；执行 `git diff --check` 后交付。
