# 专属计划独立发布预览

状态：proposed
类型：feature
Owner：backend/package/yuxi/services/exclusive_plan_service.py

本提案的价格递增、完整采购前置条件及首日商品预览由[专属菜单与采购资料分离](../implemented/2026-11-16-exclusive-menu-procurement.md)取代；以下保留原提案以说明原有取舍，不构成当前验收要求。

## 问题

商城经营配置和交易回执阻塞了家庭菜单预览。

## 提案

后台生成和读取使用 Agent 规则。任务固定一份真实商品快照并逐日核算商品包装，三档食材预估顺序严格递增后发布。用户读取授权范围内的菜单和首日食材。历史交易仍使用原签名凭据。

## 替代方案

继续依赖商城计划配置需要在菜单可用前确定完整结算规则。

## 风险

候选和真实价格覆盖不足时可能无法组成三档。估价口径为每日核算所需包装，再合计 21 天。

## 验收标准

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 核价按同一快照、实际包装数量且顺序严格递增 | 缺价或同价被当作可发布 | exclusive_plan_generation | test/unit/services/test_exclusive_plan_prices.py | 缺价、同价、按单包价误排序 | Passed |
| Worker 生成并原子发布三档各 21 天 | 重排更换快照、未验价数据可读取 | exclusive_plan_tasks | PostgreSQL 与 Worker 联调 | 缺价或同价仍发布 | Not run |
| 授权用户可读取自己已发布的菜单 | 串家庭、未完成预览泄露 | exclusive_plan_service | HTTP 集成测试 | 非本人、未完成 | Not run |
