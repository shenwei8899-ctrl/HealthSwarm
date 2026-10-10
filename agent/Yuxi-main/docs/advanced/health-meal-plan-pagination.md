# 分页读取成员餐单草稿

面向接入餐单业务的客户端开发者。登录后调用 `GET /api/health/v1/members/{member_id}/meal-plans`，读取当前账号维护的成员餐单。列表返回已保存草稿的当前版本快照，专业批准和正式采用分别沿用原业务接口。

## 读取分页

| 参数 | 默认值 | 有效范围 |
|---|---|---|
| `limit` | `50` | 整数 `1` 至 `50` |
| `offset` | `0` | 整数 `0` 至 `2147483647` |

响应保留 `plans` 和 `truncated`，增加 `next_offset`。`plans` 最多包含 `limit` 份；`truncated=true` 时使用返回的 `next_offset` 继续读取，末页返回 `truncated=false`、`next_offset=null`。无记录或偏移超过当前记录数时返回空列表。无效查询参数返回 `422`。

```http
GET /api/health/v1/members/{member_id}/meal-plans?limit=50&offset=0
GET /api/health/v1/members/{member_id}/meal-plans?limit=50&offset=50
```

每次请求按 `updated_at DESC, id ASC` 排序，读取当前数据库事实。餐单新增、保存或换菜可能改变排序位置；刷新时从 `offset=0` 重新开始，不能把不同请求视为固定快照。接口不返回总数。

每页重新检查主成员的 `diet_edit` 授权，仅查询当前账号与该成员的餐单；管理员角色也需要授权。读取到的家庭餐单还检查每位参与者的当前授权，额外读取的后续页标记行同样受检。授权变化可能拒绝整个请求，客户端清除旧页及相关私有详情并提示重新确认授权。列表查询不调用 Agent，不修改餐单、修订、审核或采用。

现有后台入口为“健康识图 → 餐单草稿”。每页固定 50 份，通过“上一页”“下一页”查看早期草稿。翻页保留已选餐单的详情与历史；选择框只显示当前页的条目。刷新、保存、换菜后重新读取首页；切换成员或授权变化清除旧内容，迟到响应不能回填新选择。

请求协议由[健康路由](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/server/routers/health_vision_router.py)拥有，排序和权限由[餐单 repository](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/repositories/health_meal_plan_repository.py)拥有。边界验证见[测试规范](../develop-guides/testing-guidelines.md#餐单列表分页验证)，取舍见[分页决定](../develop-guides/decisions/implemented/2026-10-10-health-meal-plan-pagination.md)。正式小程序可使用同一协议接入分页，页面交付由客户端负责人完成。
