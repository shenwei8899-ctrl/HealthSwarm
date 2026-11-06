# 参考餐单烹饪用水缺口一致性

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/reference_cooking_water.py

## 问题

参考餐单允许将明确的纯烹饪用水保存为 `not_sold` 缺口；单菜采购重新核对同一缺口。两处使用不同的用水正则，已保存的 `1 ½ cups water` 在保存时通过、采购时被拒绝，返回 `dish_ingredients_missing`（409）。

## 决策

### 实现方案

`reference_cooking_water.cooking_water` 统一判断独立烹饪用水，识别整数加 Unicode 分数及已有的英文、中文用量与温度写法。参考食材匹配、餐单保存与单菜采购均调用此判断；餐单快照和采购来源仍保持原文，不改写历史缺口。汤底、调味料及复合食材继续需要明确商品或自备决定，不能标为纯用水。

## 替代方案

只放宽单菜采购的正则可恢复这一次读取，但保存阶段仍有另一套更宽的规则，后续会重现分歧。批量改写已保存餐单会改变用户原文和来源版本，因此不采用。

## 后果

已有纯用水缺口在读取采购预览时通过同一校验；新餐单的保存与后续采购使用同一规则。该变更不创建订单，不改变商品、库存和营养计算。

## 验证

`Passed`：`test_reference_cooking_water.py` 的正向及负向用例，连同参考餐单保存、选择定向测试共 80 项通过；合成 `1 ½ cups water`、旧中文温度写法、`1/2-cup water`、`1-2 cups water`、`water适量` 及 `water, as needed` 同时经过保存、食材匹配和单菜采购的真实函数。恢复旧正则会使该正向用例失败。

`Not run`：真实 PostgreSQL/HTTP 中已保存餐单的采购预览、商城发布及小程序页面；本地 Docker 不可用，服务器部署依用户要求等待明确指令。Windows 环境额外运行的 144 项相关测试有 142 项通过，2 项因缺少 `os.O_DIRECTORY` 无法导入，与本次用水规则无关。
