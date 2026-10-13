# 固定 Agent 建会话成功响应契约

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_fixed_conversation_types.py

## 问题

后台通过普通配餐、饮食分析、明确选餐反馈和已保存餐单安全改版四个入口建立固定健康会话。客户端需要从 OpenAPI 获取实际角色和来源选择，并区分未选择目标与实际选定目标。普通咨询响应限定营养师角色且反馈为空，无法表达这些入口。

## 决策

### 实现方案

[固定会话响应 DTO](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_fixed_conversation_types.py)复用现有基础响应和个人目标、选餐、安全改版选择类型。[健康路由](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/server/routers/health_vision_router.py)对四个既有入口声明固定角色的 201 response_model；响应禁止额外字段，所有来源选择保留原版本约束。

普通配餐返回 `health-meal-planner`；普通分析返回 `health-diet-analyst`，未选择目标时省略 `target_selection`，已选择时返回批准规则与档案版本。选餐反馈必须返回非空 `feedback_selection` 的确认记录 ID 和来源版本。安全改版必须返回非空 `safe_selection` 的餐单 ID/版本及批准规则、档案版本。四项 `business_date` 均为 null，选餐反馈之外的 `feedback_selection` 均为 null。

[会话 service](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_consultation_service.py)与 repository 继续拥有授权、不可变来源绑定和幂等事务；[反馈 service](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_dialog_feedback_service.py)先解析用户选择的确认餐次再建立会话。四项使用请求正文 `client_request_id`，路由不要求额外 `Idempotency-Key` 或 `If-Match` 头。创建产生 Project、Conversation、HealthConsultation，反馈另有来源绑定；执行仍由客户端显式提交 Agent 请求。

## 替代方案

仅在交接文档描述字段无法提供运行时响应校验。直接复用普通咨询模型会拒绝实际角色和选餐来源；默认值为 null 的可选目标会给未选择目标的响应增加字段。无约束字典无法检查来源选择，因此分析使用两种合法响应形状，其他入口使用各自确定形状。

## 后果

响应类型独立装配，避免现有选择类型依赖 HealthDTO 时在基础 DTO 模块引入循环导入。业务接口、后台消费者、授权和事务边界保持既有职责。响应校验在业务事务提交后执行，无法替代授权或回滚已经提交的事实；非法业务返回会使响应失败，幂等重放仍由 service 负责。

该决定覆盖四个成功响应的发现与校验。其他会话模式、完整错误协议、并发写入、Worker 和真实模型执行、专业质量、自动协调及正式 App/微信页面验收沿用各自交付范围。

## 验证

[响应 unit](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/test/unit/services/test_health_fixed_conversation_contract.py)独立使用字面量 schema 和 wire oracle：38 项通过，包含四个 OpenAPI 操作、五种成功形状及 28 种非法角色、字段、UUID、空来源、错误版本和私有字段返回。移除四个 response_model 的进程内负控产生预期 33 项失败；错误添加默认 null 目标产生预期 3 项失败，分别由 schema、原 wire 与空来源拒绝断言定位。负控不修改生产文件或配置。

[真实 HTTP/PG integration](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/test/integration/api/test_health_fixed_conversation_contract_http.py)在既有隔离槽位执行 7 项，全部通过，无跳过。验证五种实际成功响应、同键重放、跨成员/角色复用、目标和餐单来源版本变化、跨账号与撤权拒绝；回读实际持久化来源及失败后的写入数量。每项 AgentRunRequest、AgentRun、Message 均为零；原配置、五个 Agent、五个 Skill 精确恢复，临时 provider 删除，按既有 scope 回读的 76 张关联表中本轮合成账号所属记录均为零。

```bash
docker exec -e LANGFUSE_ENABLED= -e LANGFUSE_PUBLIC_KEY= -e LANGFUSE_SECRET_KEY= -w /app health-diet-analysis-e2e-api-1 uv run --no-sync --group test pytest test/unit/services/test_health_fixed_conversation_contract.py -q -p no:cacheprovider
docker exec -e TEST_BASE_URL=http://localhost:5050 -e HEALTH_CONSULTATION_E2E_ISOLATED=true -e HEALTH_CAPABILITIES_RECEIPT_DIR=/tmp/health-fixed-conversation-contract-20261013/receipts-full -e LANGFUSE_ENABLED=false -e LANGFUSE_PUBLIC_KEY= -e LANGFUSE_SECRET_KEY= -e LANGFUSE_HOST= health-diet-analysis-e2e-api-1 uv run --no-sync --group test pytest test/integration/api/test_health_fixed_conversation_contract_http.py -q --tb=short --junitxml=/tmp/health-fixed-conversation-contract-20261013/02-full-junit.xml -o cache_dir=/tmp/health-fixed-conversation-contract-20261013/pytest-cache-full
docker exec -e LANGFUSE_ENABLED= -e LANGFUSE_PUBLIC_KEY= -e LANGFUSE_SECRET_KEY= -w /app health-diet-analysis-e2e-api-1 uv run --no-sync --group test pytest test/unit -m "not slow" -q -p no:cacheprovider --durations=8
python scripts/verify_engineering_contracts.py
python -m unittest scripts.test_verify_engineering_contracts
```

全量后端 unit 为 4507 passed、59 skipped；其中已包含上述 38 项。信任检查及其 63 项单测通过。主服务实际 OpenAPI 声明四个 201 响应，未登录的四种请求均返回 401。专业来源使用合成 fixture，未执行模型、Worker 或正式客户端验收。
