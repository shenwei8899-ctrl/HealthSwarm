# 血糖、血脂与血压独立记录咨询 Agent

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_consultation_service.py

固定工具和科普来源范围由后续[指标专题库决定](./2026-10-20-indicator-topic-knowledge.md)扩展为三工具；本记录保留初始两工具阶段的验收依据。

## 问题

用户要求三个独立 Agent，范围已确认为本人记录回顾、资料追问和审核知识解释。现有独立指标服务具备授权、原始数值投影和来源版本校验，综合咨询尚无三个独立入口。

## 决策

### 实现方案

既有健康任务入口接受 blood_glucose_review、blood_lipids_review 和 blood_pressure_review，分别创建固定本人成员、固定角色的咨询线程。三个入口复用 consultation 用途审批与同意，仅要求 ai_use、profile_view，并检查当前账号拥有本人成员；普通综合咨询保留其既有授权。请求幂等锁先于成员锁，跨角色竞争同键返回明确冲突。每个角色只绑定本类指标读取工具和审核营养知识工具。业务事实继续来自现有 PostgreSQL 服务，执行继续使用 Request、Run、Worker 和 checkpoint。

repository 的教育咨询角色集合拥有权威结果、引用和历史来源重验的覆盖范围；固定技能与 prompt 由咨询服务提供，网页“指标助手”复用任务入口和结果投影，未知响应及5xx重试沿用原入口幂等键。记录缺失时追问，未发布知识不可用于解释；记录更正、作废、撤权或审批变化后停止旧来源发布。临床阈值、诊断、治疗、个体化饮食干预和21天计划不属于这三个记录入口的范围。

## 替代方案

继续仅用综合咨询无法提供用户要求的独立角色与工具边界。复制三套数据和运行服务会产生重复授权与版本语义，因此复用现有服务，仅增加角色及入口。

## 后果

三类记录通过独立线程和两个固定工具隔离，角色目录以限定记录能力的部分完成状态呈现。原控糖管理的21天计划、打卡和审核规则继续保留为未交付范围。完整健康档案交付状态不因角色增加而改变。

普通解释的发布与读取边界由[健康解释校验后公开](./2026-10-13-health-validated-publication.md)拥有：执行中只公开固定进度，正文在校验与事务提交后由权威结果读取。真实模型质量与专业知识生产数据仍需独立验收，确定性回放不证明临床能力。

资料范围由[审核科普使用范围决定](./2026-10-13-health-evidence-reviewed-scope.md)拥有：三个指标角色只取得显式登记本领域、通用且无排除条件的片段；历史未登记范围的资料仅供原普通咨询。现有固定工具及本人记录回顾范围不因此扩展为个体化干预。

## 验证

隔离真实HTTP、ARQ Worker、SSE及PG回读共7项通过，包括三个指标的记录、审核引用、更正与作废失效、新线程恢复、知识撤回及空记录；其他指标与档案的Run回执不存在。本人最小权限可创建，非本人和缺档案权限被拒且无新增任务事实；跨角色同键并发仅生成一个线程，另一个返回请求冲突。测试由[独立指标E2E](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/test/e2e/test_health_indicator_agents_e2e.py)和[任务HTTP测试](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/test/integration/services/test_health_task_http.py)拥有，并接入既有隔离回放门禁。

固定上下文、角色与技能发现、能力提示等58项单测，以及指标授权和回放32项单测通过；公开历史、失败发布、引用与搜索86项定向单测通过。前端19项定向测试、lint与build通过。工程契约检查、其63项单测、相关Ruff检查、文档构建及diff检查通过。

Not run：真实供应商模型质量与生产审核知识验收。完整网页单测因既有慢用例中止；合成账号登录后的健康页浏览器导航发生CDP超时，页面视觉验收未完成。这些范围独立于已验证的服务与组件结果。
