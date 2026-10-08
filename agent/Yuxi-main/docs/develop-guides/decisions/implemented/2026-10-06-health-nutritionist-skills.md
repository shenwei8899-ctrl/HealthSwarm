# 健康营养师的固定 Skills 与审核证据

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_consultation_service.py

## 问题

成员咨询已有授权和已确认记录读取，缺少固定业务 Skills、红阳档案能力边界和可撤回的审核知识引用。用户要求在现有 Agent 上逐批完成角色、Skills 与接口，保留原数据与身份架构。

## 决策

health-consultation 和 HealthConsultationAgent 固定预加载随代码发布的 family-nutritionist 内置 Skill，其内容包含营养师流程、档案边界和引用质量约束；发布与启停由[家庭营养师 Skill 决策](2026-10-06-family-nutritionist-builtin-skill.md)说明。后端复用既有成员授权、Run、worker 和 checkpoint。完整档案接口由红阳提供，未接入时返回结构化未就绪。管理员通过 nutrition-evidence 接口登记已经专业审核的通用科普片段、来源版本、审核凭据与有效期；修订发布新片段，原片段仅可撤回。

health_evidence_repository 拥有 PG 检索和引用归属，health_evidence_service 拥有发布、撤回与用例事务。检索使用转义的短关键词，只返回最多五个有效片段；每次检索重查成员、处理同意和执行 lease，并写入运行引用回执。构图和每次模型调用核对历史来源，最终答复引用须来自本轮运行。Skills 不扩展个人文件、通用 KB、MCP 或任意工具。agent-roles 接口展示七个业务角色的实际实现范围，待实现角色不发布为可运行预设。

## 替代方案

七个独立执行引擎会重复权限与生命周期管理。通用知识工具不能保证专业审核或运行引用归属。仅以提示词约束引用不能验证来源状态。本阶段采用一个健康执行后端和服务端证据校验，其余角色保持待实现的边界说明。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 固定工具和 Skills 不扩权 | 模型／工作区输入 | graph、consultation service | 实际图 unit | 伪造成员和额外工具 | Passed |
| 档案未接入不伪造数据 | 工具协议 | health toolkit | unit | 不能把指标当完整档案 | Passed |
| 审核证据引用可追溯、可撤回 | HTTP、PG、worker | evidence repository/service | HTTP integration、咨询 replay E2E | 普通用户发布、来源撤回、跨运行伪造 | Passed |
| Schema 增量迁移保留记录 | PG migration | storage migrator | migration unit、真实 PG | 版本 3 升级且重复执行 | Passed |

定向验证使用真实运行容器中的 python -m pytest：咨询、重放、营养师、迁移及 schema 五个 unit 文件 73 项通过；角色发现 13 项通过；健康 HTTP integration 19 项通过；独立 Compose 中营养证据与原咨询 FIFO 两项 worker E2E 通过。营养证据 E2E 回读发布版本、引用回执、Message 和 Run，覆盖普通用户发布／撤回拒绝、过期与撤回片段排除、通配符字面检索、正文篡改、跨账号／成员／运行引用拒绝、模型最终伪引用导致 failed，以及撤回历史在外呼前终止。原咨询运行 manifest 的四个固定工具名单使用显式 oracle 更新。

工程契约检查及其 62 项 unittest、pnpm --dir docs run build、修改范围 ruff check 和 format --check 通过。全量 unit 命令曾运行但未完成，发现的三处健康角色发现旧断言已修正并通过定向验证；全量结果不作为通过证据。uv run 的依赖同步在非 root 容器中受到安装路径权限限制，定向测试使用镜像内已安装的 python/pytest，格式检查使用宿主 ruff。

## 后果

审核质量依赖管理员登记的专业审核凭据，系统不推断管理员具有临床资质。证据库初始为空，匹配不到证据时明确报告不足。引用检查证明校验时刻的归属与来源有效性，不承担自然语言临床断言审核，也不与 Run 终态提交构成同一事务。模型文本按既有流式协议先输出；最终引用拒绝使运行 failed，已流出的部分文本保留为 is_error 消息。[成员记忆与每日对话](2026-10-06-health-memory-daily-conversations.md)扩展营养师的自述读写、管理和消息摘录范围；[单餐反馈](2026-10-06-health-meal-feedback.md)拥有餐次关联、管理撤回和联合历史过滤；配餐、控糖、采购与红阳完整档案仍有独立实现和联调工作。
