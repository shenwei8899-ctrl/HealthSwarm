# Reference Product Name SKU Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Match recipe ingredients to commerce products by product name, let the Agent select only real candidate SKUs for the current family, and save unmatched ingredients as self-purchase items.

**Architecture:** The service owns normalized ingredient names, candidate groups and original recipe references. The Agent receives opaque candidate keys plus real SKU facts and returns only SKU/package choices; the service validates and persists those choices, while unmatched ingredients use the existing gap projection with explicit self-purchase semantics.

**Tech Stack:** Python 3.12, Pydantic, FastAPI service layer, pytest, Vue 3/uni-app, Node test runner.

**Spec:** `agent/docs/2026-11-09-reference-product-name-sku-selection-design.md`

## Global Constraints

- Product matching uses only normalized recipe ingredient names and commerce `product_name`.
- Agent choices are limited to server-issued candidate SKU IDs.
- Reliable servings may scale required quantity; missing servings never invent personal portions.
- Unmatched or unavailable ingredients save successfully as self-purchase items with no SKU or price.
- Existing diet restrictions continue to constrain recipe selection, not product-name matching.
- No database migration and no commerce or Agent admin page changes.
- Preserve live-only source behavior before feature edits.

## Review Focus

- Compound or alternative ingredients such as `vegetable or peanut oil` must not match olive oil by broad semantics.
- Duplicate ingredients across dishes must share one candidate group without losing original references.
- Unit-incomparable recipe quantities must not claim exact package coverage.
- Catalog service failure must remain an error instead of converting every item to self-purchase.
- Mixed purchasable and self-purchase items must never send null SKU entries to checkout.

---

### Task 1: Reconcile the Git baseline with deployed source

**Files:**
- Modify: six deployed meal-planner source files under `agent/Yuxi-main/backend/package/yuxi`
- Test: existing reference meal unit tests

**Interfaces:**
- Consumes: source captured under `agent/.tmp/live-source-20261109`
- Produces: tracked source that preserves the deployed Agent purchase contract, correction handling, daily projection and cosmetic compatibility

- [x] Compare each captured file with `origin/main` and classify every live-only hunk.
- [x] Apply the live-only behavior to tracked source without copying runtime secrets or generated artifacts.
- [x] Run the focused reference unit tests from `agent/Yuxi-main/backend`.
- [x] Record any existing test expectation that must change only because the deployed contract is newer.

### Task 2: Add name-owned candidate groups

**Files:**
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/reference_recipe_matching.py`
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/reference_meal_plan_service.py`
- Test: `agent/Yuxi-main/backend/test/unit/services/test_reference_meal_plan.py`

**Interfaces:**
- Produces: `reference_product_name_candidates(ingredients: tuple[str, ...], products: list[dict]) -> list[dict]` with stable candidate keys, original references and real SKU candidates

- [x] Add tests for English/Chinese aliases, alternative oils, duplicate ingredients, no match and details-independent matching.
- [x] Implement controlled name normalization and candidate grouping using only ingredient text and `product_name`.
- [x] Return candidate groups from recipe reads without exposing model-editable source ownership.
- [x] Run focused tests and confirm they pass.

### Task 3: Replace free-form mappings with candidate SKU choices

**Files:**
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/reference_meal_plan_types.py`
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/reference_meal_selection_service.py`
- Modify: `agent/Yuxi-main/backend/package/yuxi/agents/toolkits/meal_planner.py`
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/health_consultation_service.py`
- Test: `agent/Yuxi-main/backend/test/unit/services/test_reference_meal_selection.py`
- Test: `agent/Yuxi-main/backend/test/unit/toolkits/test_reference_save_validation_feedback.py`

**Interfaces:**
- Consumes: candidate groups from Task 2
- Produces: tool input containing candidate key, selected `sku_id`, integer package quantity and optional selection note; service-owned `ingredient_refs`

- [x] Add tests proving an outside SKU is rejected, free-form `match_basis` is unnecessary, and server-owned references are preserved.
- [x] Implement the candidate-choice schema and service assembly with receipt-bound candidate keys.
- [x] Update the Agent prompt to choose only issued candidates and apply coverage/minimum-excess/lowest-price ordering when the source provides reliable servings.
- [x] Keep one correction path for invalid candidate choices; after correction exhaustion convert unresolved items to self-purchase.
- [x] Run the focused test modules and confirm they pass.

### Task 4: Persist and project self-purchase items

**Files:**
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/reference_meal_plan_service.py`
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/daily_meal_plan_service.py`
- Modify: `agent/Yuxi-main/backend/package/yuxi/services/meal_dish_service.py`
- Test: `agent/Yuxi-main/backend/test/unit/services/test_reference_meal_plan.py`
- Test: `agent/Yuxi-main/backend/test/integration/services/test_reference_meal_plan_http.py`

**Interfaces:**
- Produces: compatible gap projections with `purchase_mode="self_purchase"`, `sku_id=None`, `price_cent=None`, original ingredient and source quantity

- [x] Add tests for no product, no available SKU and mixed purchase modes.
- [x] Implement self-purchase persistence and projection without a schema migration.
- [x] Ensure purchase endpoints filter self-purchase entries and preserve matched items.
- [x] Run the focused unit tests; HTTP integration remains environment-dependent.

### Task 5: Show self-purchase items in the miniapp

**Files:**
- Modify: `App/src/components/ReferenceMealPlanCard.vue`
- Modify: `App/src/components/CloudMealPurchase.vue`
- Modify: `App/src/utils/meal-presentation.js`
- Test: `App/tests/reference-meal-plan.test.mjs`
- Test: `App/tests/meal-purchase.test.mjs`

**Interfaces:**
- Consumes: compatible self-purchase projection from Task 4
- Produces: separate “商城可购” and “自行购买” display; checkout contains only SKU-backed items

- [x] Add Node tests for “自行购买/暂无价格”, mixed lists and checkout exclusion.
- [x] Implement the minimal display changes in the existing card and purchase detail.
- [x] Run the focused Node tests from `App`.
- [x] Build the WeChat miniapp and run the existing package-size check（构建成功；既有主包预算仍超 5,030 bytes）。

### Task 6: Regression, decision finalization and local handoff

**Files:**
- Modify: `agent/Yuxi-main/docs/develop-guides/decisions/proposed/2026-11-09-reference-product-name-sku-selection.md`
- Test: backend focused unit/integration suites and App focused tests

**Interfaces:**
- Consumes: Tasks 1-5
- Produces: reviewed local branch ready for merge, with no deployment

- [x] Run backend reference meal tests, App reference purchase tests and `git diff --check`.
- [x] Run repository engineering-contract checks when their runtime is available.
- [x] Rewrite the decision record as implemented current fact after focused tests pass.
- [x] Request a fresh whole-diff review required by repository instructions and fix material findings.
- [x] Keep the completed work local until the user's next instruction; merge, push and deployment were subsequently authorized on 2026-11-09.
