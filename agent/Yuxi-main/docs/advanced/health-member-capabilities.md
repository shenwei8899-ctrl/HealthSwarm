# 查询成员的任务入口状态

面向接入健康业务的客户端开发者。登录后调用 `GET /api/health/v1/members/{member_id}/capabilities`，读取当前账号、成员和任务用途的入口状态、阻断原因及所需选择。查询结果用于展示入口提示；提交任务、执行工具和发布结果各自重新检查当前权限及业务来源。

## 读取状态

接口使用登录账号已有的有效成员授权。不可见、不存在、撤回和空授权成员统一返回 `404 not_found`；管理员角色也需要成员授权。可见成员的响应包含 `member_id`、`tasks` 和 `dependencies`，并使用 `Cache-Control: no-store`。

每个任务返回 `task_type`、`purpose`、`status`、`reason_code`、`configuration_reason_code`、`missing_scopes` 和 `required_inputs`。字段的可选值与任务分类由[响应协议](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_capability_types.py)和[任务入口选择](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_task_types.py)拥有。

| 状态 | 客户端含义 |
|---|---|
| `available` | 当前授权、固定角色与内置 Skill、用途审批和处理同意满足已实现交互入口条件 |
| `needs_input` | 公共入口条件满足，用户还需选定 `required_inputs` 描述的业务对象 |
| `unavailable` | 当前公共条件未满足，或任务需要外部未交付的契约 |

普通咨询、非个体化配餐草稿和饮食分析分别检查自己的前置条件。初始配餐、家庭改版、安全改版、质量检查和采购净需求需要明确选择；客户端提交选择后，原业务服务检查选定来源、版本和其他参与者。入口可用不能证明个体化方案已获专业批准、真实模型效果或商城下单可用。

`required_inputs` 中的 `selection.*` 对应任务入口的选择字段。`interaction.inventory_confirmation` 提示客户端通过业务入口取得用户库存确认，在采购选择中提交 `inventory_confirmed` 和 `inventory`；已创建采购线程的选择固定，需要调整时使用新的 `client_request_id` 创建采购线程。`interaction.confirmed_meal_or_period` 提示饮食分析范围，可通过现有分析 Agent 交互明确。客户端按各任务的选择模型组装请求。

## 处理阻断原因

`missing_scopes` 只列出当前可见成员、本账号缺少的任务授权。客户端根据 `reason_code` 提示用户补充授权、配置角色或 Skill、处理用途审批、更新处理同意或完成选择；`external_contract_required` 保持待对接状态。

`configuration_unavailable` 通过 `configuration_reason_code` 区分政策未审批、模型未就绪和处理配置审批失效等原因。配置检查复用[健康用途配置 Owner](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_vision_service.py)产生的原因码。处理同意必须属于同一账号、成员和用途，并匹配当前处理方及政策版本。配置或授权变更后重新查询，再以实际业务提交响应处理变化。

## 阅读最小依赖摘要

`dependencies.profile_projection` 仅在具备 `profile_view` 时读取当前最高安全来源，返回状态、原因和版本；未授权时返回 `not_authorized`。该投影不表达完整专业健康档案已经交付，也不返回指标、档案内容或证明。`published_recipes` 只表示已发布菜谱目录存在记录，不能判断专业适用性；`rules` 保持待明确选择的状态。

该 GET 只读取入口事实，不创建项目、会话、Request、Run、预览、审核或采用，不写健康访问审计，也不触发来源失效修复。本接口使用的 `HealthGrant` 和 `HealthProcessingConsent` 没有期限字段，客户端仍须遵循各业务服务的当前授权检查。实现与验证边界见[只读汇总决定](../develop-guides/decisions/implemented/2026-10-10-health-member-capabilities.md)；运行排障见[家庭营养 Agent 运维](./health-agent-operations.md)。

## 按业务依赖降级入口

客户端调用 `GET /api/health/v1/members/{member_id}/readiness`，读取同一成员的 `capabilities`、`runtime`、`catalogue`、`role_versions` 和 `entries`。认证、成员可见性及 `no-store` 规则相同。`entries` 提供任务、照片识别与人工录入的独立状态，`missing_dependencies` 列出当前阻断依赖，`configuration_reason_code` 区分照片用途的模型或 OCR 缺项；具体协议由[诊断 DTO](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_readiness_types.py)拥有。

`runtime` 复用平台 PostgreSQL、Redis 和兼容 Worker 的探针，增加对象存储签名只读访问检查。核心探针沿用一秒短缓存；对象存储使用当前配置、有界连接与读取超时，不创建桶或写入对象。探针成功只证明当前只读访问，上传、执行和结果发布仍由实际操作确认。数据库不可用时无法证明成员可见性，使用平台 ready 排障，不返回成员目录摘要。

普通咨询和确认事实分析保持各自条件；对象存储故障只影响照片入口。配餐目录缺失或专业方案缺安全投影、有效规则时，相关入口返回 `unavailable`。`catalogue` 的营养、最新有效规则和已映射审核知识布尔值仅表示目录存在；明确选择、适用范围、内容完整性、营养重算和当前版本仍由业务 Owner 校验。审核知识目录为空时，普通咨询仍可追问和读取已授权事实，正式知识引用按实际检索结果返回。

`role_versions` 核对内置 Skill 发布源码与 PostgreSQL 登记的版本和内容哈希；不一致时只标记对应角色的 `role_version` 缺项。该摘要不证明全部 Worker 已部署相同版本。用户需要明确选定来源的入口保持 `needs_input`，客户端按 `complete_selection` 引导完成选择。

客户端隐藏或禁用 `unavailable` 入口，并仅展示 `allowed_actions` 给出的人工报告、人工饮食、补充选择或重试。人工路径依赖自己的成员授权及数据库，不能通过开放聊天替代缺失的专业能力。健康任务创建在运行依赖不可用时返回 `dependency_not_ready`、`runtime_dependency_unavailable` 和 `missing_dependencies`，不创建线程；已创建线程的提交、执行和结果发布继续使用现有门禁。诊断是当前快照，客户端必须处理操作时返回的新错误。决定与验证见[业务就绪诊断](../develop-guides/decisions/implemented/2026-10-11-health-business-readiness.md)。
