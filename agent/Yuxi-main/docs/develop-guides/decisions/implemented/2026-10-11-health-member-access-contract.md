# 成员与用途同意响应契约

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_vision_types.py

## 问题

后台及账号密码联调工程通过现有健康成员、授权和用途同意接口准备 Agent 咨询。四个成功响应缺少 OpenAPI 字段定义，客户端无法据此区分成员裸数组、建档 ID、授权保存结果及明确的同意或撤回结果。补充响应校验需要保留已有形状和访问边界。

## 决策

### 实现方案

现有[健康类型模块](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_vision_types.py)定义成员摘要、建档结果、授权保存结果及用途同意结果 DTO，由 [health 路由](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/server/routers/health_vision_router.py)的 GET/POST members、PUT member grants、POST member processing-consents 四个现有入口声明响应模型。成员读取保留裸数组、空数组及 scopes 顺序；创建仅返回 id；授权保存固定返回 saved:true；用途同意保留 accepted:true/false。四种输出拒绝缺字段、错误形状及额外字段。

现有 HealthVisionService 和 HealthVisionRepository 继续拥有成员事实、授权、用途处理配置及事务。建档每次创建新 ID；修改授权仅允许当前 Owner，健康字段授权及管理员身份不能替代 Owner；授权及同意更新当前槽位。用途接受验证当前处理方、政策和可用性，撤回可以使用旧政策，但两者均要求当前 ai_use 授权。四个操作没有 client_request_id、Idempotency-Key 或 If-Match 要求，也不创建 Run、Request 或模型调用。

后台 HealthVisionView 继续消费成员数组及建档 id，用途同意返回的布尔值明确区分接受与撤回。四种 DTO 描述现有健康成员边界；正式 App、微信身份、专业档案、数据库迁移、Worker 或生产模型验收由既有 Owner 处理，客户端对接范围见[项目交接](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/docs/家庭营养师-Agent交付与待对接.md)。

## 替代方案

人工交接表无法为 OpenAPI 消费者提供字段定义。将成员数组包装为分页对象会改变现有后台及联调工程的消费方式。用家庭档案输入类型代替健康成员输出会混合两个身份及授权 Owner，故保持现有健康边界。

## 后果

响应校验位于现有业务事务提交之后，不能反向替代写入 Owner 的事务或授权检查。建档没有新增安全重放承诺；用途接受仍验证当前处理方、政策和可用性，撤回仍要求当前 ai_use 授权。验证使用合成账号和独立测试环境，配置及资源恢复必须直接回读。

## 验证

[响应契约 unit](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/test/unit/services/test_health_member_access_contract.py)使用实际四个路由及独立字面量 oracle；26 项涵盖 OpenAPI 必需字段、成员数组和 scopes 顺序、撤回 false，以及 14 种非法服务返回。与前序本人关联及咨询响应测试一同执行，48 passed。主服务实际 OpenAPI 回读四个 schema 及 required 字段通过，四个匿名请求均为 401。

两个独立 Python 进程仅修改内存中的路由响应模型：移除四个 response_model 后，4 个 schema、1 个字段定义及 14 个非法响应 guard 按正确原因失败（19 failed / 7 passed）；把 accepted 错限为 Literal[True] 后，schema 和实际撤回 false 失败（2 failed / 24 passed）。负控程序验证预期失败的节点及原因后成功退出，生产文件和业务服务保持原样。

[真实 HTTP/PG 测试](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/test/integration/api/test_health_member_access_contract_http.py)在隔离服务和数据库使用合成账号，最终完整运行 7 passed in 39.23s，0 skipped。每项回读建档、授权当前槽位、撤权、同意及撤回事实，并验证非 Owner/管理员拒绝、政策或处理方漂移、处理方审批失效、缺 ai_use、401 和原有输入校验；失败路径保持数据库快照不变。Run、Request、Message 及咨询等执行表始终为 0。最终七个独立清理回执各验证 76 张关联表计数为 0；所有 16 个 fixture 周期回读原 ConfigOption、Agent、Skill 字节恢复一致且临时 provider 为 0。

原始证据保留首次测试样例使用空 processor 导致 422 的失败，以及修正后完整通过的日志。新增 fixture 显式依赖 verified_capability_cleanup，最终七项均取得独立清理回执；早期九轮缺失的独立归零回执不作为清理验收依据。

验证命令使用已有测试环境的 `uv run --no-sync --group test pytest`。全量后端 unit（`test/unit -m "not slow"`）4469 passed、59 skipped、6 warnings in 554.08s；仅测试进程清空 Langfuse 导出环境变量，避免独立测试服务配置影响既有默认配置断言，主服务配置保持原样。相关 unit、HTTP/PG、两项进程内负控及主服务回读的原始日志、JUnit 和 JSON/JSONL 回执保存在被忽略的 `agent/.tmp/health-member-access-contract-20261011/`。工程信任校验及其 63 项 unittest、四个变更 Python 文件的 Ruff/check-format、两个文档的 50 个源码链接检查及 VitePress build 均通过。

未验证：Worker/队列/真实模型执行、并发授权与同意写入、专业档案、正式 App/微信/真机及生产部署。四个响应模型不构成完整客户端协议冻结或营养业务完成。
