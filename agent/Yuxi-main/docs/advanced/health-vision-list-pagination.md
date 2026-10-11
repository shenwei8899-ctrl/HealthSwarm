# 分页读取OCR任务和复核草稿

已登录账号具有当前成员的report_view授权时读取报告用途，具有diet_edit授权时读取饮食用途。管理员同样需要成员授权。普通分页不提交识别、重试或确认，不调用模型，不改变任务、草稿及正式健康记录。

`GET /api/health/v1/members/{member_id}/vision/page?kind=report&jobs_limit=20&jobs_offset=0&drafts_limit=20&drafts_offset=0`

kind必填，取report或meal。jobs_limit和drafts_limit各默认20、范围1至50；jobs_offset和drafts_offset各默认0、范围0至2147483647。非法参数返回422；成员不可见或请求用途无权返回404及code=not_found，包括空页和越界页。成功响应禁止缓存：

```json
{"jobs": [], "drafts": [], "jobs_next_offset": null, "drafts_next_offset": null}
```

jobs使用既有任务摘要，执行状态、进度和取消意图来自TaskRecord，复核状态来自关联草稿；不包含内部输入、原始错误正文或租约。drafts使用既有草稿投影，包含候选内容、版本、复核状态、模型和解析版本。草稿列表包含待复核、已确认等原有状态，列表读取不完成专业复核。

两侧在数据库中先按成员及kind筛选，再各按created_at降序、id升序分页。next_offset指向该种类的下一批入库行；失效图片派生的任务或草稿被过滤后，中间页可以不足一页或为空。客户端分别使用jobs_next_offset和drafts_next_offset继续，不能按可见数组长度推进或因空数组停止。null表示对应列表结束。不返回总页数，并发新增可改变跨页边界；本接口不是一致快照。

后台健康识图的“健康报告”和“饮食照片”分区分别提供识别任务和复核草稿两个分页面板，每页最多20条。单侧翻页保留另一侧位置；成员或用途切换、显式刷新和新建成功回到首页。可见且已授权的OCR分区在不忙时每3秒刷新当前两页，列表刷新保留正在编辑的草稿。任务完成后用户点击“打开草稿”；详情仍由独立接口读取。读取失败可重试本页；403/404清除私有列表及当前详情，迟到响应不会回填上一成员或用途。

原 `GET /members/{member_id}/vision` 保留jobs和drafts两个最近50条数组，供已有消费者兼容。正式小程序由客户端负责人接入分页接口。协议由健康路由与VisionListPage拥有，查询由HealthVisionRepository拥有，授权及来源有效性由HealthVisionService拥有。取舍见[分页决定](../develop-guides/decisions/implemented/2026-10-11-health-vision-list-pagination.md)，命令见[测试规范](../develop-guides/testing-guidelines.md#ocr任务与草稿分页验证)。
