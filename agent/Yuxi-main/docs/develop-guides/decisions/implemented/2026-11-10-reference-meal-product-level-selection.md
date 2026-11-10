# 参考餐单按商品关联并延后选择规格

状态：implemented
类型：simplification
Owner：backend/package/yuxi/services/reference_meal_selection_service.py

## 问题

参考餐单曾要求 Agent 在保存前选择具体 SKU 和包装数量，并用库存、价格和本轮分类读取范围校验餐单。该约束把配餐与交易混在一起，导致商品名称已经匹配时仍可能因为 SKU 缺货、价格变化或包装无法估算而生成失败。

## 决策

### 实现方案

商城目录接口继续返回扁平 SKU，同时允许 `available_only=0` 返回已发布但当前不可售的规格。Agent 在 `daily_commerce_service.py` 中按 `product_id` 组合商品与全部规格，不复制商城事实，也不建立第二套商品知识库。

`reference_recipe_matching.py` 按菜谱食材名称、商城商品名称和明确别名生成 `candidate_products`。`reference_meal_selection_service.py` 只接受候选 `product_id` 与菜谱食材引用；`reference_meal_plan_service.py` 保存 `product_matches`，餐单保存不依赖 SKU 库存、价格或包装数量。历史 `purchase_items` 继续只读兼容。

小程序菜品详情读取商品及全部规格。用户发起采购时选择需要购买的规格，后端再读取商城当前目录并校验商品归属、销售状态、库存、数量和忌口冲突，随后沿用现有推荐包、购物车、核价和订单接口。未选择或无库存的商品不阻断其他已选商品。

## 替代方案

- 继续让 Agent 选择 SKU 会把包装估算、库存波动和交易状态带入配餐边界。
- 每次对话把全部 SKU 放入模型上下文会增加延迟和上下文体积。
- 把商城目录永久复制到 Agent 知识库会产生两份可能不一致的商品事实。

## 后果

- 配餐结果稳定绑定商品，价格和库存变化不再使已生成餐单失效。
- 一个商品的所有规格均可展示，但只有用户在采购阶段明确选择的可售规格进入推荐包。
- 商品下架后历史餐单仍保留来源，当前投影明确标记不可用，不伪装成可购买。
- 旧 SKU 级回执仍可读取；新餐单不再要求 Agent 选择 SKU。
- 已打开菜谱签发的跨分类候选可参与选择；候选以逐食材回执为边界，不能任意指定目录中的商品。
- 商品配料、过敏原或营养说明变化后须重新分析；直接采购 POST 同样校验。调价、增减规格、库存波动不使菜谱失效。
- 商城调库存、占用、释放和确认库存与目录版本在同一事务更新，Agent 下一次版本探测重读快照。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 餐单只绑定商品 | Agent 仍提交 SKU | `reference_meal_selection_service.py` | `test_reference_meal_selection.py` 与真实 HTTP/PG 测试 | 候选外商品、空候选回执及旧 SKU 写入被拒绝 | Passed |
| 全部规格可展示 | 只返回有货规格 | `daily_commerce_service.py`、`CatalogService.php` | `test_dynamic_commerce_catalog.py`、小程序全量测试 | 缺货规格可见但不能进入采购 | Passed |
| 库存价格不阻断餐单 | 保存时检查库存或价格 | `reference_meal_plan_service.py` | `test_reference_meal_plan.py` | 零库存商品仍可保存商品关联 | Passed |
| 交易实时校验 | 使用餐单快照直接下单 | `reference_meal_plan_service.py` | 采购阶段 unit 与小程序采购测试 | 缺货、跨商品 SKU、非法数量被拒绝 | Passed |
| 多用户沿用认证隔离 | 代码硬编码单一用户 | 现有认证上下文与 repository | 修改代码检索和既有用户隔离测试 | 请求始终从当前 `uid` 与家庭读取 | Inspected |

### 发布前验证记录（2026-11-10）

- App：`npm test` 1537 项通过；H5 与微信小程序构建通过。
- Agent：最终 Linux 容器全量 `pytest test/unit -m "not slow"` 5768 项通过、59 项跳过；新增修复覆盖商品资料变化、别名种类误配、跨分类缺货候选和旧餐单采购。
- HTTP/PG：`test_reference_meal_plan_http.py` 共 61 个案例，60 项在整文件运行中通过，余下展示投影断言修正后单独复验通过；采购资料变更直接 POST 及来源校验已额外复验。
- 商城：专用 `healthflow_link_test` 数据库中 `IngredientCatalogServiceTest.php` 通过，包含真实库存调整、占用、释放后目录版本更新；测试事务回滚。
- 工程契约检查通过；检查器 63 项单元测试通过；变更 Python 文件 Ruff 检查通过（本机旧 Ruff 的已有 UP038 提示单独排除）；`git diff --check` 通过。
- 独立 Reviewer 对业务代码复核未发现剩余功能阻塞；发布脚本的回滚步骤已改为独立尝试，避免单步失败跳过其他恢复动作。

边界：HTTP 测试使用真实 TCP 与 PostgreSQL，外部商城响应、对象字节为隔离测试输入；不代表真实模型、图片供应商或手机端到端验收。线上检查只读，不创建订单，不写模拟商品、档案或餐单。

旧能力不存在：新餐单保存工具不再要求 Agent 选择 `sku_id`、包装数量或价格。

重新引入条件：只有业务明确要求自动代购，并提供可审计的份量换算、包装选择和替代规则时，才重新评估餐单阶段自动选择 SKU。
