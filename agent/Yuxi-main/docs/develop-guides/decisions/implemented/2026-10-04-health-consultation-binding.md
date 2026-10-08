# 健康成员专属咨询绑定

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_consultation_service.py

## 问题

用户从健康识图页面选择成员后进入专属咨询。普通 Agent 请求只绑定账号和会话，不拥有健康成员及咨询处理用途；模型输入中的成员标识不构成授权。本文面向业务接口、Agent 开发者与 Reviewer，目标是闭合成员绑定与已确认数据读取，不上线自动配餐、诊断或未经审批的真实云调用。

## 决策

健康接口在单一事务创建专属 Conversation 和不可变成员绑定；幂等键绑定账号、成员及操作。专属会话不能换成员，切换成员创建新会话；模型与客户端 metadata 无权改写绑定。绑定、读取及提交咨询均重查成员 grant，管理员没有旁路。

复用 AgentRun 的 FIFO、lease 和 checkpoint，健康咨询使用受限执行后端，固定装配受控业务工具，不装配人工确认、正式档案写入、任意 URL、文件记忆、MCP 或子 Agent。工具以服务端注入的 actor/thread/run 身份查绑定，不接受模型传入身份。通用请求入口和 worker 构图前均核对咨询用途、配置指纹及当前权限；配置未审批时不调用默认模型。咨询同意与报告、饮食识别的同意分开，默认不启用。

本记录拥有成员绑定与两项基础指标、日记读取的边界。当前营养咨询固定装配九项受控工具，名单由 consultation service 与执行后端拥有。[固定 Skill 与审核证据](2026-10-06-health-nutritionist-skills.md)、[成员自述记忆](2026-10-06-health-memory-daily-conversations.md)及[餐后反馈](2026-10-06-health-meal-feedback.md)拥有相应扩展；[本人档案](2026-10-08-family-profile-agent-read.md)、[实测体重](2026-10-08-member-weight-agent-read.md)与[实测血压](2026-10-08-member-blood-pressure-agent-read.md)拥有后续来源读取和失效传播。新增自述写入只作用于私有记忆，不写正式档案。

界面在成员选择区提供入口，明确咨询服务的未配置状态；启用后由用户单独确认咨询处理用途，再创建并导航至绑定会话。已确认指标只投影必要业务字段，不外发原图、OCR 原文证据、姓名或对象地址。档案完整性、专业规则和模型效果仍独立验收。

健康咨询从通用 Agent 的历史记忆读取中永久排除；本地历史、checkpoint 状态、队列内容及 Run 输出重查绑定和当前成员权限。通用管理看板不提供健康咨询详情、逐会话列表或反馈正文。实时 Run 每个载荷发送前重新检查授权。历史工具引用的记录失效时，模型调用明确失败，用户需从健康识图进入新会话，旧上下文不继续用于推断。

专属聊天提交空模型覆盖，由后端选用当前批准模型；普通模型选择器、首条消息的标题模型调用不参与健康会话。健康反馈读取和提交重查成员权限，健康正文、身份及反馈理由不装配 Langfuse 追踪或评分外发。固定成员绑定由健康 Schema version 3 的增量迁移建立，原有健康表与业务记录保留。

## 替代方案

模型传入 member_id 会把对象选择当作可信运行身份。仅在提示词约束授权与工具名单不能阻止替代调用。复用普通 Chatbot 的全部中间件会同时装配文件与其他扩展能力；受限后端保留原 AgentRun 执行框架和服务器固定的业务工具，权限由服务及仓储执行。

## 后果

真实供应商、外发样本和预算未获批准，默认关闭咨询，所有本地验证只使用合成数据和固定响应模型。已确认指标不等于完整健康档案；过敏、适用人群及专业规则没有审核事实时禁止输出个人配餐计划。小程序身份签发仍由业务后端另行确定。成员绑定与受限读取生效不表示专业知识库、完整档案或正式 AI 咨询效果已经验收。

来源失效时，存量历史留在私有持久层，但旧会话不继续推断；用户在健康识图页面重新进入咨询，获取有效记录。撤回授权立即关闭后续受控读取，不静默删除原有记录。管理员通用看板与记忆检索不能承担健康正文管理入口，专门的健康权限入口需要单独设计。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 咨询会话固定成员且同请求唯一 | 迟到响应、换成员重放、跨账号读取 | consultation service / PG binding | `test_health_vision_http.py` 的 consultation 用例，HTTP 与 PG 回读 | 同键换成员、跨账号、管理员、四次并发重放、撤权重放 | 通过 |
| 健康数据只来自已确认且有效来源 | 未确认或失效记录进入模型 | tool executor / health repository | 实际 graph / ToolNode、PG 正式记录和 PostgreSQL checkpoint 回读 | 未确认草稿、来源失效、旧 worker、处理指纹变化、缺少读取权限、伪造工具身份 | 固定合成模型通过；来源失效后第二轮模型调用被拒绝 |
| 专属后端固定装配受控工具 | 空配置扩展为全部工具 | health backend / manifest | `test_health_consultation.py` 的真实构图及 context 准备；独立 worker manifest 回读 | 额外身份参数、确认或正式档案写入工具、资源默认扩展 | 两项基础读取工具及空资源的首次验收通过；当前九项工具的扩展证据由上文各决定拥有 |
| 咨询未审批不发起模型调用 | 静默默认模型、错误用途同意 | request service / model preflight | shipping HTTP 拒绝与 PG 零消息 / Request / Run；逐轮审批 guard | 云未配置、旧政策、错误用途、模型覆盖、无执行 lease | 通过；正式供应商和真实外发效果为 Not run |
| 页面由用户选择成员再咨询 | 迟到绑定跳转错误成员 | health workbench / chat component | Vue 实际脚本、首条发送分支和模型选择行为测试；lint / build；本地关闭状态 DOM | 无授权、切换成员、未知响应重试、错误系统默认模型、普通标题模型 | 30 项前端相关测试通过；真实浏览器正向云咨询为 Not run |
| 存量健康正文不绕过授权进入其他入口 | Memory、反馈、管理看板、已打开 SSE | conversation / feedback / run repositories and services | HTTP、真实 PG 与合成 SSE 同批双载荷 | 通用记忆、管理员详情或反馈、撤权后历史 / 状态 / 输出 / 反馈、撤权后的下一载荷 | 通过；有效历史保留在私有持久层 |
| 健康用途不授权通用云追踪 | 自动 tracing 或评分发送正文与理由 | chat / feedback services | `test_chat_service_langfuse_stream.py` 与 `test_feedback_service.py` | 健康 backend 克隆、已有 trace 标识、错误 fast model | tracing 回调、评分外发及首次标题调用均被排除 |

以下数量保留成员绑定首次交付阶段的实际证据，当前工具扩展与健康 Schema 升级分别由上文链接的决定拥有。

迁移单元 15 项通过，增量 storage-migrator 退出 0，API 与 worker readiness 正常。相关普通 Run、请求队列、聊天、会话审计、反馈、管理看板与 repository 单元 243 项通过；追加的健康 tracing 与相关聊天回归 70 项通过。健康咨询单元 6 项、反馈单元 3 项与完整真实 HTTP 文件 13 项联合通过；咨询专属 HTTP / PG 用例切换到实际 PostgreSQL checkpoint 后 4 项通过，精确清理并回读确认本次 thread checkpoint 不再存在。独立 Reviewer 只读复测 15 项后端、5 项前端，审查范围内无遗留 P1/P2。固定合成模型的真实 API / worker / FIFO / SSE / PG 输出链路通过，命令、证据与撤权排队及正式云未覆盖范围由[端到端决策](./2026-10-04-health-consultation-e2e.md)拥有。
