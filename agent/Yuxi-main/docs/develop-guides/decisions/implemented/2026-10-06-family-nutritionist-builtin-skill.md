# 家庭营养师 Skill 的发布与固定预加载

状态：implemented
类型：feature
Owner：backend/package/yuxi/agents/skills/buildin/family-nutritionist/SKILL.md

## 问题

用户要求补齐家庭营养师 Skill。营养咨询已有固定提示片段，平台 Skills 目录尚未发布对应技能，运行清单也没有技能身份与版本。目标是让管理员能在 Skills 列表查看完整业务流程，且成员营养咨询实际加载同一份内容。

## 决策

family-nutritionist/SKILL.md 是家庭营养师流程的唯一内容 Owner，声明中文名称、版本和健康工具依赖，覆盖咨询分流、已确认数据读取、科普证据检索、成员自述记忆、缺资料处理、回答格式和业务边界。平台沿用内置发现与同步；health_consultation_service 使用发布源码冻结提示与运行快照，Context 固定预加载该技能，manifest 保存版本、目录 hash 和预加载内容 hash。个人同名覆盖和任意技能依赖不参与健康装配。餐后反馈读取及撤回传播由[单餐反馈决策](2026-10-06-health-meal-feedback.md)拥有。记忆及每日会话的持久化、失效传播和验证由[成员记忆与每日对话决策](2026-10-06-health-memory-daily-conversations.md)拥有。

平台 Skill 索引拥有启用状态，require_consultation 在成员授权和用途同意通过后要求该索引存在、属于 builtin 且已启用。提交、构图及每次模型和工具调用共用此检查，停用时返回 nutritionist_skill_unavailable；不回退到个人版本或无 Skill 提示。既有授权、审核证据与引用校验沿用[营养师后端决策](2026-10-06-health-nutritionist-skills.md)。

## 替代方案

只扩充原 Markdown 片段不能让平台发现 Skill。直接使用通用技能装配会允许个人同名覆盖并扩大工具依赖。采用原生内置发布和受限健康执行组合，保持同一个内容 Owner。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 平台发现 Skill 及发布声明的工具依赖 | 内置发现、HTTP | Skill service | discovery unit、真实 Skill 列表读取 | 固定快照不调用个人技能解析 | Passed |
| 固定 Skill 内容进入营养师模型输入与 manifest | worker 装配 | consultation service | 实际图 unit、worker E2E | 用户任意技能、提示不能扩大名单；重放模型拒绝缺失 Skill 内容 | Passed |
| 平台停用阻止咨询执行 | HTTP、PG、模型授权入口 | Skill index、consultation service | 状态矩阵 unit、管理员停用后的真实 HTTP | 停用后 503 且没有 Message、Request、Run；恢复启用后 worker 正常执行 | Passed |
| 既有权限与引用约束保持有效 | 工具、模型最终输出 | health graph | 营养证据及咨询 E2E | 伪引用与来源撤回仍拒绝 | Passed |

运行容器中的 python -m pytest 定向咨询、营养师、发现及 manifest 四个 unit 文件 56 项通过；重放与技能运行时两个 unit 文件 29 项通过。独立 Compose 中原咨询 FIFO 和营养证据两项真实 worker E2E 通过，重放模型读取实际协议中的完整 Skill 标记，运行 manifest 与 HTTP 发布内容及 PG 索引版本核对。引用负向用例回读 failed Run 和 is_error Message。以上测试覆盖装配和执行协议，未运行外部临床模型质量评估或全量 unit。

工程契约检查及其 62 项 unittest、pnpm --dir docs run build、修改范围 ruff 检查和格式检查、git diff --check 通过。独立复核检查完整需求、装配路径、工具契约、版本快照和平台停用行为，未发现待修复项。

## 后果

家庭档案服务提供已确认原始档案，家庭营养师通过[本人档案接入](2026-10-08-family-profile-agent-read.md)消费显式关联的本人版本，并维护当前账号的成员自述记忆；完整专业安全语义和多人模型处理同意独立待验收。业务流程文本的装配验证不证明真实模型医学回答质量，临床判断仍依赖专业审核知识。Skill 在通用未绑定会话中没有健康数据权限。发布源码更新后需重新加载 API 和 worker，保证进程冻结的提示与快照更新；平台启用状态则在每次授权检查时读取。
