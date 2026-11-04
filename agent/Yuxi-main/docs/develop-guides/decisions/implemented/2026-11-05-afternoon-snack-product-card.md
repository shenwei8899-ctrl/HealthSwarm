# 下午加餐商品卡与购买入口

状态：implemented
类型：feature
Owner：backend/package/yuxi/agents/middlewares/health_catalog.py

## 问题

用户询问“下午加餐吃啥”时，普通咨询不会稳定查询真实商品；现有食材包卡片和详情页还会展示冗长商品说明，购买交互与今日餐单详情不一致。

## 决策

### 实现方案

咨询中明确询问下午加餐吃什么时，`HealthCatalogMiddleware` 强制调用 `find_food_packages`，并在有查询结果后要求 `select_food_products`。完成消息绑定实际商品回执；用户明确拒绝商品时维持普通建议，无合适商品时只回答已核实的建议和缺项。对话采购 service 继续校验本人、回执、SKU、配料、版本及购买资格。

客户端 `ConversationFoodPackages` 只展示图片、商品名、规格和参考价。`ConversationPackagePurchase` 详情用商品名、规格及配料字段给出简短信息，不展示完整 `product_description` 或长篇 `note`。购买入口使用今日餐单的 `MealPurchaseSheet` 和 `MealPurchasePanel`，向现有对话采购接口发布固定一包的 SKU，再核价、下单并进入订单详情支付。地址返回后重新读取并核价；过期报价及不确定下单结果沿用既有校验与恢复。

## 替代方案

仅修改前端卡片无法让普通加餐问题产生真实商品回执；硬编码低脂牛奶会绕过目录、本人限制及库存变化；把商城原文简单截断会丢失限定条件。因此选择真实商品查询和最小字段展示。

## 后果

对话食材包的数量保持服务端固定一包，采购面板隐藏增减和取消选择控件；今日餐单仍按原逻辑选择与调整商品。真实模型是否选出合适加餐商品取决于当前目录及本人已确认限制；图片是否与 SKU 对应取决于商城源数据。

## 验证

`test_health_meal_advice.py` 40项、`test_health_catalog_final_answer.py` 21项、App定向36项通过；H5与微信小程序构建通过。负向覆盖明确拒绝商品、未提交选择、异常或过期报价、未知订单结果及跨账号晚到响应。全量App测试存在既有 `defineOptions` 测试夹具缺失；本机缺少 `langgraph.checkpoint.postgres`，对话采购单测无法收集。真实模型、商城SKU图片、真实订单/支付及微信真机尚未验收。
