# 健康角色入口、取消读取与识别重试边界

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/repositories/agent_run_repository.py

## 问题

健康运行的取消响应绕过成员授权，返回已被读取接口隐藏的完整运行。普通智能体入口能创建没有成员绑定的健康线程，随后主请求失败；结构化健康角色的首条输入还会进入普通标题模型。识别重试在未知响应后更换幂等键，能够重复创建云任务。确认弹窗期间成员选择仍可变化，使旧成员草稿回填到新成员视图。

## 决策

### 实现方案

运行取消授权由本记录 Owner 负责；普通线程创建边界由 `conversation_service` 负责，成员入口、重试和确认视图由 `AgentView`、`AgentChatComponent`、`HealthVisionView` 负责。

取消用例先锁定属于当前账号的 Run，再对健康角色执行当前成员与来源授权的锁定校验，授权成功后才允许修改或响应投影。锁顺序沿用运行发布的 Run → 成员顺序。普通线程创建服务拒绝健康角色，前端选择该角色引导用户从健康工作台绑定成员；所有健康角色均采用后台批准模型和固定标题。首次默认选择只考虑普通角色，已有绑定线程仍显式加载其健康角色。已有健康角色切到空白新对话时禁止发送，并展示成员入口。

识别重试按父任务保存未知请求键，未知响应、列表回读失败以及成员或用途来回切换均保留原键；仅在同成员同页面代次下成功回读后释放，组件卸载时清理。确认弹窗禁用成员选择，并在提交与回填时检查原成员和页面代次。最终授权与草稿成员身份仍由服务端负责。

## 替代方案

取消保持整 Run 响应而只隐藏前端字段不能关闭 HTTP 旁路。普通入口自动选择成员会扩大代理与用途同意范围。以新键重试能够把未知响应变成第二个付费任务。仅禁用成员选择不能阻止迟到响应回填，须同时保留请求上下文检查。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 撤权后取消接口不返回健康 Run | 锁定路径跳过读取授权 | agent_run_repository.lock_run_for_user | test_health_vision_http.py::test_consultation_private_history_memory_dashboard_and_sse_recheck_revocation | 撤回 grant 后取消返回 404，无错误详情或状态修改 | HTTP / PG 通过 |
| 健康角色由成员入口创建线程 | 普通入口创建孤儿线程或外发标题 | conversation_service、AgentView、AgentChatComponent | test_health_vision_http.py::test_plain_thread_creation_rejects_health_roles_before_any_persistence；healthAgentEntry / conversationModelBinding / agentInitialization 测试；test_health_entry_ui.py | 四角色普通建线程均拒绝且数据库无行；四角色模型为 null，首条标题调用为零；普通角色保持原行为；浏览器从普通角色选择跳转到工作台，PG 无 Conversation 行 | HTTP / PG / Vue / 真实浏览器通过 |
| 未知识别重试复用请求键 | 响应断线后重复创建云任务 | HealthVisionView | healthVisionView.test.js 的实际页面状态和重试按钮测试 | 未知响应、回读失败、成员 / tab 来回导航以及列表迟到后均为同键 | Vue 通过 |
| 确认保留原成员上下文 | 弹窗切换或迟到响应展示错成员 | HealthVisionView | healthVisionView.test.js 实际模板与确认回调；test_health_entry_ui.py 的浏览器及 PG 夹具 | 确认期间禁用成员选择；成员变更或卸载后不提交或回填旧草稿；PG 仅原成员一条正式记录 | Vue / 真实浏览器 / PG 通过 |

### 实际结果

2026-10-08：上述两项真实 HTTP / PostgreSQL 用例 2 passed；共享 Run / checkpoint / conversation 回归 142 passed；相关前端组合 37 passed、0 failed、0 skipped，随后追加迟到列表负控的健康页面单文件 24 passed、0 failed、0 skipped。六个相关 Python 文件 Ruff check / format check 通过。

真实浏览器最终 r5 用例 1 passed（69.36 秒），浏览器脚本 exit 0，PG 回读确认仅原成员一条 HealthObservation、草稿 confirmed v1、无普通健康 Conversation。此前四轮环境重载或脚本定位失败均未计通过。测试使用独立合成账号、两个成员和人工报告草稿，不修改全局健康配置；fixture 退出时按精确外键完成清理。

本地证据为 `agent/.tmp/github-submit-20261008/health-entry-ui-r5.log`、`health-entry-browser-r5.log`；控制目录为 `backend/test/.tmp/health-entry-ui-20261008-r5/`，包含 done / verified 回执及三张截图。共享单测与前端日志在 `agent/.tmp/backend-core-review-unit.log`、`health-entry-review-web.log`、`health-vision-review-final.log`。这些临时证据不提交。

实现者自审及独立 fresh reviewer 均复核当前四处修复的服务端边界、普通角色兼容性和异步回填，没有未解决的生产阻断项。全量后端、前端及提交门禁由主任务统一执行，不能以本记录的定向检查替代。

## 后果

来源失效或成员撤权后用户不能通过取消接口访问运行；Worker 仍在模型和工具边界重新检查授权。外部真实模型、完整专业营养安全与生产环境迁移不属于本修复验收。
