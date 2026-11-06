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

Windows 环境额外运行的 144 项相关测试有 142 项通过，2 项因缺少 `os.O_DIRECTORY` 无法导入，与本次用水规则无关。

## 线上部署与验证（2026-11-07）

用户授权后，修复提交 `47ae867` 快进至远端 `main`。生产保留原运行镜像的其他补丁，仅叠加三个相关服务文件；API 和 Worker 切换到同一镜像 `sha256:4d8266ad1152b0bfa10e0429e8ee975b2330391abe2f7141adcc234ba591765c`，均为 healthy，API `/api/system/ready` 返回 ready。候选镜像及两个运行容器中的 5 种纯用水写法通过保存、匹配、单菜采购函数，3 种复合食材被拒绝。线上 PostgreSQL 只读检查命中 3 份已保存参考餐单快照、3 道相关菜品，`1 ½ cups water` 均正确投影为 `not_sold`。发布记录与回滚配置在服务器 `/opt/healthswarm-agent/releases/reference-water-gap-47ae867-20261107/`。

尚未以授权用户身份执行真实 HTTP 采购预览、商城下单或小程序真机验收。Worker 的日终摘要定时任务另有 PostgreSQL 错误日志，其影响未在本次用水修复范围内核实。
