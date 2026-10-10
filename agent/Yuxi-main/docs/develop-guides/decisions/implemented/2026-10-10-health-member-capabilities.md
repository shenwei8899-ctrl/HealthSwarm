# 成员任务能力的只读汇总

状态：implemented
类型：feature
日期：2026-10-10
Owner：backend/package/yuxi/services/health_capability_service.py

## 问题

客户端需要在当前账号和成员下判断哪些已实现任务可进入、哪些条件缺失以及哪些任务仍需明确选择。角色目录、七用途配置和平台 readiness 分别表达不同事实，客户端缺少可以直接消费的成员业务能力汇总。

目标是在现有健康路由提供只读 GET，返回八类已实现任务和三类未实现任务的状态、稳定原因及本人的缺失授权，附带最小依赖元数据。查询不创建项目、会话、Request、Run、预览、审核或采用，不调用模型，不写访问审计。该结果是查询时的入口提示，任务提交、执行和发布仍重验当前来源与权限。

本范围不实现列表分页、恢复协议、小程序页面、专业规则、完整档案、21 天计划、自动协调或商城交易。缺少选定对象时不猜测规则、参与者、方案或库存版本。

## 决策

### 实现方案

健康 HTTP 路由从登录上下文取得账号并调用只读能力 service。service 先使用 HealthVisionRepository 证明成员可见性，再读取当前用途配置、固定 Agent、内置 Skill 和同用途同意，按任务投影最小入口状态与所需选择。当前最高安全投影在 `profile_view` 授权内读取；响应不保存新的能力状态，数据库事实及执行检查由原业务 Owner 继续维护。

- `GET /api/health/v1/members/{member_id}/capabilities` 从登录上下文确定账号。先证明当前有效授权的成员可见性；不存在、撤权、空授权和不可见成员统一返回 404。只有可见成员才返回本账号的缺失 scope。
- 普通咨询、普通配餐草稿和饮食分析在各自授权、专属 Agent、内置 Skill、用途审批与当前处理同意满足后可进入。完整专业档案不是这三类入口的统一前置。
- 初始配餐、家庭改版、安全改版、质量检查和采购净需求在公共前置满足后返回 `needs_input / selection_required`。特定来源和其他参与者在选定后由原服务检查。
- 控糖、多日和自动协调沿用外部契约未就绪原因。采购净需求不表达 SKU、下单或专业批准可用。
- 用途配置补充稳定原因码，由现有 configuration Owner 在原检查分支产生；能力响应仅使用必要状态，不透传供应商配置、模型选项或处理指纹。
- 安全档案投影仅读已授权的当前最高来源状态、原因与版本；不返回内容、证明或指标。菜谱存在性只表达已发布菜谱库是否有记录，不能证明专业适用性。专业规则仍须明确选择来源。
- 禁止用创建入口、审核状态修复函数、采用有效性修复函数和默认审计读取当探针。当前 `HealthGrant` 和 `HealthProcessingConsent` 没有期限字段，本接口不新增或宣称这些对象的有效期机制。

## 替代方案

客户端逐个调用现有服务会重复组合入口条件，且部分业务读取会更新失效状态。只读 service 复用来源 Owner，以统一稳定协议表达现有条件；代价是查询结果可能被随后变更替代，客户端必须以实际提交和执行响应为准。

不增加中央可编辑能力表、持久缓存、健康计算副本或新的 Agent 状态机。具体营养、规则、专业批准和交易状态继续归原业务对象所有。

## 后果

入口提示与实际提交之间的授权、配置和来源可能发生变化；实际业务服务继续重验，客户端依实际响应处理。最高来源可失效，汇总查询保持只读，选定来源后的专业批准由原业务流程判断。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 成员可见性先于私有依赖读取 | 跨成员、管理员旁路、撤权泄漏 | HealthVisionRepository 与新 GET service | 真实 HTTP/PG 回读 | 无授权、空 scope、已撤权、非本人管理员 | Passed |
| 状态复用当前用途、同意和固定资源 | 旧同意、用途混用、失效模型或 Skill 被标可用 | configuration、consent、Agent/Skill repositories | unit 与真实 HTTP | 政策/处理方变化、独立用途未同意、Skill 禁用 | Passed |
| 无明确选择的专业任务保留待输入 | 猜选规则或以档案存在代替专业批准 | Task DTO 与来源 Owner | HTTP 协议结果 | 安全投影就绪仍不能自动使特殊任务可用 | Passed |
| 查询不产生业务副作用 | 创建运行、审计或失效写入 | service 调用图与 PG | 查询前后精确业务快照 | 同一查询重复及失效来源仍无状态/版本变化 | Passed |
| 缺少专业资料不误封普通入口 | 角色 partial 被当全局禁止 | 普通入口契约 | 正常、缺资料与选择分支 | 无安全投影的普通咨询仍按现有门禁判断 | Passed |

在独立合成槽位、当前数据库及实际 API 进程中运行以下命令，成员能力 HTTP 验收 17 项通过、零跳过。fixture 在每例结束时精确恢复用途配置、五个内置 Agent 与 Skill，回读所属关联表行数归零。HTTP 测试比较完整 PG 行摘要、计数和状态版本，保留现有过期最高档案及已批准审核、有效采用以验证 GET 无失效写入。

```bash
uv run --no-sync --group test pytest test/integration/services/test_health_capabilities_http.py -q --tb=short --show-capture=no -p no:cacheprovider
uv run --no-sync --group test pytest test/unit/services/test_health_capabilities.py test/unit/services/test_health_vision.py -m "not slow" -p no:cacheprovider
```

HTTP fixture 要求 `HEALTH_CONSULTATION_E2E_ISOLATED=true`、测试数据库与 `TEST_BASE_URL` 同一独立槽位。第二条定向 unit 命令 57 项通过；这些结果分别计数。服务与协议的语义由[只读 service](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_capability_service.py)及[独立 HTTP/PG oracle](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/test/integration/services/test_health_capabilities_http.py)拥有，接入方式见[成员任务入口状态](../../../advanced/health-member-capabilities.md)。

独立无网络进程恢复授权谓词、非法 scope、私有读取授权、固定角色及内置 Skill、同账号成员用途处理同意、选择状态、普通入口误封和私有字段泄漏等 18 个缺陷变体，全部在目标断言阶段被拒绝。前后正控各 25 项通过，源码摘要一致；其中内存 SQLite 只验证查询谓词，真实权限和无写入事实由上述 HTTP/PostgreSQL 验收提供。

该接口没有新增 Run 执行路径，Worker、云模型与专业医学质量验收为 `Not run`。列表分页、客户端恢复、正式小程序页面、商城和外部完整档案仍在本决定范围之外。
