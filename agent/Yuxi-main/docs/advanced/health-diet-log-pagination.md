# 分页读取已确认饮食记录

已登录且具有当前成员 `diet_edit` 授权的账号，可读取成员正式饮食记录；管理员同样需要授权。分页是普通业务读取，不创建 Agent Run，不调用模型，不更新快照。

`GET /api/health/v1/members/{member_id}/diet-logs/page?limit=20&offset=0`

limit默认20，范围1至50；offset默认0，范围0至2147483647。非法参数返回422，资源不可见或授权撤回返回404及 `code=not_found`。成功响应禁止缓存：

```json
{"records": [], "next_offset": null}
```

records条目含id、snapshot、created_at和source_version，与原数组条目一致。按确认入库的created_at降序、ID升序排列，日期输出UTC；这不是实际用餐日期的排序。只展示当前来源仍有效的快照。

next_offset是下一批**入库记录**的位置，null表示已到结尾。被删除图片等失效来源不展示，所以不足一页甚至空页仍可能返回非空next_offset。客户端必须使用该位置继续，不能按records.length推进或因空数组停止。上一页按固定limit退回；刷新从offset=0开始。不提供总页数，跨请求新增记录可能改变offset页边界，本接口不是一致快照。

后台“健康识图 → 已确认记录 → 已确认饮食日记”提供20条分页、刷新、重试和单餐反馈。成员变化及撤权会清空私有页，迟到响应不会覆盖当前页。饮食分析来源选择仍使用既有最近100条数组接口 `GET /members/{member_id}/diet-logs`。正式小程序页面由客户端负责人接入。

协议字段由健康路由与DTO拥有，查询由HealthVisionRepository拥有，授权及来源可见性由HealthVisionService拥有。取舍见[分页决定](../develop-guides/decisions/implemented/2026-10-11-health-diet-log-pagination.md)，验证命令见[测试规范](../develop-guides/testing-guidelines.md#饮食记录分页验证)。
