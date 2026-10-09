# 单成员已保存餐单的安全改版 Agent 预览

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_safe_planner_service.py

## 问题

单成员安全换菜及整份重生成业务已有批准规则、营养复算和用户确认接口，配餐师 Agent 尚不能从用户明确选定的单成员餐单进入该流程。通用草稿模式缺少原餐单与专业来源绑定；家庭模式要求家庭餐单和全体成员，无法覆盖单成员对象。

## 决策

### 实现方案

配餐师复用既有 meal_plan 处理用途与用户确认写入接口，通过 `POST /api/health/v1/members/{member_id}/safe-meal-plan-conversations` 进入固定单成员已保存餐单模式。用户明确提交餐单ID/版本、专业档案版本和规则代码/版本；service 持锁验证所属成员、单成员对象、健康授权、处理同意及当前专业来源。HealthConsultation 的独立 safe_planner_selection 保存严格选择与来源摘要。健康Schema20→21增加可空绑定列和单成员安全预览回执表，已有线程及业务事实保留。

模型只有读取当前上下文、预览安全换菜和预览整份重生成三个工具，身份及版本从服务器绑定取得。候选与重算直接调用现有业务Owner，只有当前attempt能写本Run不可变预览回执。模型最终只选择本Run preview_id或提出补充问题；服务端生成完整权威结果。工具、checkpoint和Message发布重新核对绑定、权限、同意、所有来源与重算结果。预览不写餐单修订、质量决定、采用或饮食；用户确认复用现有安全写入接口。

用户新请求和私有结果、SSE、历史、审计读取核验真实保存的Message、成功ToolAudit、预览回执及当前候选来源。固定选择被删除时，专用回执或旧Run的安全选择摘要仍识别原模式并拒绝退回通用草稿。用户请求接入在写入Request或Message前执行完整历史验证；工具调用继续以原Run的处理摘要校验当前绑定。私有读取由咨询repository授权边界执行，发布由chat事务内最终验证执行。

交付范围是单成员已保存餐单的安全改版Agent只读预览。[餐单页面确认](2026-10-09-safe-planner-web-confirmation.md)拥有Web入口、用户确认与恢复语义。新专业公式、阈值、完整参数语义、小程序、21天计划、采购与真实外部模型质量分别保持待实现或待验收。

## 替代方案

通用草稿工具无法绑定原对象及批准来源。单成员对象直接调用家庭模式违反其实际餐单与参与者契约。复用家庭JSON字段或家庭预览表会混淆持久身份；新增明确绑定和专用回执保留两种模式的独立授权边界，运行、计算、确认与发布流程继续复用现有Owner。

## 后果

专用绑定和回执保留模式身份，复用现有Run、专业业务计算与确认接口；共享请求、checkpoint、私有读取和发布边界均参与校验。当前Run输出只包含经过服务端复算的预览，正式改版仍需要用户明确确认。

完整历史核验随实际消息与回执数量线性增长。同一授权事务通过operation和严格类型参数摘要缓存相同预览，避免重复搜索；SSE每次鉴权仍分别执行核验，缓存不跨鉴权事务。长历史、大规则库及SSE并发的性能预算尚未实测，不能从小型合成用例推断该预算已满足。

开发库迁移保留既有业务事实；备份与隔离回归只证明本地升级和工程行为。生产迁移、真实专业资料与外部模型质量各自需要独立验收。

## 验证

以下测试通过真实装配入口和最终PG状态验证身份、版本、只读预览与拒绝后果；模型使用本地合成协议回放。

| 验证范围 | 直接Owner与oracle | 实际结果 |
|---|---|---|
| 固定成员/餐单/版本、幂等模式、授权与同意 | consultation service/repository；HTTP oracle `backend/test/integration/services/test_health_safe_planner_http.py` | Passed，跨对象、家庭降级、撤权和撤同意均被拒绝；预览期间正式事实保持 |
| 固定三工具、跨轮checkpoint、当前Run回执与迟到发布 | safe planner service/toolkit、chat publication；Worker oracle `backend/test/e2e/test_health_safe_planner_e2e.py` | Passed，实际Run/Message/审计/回执回读；候选更正、Message/审计篡改、绑定丢失后私有入口隐藏，新请求未入队 |
| Schema21幂等升级与旧记录保留 | PostgreSQL manager/models；Schema oracle `backend/test/integration/services/test_health_safe_planner_schema.py`及既有健康迁移测试 | Passed，两本地库正式迁移、catalog/JSONB/操作约束与ready回读；各8张既有表count与整表摘要前后相同 |

完整后端非slow单元命令 `uv run --group test --no-sync pytest test/unit -m "not slow" -q -p no:cacheprovider` 在最终18个生产文件冻结版本上取得3947 passed、59 skipped。跳过项不计入通过。新单成员HTTP/Worker共26个唯一用例分批Passed：首批23通过，伪造preview_id用例误将业务409期望为410导致该命令非零退出；仅修正此错误码oracle后，剩余3项定向通过。既有家庭配餐及初始个人/家庭Worker三项Passed。

健康迁移及迁移unit共59个唯一用例分批Passed。合并命令达到600秒时限并返回124，其中20项已通过，剩余39项另行通过；非零退出命令未记为整批成功，重复运行用例未叠加。所有任务测试schema及隔离合成账号、临时模型审批/provider、非终态Run、lease和排队Request最终回读为零。

guard负控在独立测试进程中恢复目标缺陷，磁盘源码保持不变：完整消息/审计核验解除后10个负向用例变红，模式证据解除后1项变红，共享checkpoint工具限制解除后2项变红，用户请求入口与透传各解除后均1项变红，严格类型版本比较退回普通dict相等后5项变红。均在预期拒绝未发生处失败，修复版本的对应测试通过。37个改动Python文件Ruff与格式检查通过。

Not run：真实外部模型、生产专业规则与完整专业档案、生产部署迁移、长历史与并发SSE性能预算。Web及浏览器证据由[餐单页面确认](2026-10-09-safe-planner-web-confirmation.md)记录。
