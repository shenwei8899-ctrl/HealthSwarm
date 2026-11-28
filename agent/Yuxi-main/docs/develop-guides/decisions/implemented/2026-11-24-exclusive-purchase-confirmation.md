# 7 天参考计划采购确认与配送

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/exclusive_plan_purchase.py

## 问题

原谱配送建议不能表达用户减选及调整包装数后的实际采购。确认界面需要核对同一份商品、分趟数量、开始食用日及整周运费，批次仅可查看；食材明细默认折叠，修改仍在采购页。

## 决策

### 实现方案

商城版本化政策的 `delivery.storage_rules` 按 SKU 维护储存依据，每条仅有 `review_status`、`condition`、`max_days`、`source`、`version` 五个字段；正式发布只接受 approved、ambient/refrigerated/frozen、正整数保存天数及非空来源版本。商品目录输出当前有效政策中的规则，目录身份包含有效政策摘要以覆盖定时生效。缺少规则返回待核对，不填默认保鲜天数。

Agent [采购来源](../../../../backend/package/yuxi/services/exclusive_plan_purchase.py)仅签名发布选中 SKU 的使用日及审核规则，不传成员健康或完整菜谱。Shop 将签名规则与当前政策直接比较，使用实际购买整数包装分配各趟，复用配置的配送区域、统一时段、提前期、停运日期及整周费用。包装不足以分趟时要求返回调整，不自动加购；原谱相对用量用于分配，不代表家庭份量已核定。食材在对应使用日前一天送达。

报价及订单的现有 pricing snapshot 保存配送安排；下单事务锁定规则并重新计算。SKU 包装、成分、过敏原先用现有 assertComposition 校验，再排除含动态 valid_until 的展示快照，比较数量、价格、金额、排期及政策身份。容量统计同时包含服务计划和参考采购，取消或未付款过期参考订单不占用容量。

[专属确认组件](../../../../../../App/src/components/ExclusivePurchaseConfirmation.vue)复用既有采购控制器，以地址、开始用餐日期、统一时段、只读时间线、折叠食材、费用顺序展示；日期或时段变化使旧报价失效。付款与分趟供应商履约未开放，按钮明确禁用；v5、旧版及本地测试付款入口均拒绝 exclusive_delivery 快照，订单详情不提供 pay/repurchase 动作。真实付款通知的事实处理保留原路径。

## 替代方案

- 只在前端搬运原谱建议：无法反映减选或包装调整，拒绝。
- 转为已有 service_plan：其三档政策、菜单及售后契约不同，拒绝。
- 专属界面复用既有商品控制器；普通采购弹层及交易来源不变。

## 后果

无需新增数据库结构。部署需要 Agent 与 Shop 后端、App 同步更新，商城需已有计划政策、配送区域及时段，并由业务人员发布真实审核的储存规则。未提供的规则、费用及可预约日显示待确认，不承诺固定三趟。支付开放需要完成分趟履约契约后明确移除服务端付款限制。

## 验证

| 验收主张 | 失败面 | Owner | 证据 | 负向案例 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| 配送数量严格等于最终选购量 | 原谱取整重复购买 | ExclusivePurchaseDeliveryService | PHP 分配单测及 PostgreSQL 集成 | 包装数不足、取消商品、整数守恒 | Passed |
| 排期、费用与订单快照一致 | 单趟费用冒充整周 | CheckoutService、PlanScheduleService | PostgreSQL 回读、两个独立 PHP 进程抢最后名额 | 停运、容量、取消、跨秒提交 | Passed |
| 专属确认清晰只读 | 普通采购被改动 | App 专属组件、控制器 | 144 项 Node 测试；320/390/430 宽实际构建浏览器交互；H5/小程序构建 | 时段重报价、折叠展开、未知金额不显示零 | Passed |
| 来源、储存及稳定商品事实重新校验 | Agent 缓存掩盖当前事实 | Agent 签名来源、Shop 政策与目录 | 18 项 Python 测试及 ruff；PHP、PostgreSQL 负向用例 | draft 规则、规则更新、包装/成分/过敏原变更 | Passed |
| 未开放支付无付款副作用 | 从普通/本地入口付费并整单派送 | PaymentService、WechatPayService | PostgreSQL 集成；普通付款到合成 provider 边界 | 专属订单零意图、零 prepay、零网关；local_test 不可标记 paid | Passed |

PHP 相关单测同时覆盖既有参考来源、原计划配送频次及复合包装库存。PostgreSQL 测试执行实际商城服务及事务，来源回源 HTTP 和支付 provider 使用合成 fixture；未验证生产 Agent 回源、真实支付、供应商派单及微信真机。独立 Reviewer 已检查实现及证据，修复快照身份问题后未发现阻塞项。代码未提交或部署。
