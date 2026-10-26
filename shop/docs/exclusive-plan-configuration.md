# 专属计划经营配置

本页供商城运营、供应链与发布人员填写真实经营参数。配置由 [PlanPolicyService](../addons/shop/library/v5/PlanPolicyService.php) 校验和读取；Agent 在配置范围内组合审核食谱，商城计算包装数量、金额和可预约日期。

## 发布入口与前置数据

后台「设置」的 `plan_rules` 资源新增版本，填写 `policy_version`、完整 `config_json` 和 Unix 秒格式的 `effective_at`。版本发布后不可覆盖，调整规则须新增版本。现有订单保留购买时快照；未购买方案按当前规则重新核对。

发布前确认三档真实 SKU、净重、部位、加工方式、过敏原、审核通过的食材换算，以及供应商供货关系。食谱版本须已在 Agent 审核发布，并有做法及商城食材编码映射。三档使用相同的营养和安全校验；预算只核对结果，不降低必要份量。

在配送区域内另建 `service_scope=plan` 的配送时段。该时段 `capacity` 表示每天该时段名额，区域 `daily_capacity` 表示每天全部计划时段总名额。普通订单使用 `service_scope=normal`，两者名额分开；已建时段不可切换用途。计划时段应填写真实有限容量，`used_capacity` 保持 0。未最终关闭的待支付订单继续占名额，支付状态不确定时不得仅凭本地过期时间释放。

## 配置字段与填表口径

金额一律为人民币分的整数，0 表示业务明确免收，`null` 表示待填写。下表中的必填项缺失不能发布；不要将待定值改成 0 来通过校验。

| 字段 | 含义 |
| --- | --- |
| `tiers.economy/standard/premium` | 经济型／标准型／品质型三组配置，必须全部存在 |
| `allowed_sku_ids` | 该档允许的真实商品规格 ID 列表 |
| `allowed_recipe_version_ids` | 该档审核食谱版本 ID 列表 |
| `difference` | 有商品依据的简短差异文案，不描述治疗效果 |
| `budget` | 按适用成员人数区间设整套金额范围；区间不重叠，不按成人价格乘人数 |
| `includes_service_fee/includes_delivery_fee` | 预算范围是否包含对应费用；含配送费时，选址后的报价才完整核对 |
| `repeat.dish_gap_days` | 两次使用同一菜品身份之间至少间隔的完整天数，0 允许相邻天复用 |
| `repeat.dish_max_per_7_days` | 滚动 7 天内同一菜品身份最多出现的天数 |
| `repeat.main_ingredient_max_per_7_days` | 滚动 7 天内同一主食材身份最多出现的天数 |
| `repeat_identity` | 每个允许食谱版本对应 `dish_key` 和 `main_ingredient_key`；改名不产生新身份，做法和主食材变化由审核人员按统一口径归类 |
| `service_fee_cent` | 整套一次收取，按 21 批分摊的服务费 |
| `quote_ttl_seconds/estimate_ttl_seconds` | 正式报价和展示预估金额的有效秒数 |
| `first_lead_days/resume_lead_days` | 首次预约／恢复预约的最少提前天数，按上海时区自然日计算 |
| `cutoff_lead_days/cutoff_time` | 每批相对送达日提前多少天、几点截单，`HH:mm` 上海时间 |
| `pause_max_days` | 从暂停时刻计算的最长可重新预约时间；超期转人工复核或取消剩余批次 |
| `booking_horizon_days` | 首批日期最远可预约到今天之后多少天 |
| `meal_lead_days` | 固定为 1：送达次日食用 |
| `regions` | `area_id`、每批 `fee_cent`、每日容量、开放星期（1 周一至 7 周日）、关闭日期列表 |

21 批按连续自然日排程，全部日期都满足区域和时段开放、截单及容量条件才返回可选首批日。时段额外费用逐批加入配送费。恢复不能与已确定批次重叠或改变餐单日序；新地址或时段涉及运费差额时转人工处理，不能静默收费。

## 填写模板

以下 JSON 是待填表，不能直接发布。将 `null` 和 `待填` 全部替换为业务已确认的实际值，补齐各档完整清单。预算金额须用同一组成员的实际三套菜单与商品核算后确定。

```json
{
  "tiers": {
    "economy": {"allowed_sku_ids": ["待填"], "allowed_recipe_version_ids": ["待填"], "difference": "待填", "budget": [{"min_members": null, "max_members": null, "min_cent": null, "max_cent": null, "includes_service_fee": null, "includes_delivery_fee": null}], "repeat": {"dish_gap_days": null, "dish_max_per_7_days": null, "main_ingredient_max_per_7_days": null}},
    "standard": {"allowed_sku_ids": ["待填"], "allowed_recipe_version_ids": ["待填"], "difference": "待填", "budget": [{"min_members": null, "max_members": null, "min_cent": null, "max_cent": null, "includes_service_fee": null, "includes_delivery_fee": null}], "repeat": {"dish_gap_days": null, "dish_max_per_7_days": null, "main_ingredient_max_per_7_days": null}},
    "premium": {"allowed_sku_ids": ["待填"], "allowed_recipe_version_ids": ["待填"], "difference": "待填", "budget": [{"min_members": null, "max_members": null, "min_cent": null, "max_cent": null, "includes_service_fee": null, "includes_delivery_fee": null}], "repeat": {"dish_gap_days": null, "dish_max_per_7_days": null, "main_ingredient_max_per_7_days": null}}
  },
  "repeat_identity": {"待填食谱版本ID": {"dish_key": "待填统一菜品身份", "main_ingredient_key": "待填统一主食材身份"}},
  "service_fee_cent": null, "quote_ttl_seconds": null, "estimate_ttl_seconds": null,
  "delivery": {"first_lead_days": null, "resume_lead_days": null, "cutoff_lead_days": null, "cutoff_time": "待填", "pause_max_days": null, "booking_horizon_days": null, "meal_lead_days": 1,
    "regions": [{"area_id": null, "fee_cent": null, "daily_capacity": null, "weekdays": [], "closed_dates": []}]
  }
}
```

## 发布与验收边界

先对商城应用 [021 增量迁移](../database/postgresql/migrations/20261025_021_exclusive_plan_contract.sql)，Agent 使用正式存储迁移升级 health schema 30→31，并同步 API 与 Worker 源码。保存数据库备份和原发布指向；升级包含新增表、列与索引，无需删除旧单日餐单。

新前端依赖这些接口及 schema，不能只替换静态页面。正式发布前须完成真实经营配置、专业食谱覆盖验证、队列进程恢复验证、支付回调及退款验证；小程序构建与微信上传/体验版/真机验收分别记录。缺业务配置时明确显示暂未开放，不向生产插入测试方案或样例价格。
