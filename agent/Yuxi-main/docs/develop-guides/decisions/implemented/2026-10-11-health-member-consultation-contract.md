# 本人关联与普通咨询响应契约

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_family_profile_service.py

## 问题

正式客户端需要区分家庭档案成员与健康业务成员，并复用现有普通咨询入口。本人关联和咨询的四个既有 HTTP 操作需要通过 OpenAPI 提供成功响应字段定义。缺省字段、null 和分页尾部具有兼容意义，响应校验必须保留已有 wire 形状。

## 决策

### 实现方案

[本人关联服务](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_family_profile_service.py)拥有未绑定及已绑定的成功 DTO。[健康类型](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_vision_types.py)拥有普通咨询创建和分页 DTO。[健康路由](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/server/routers/health_vision_router.py)声明四个 `response_model`，在服务返回后校验并序列化成功响应。

本人关联 GET 未绑定时返回必填的 `source_member_id:null`，省略 `family_id`；已绑定 GET 和 POST 返回健康成员、原档案成员及家庭 ID。咨询创建固定返回 `health-consultation` 角色、可空业务日期及必填的 `feedback_selection:null`。咨询列表保留元信息、原有 UTC `Z` 时间字符串及末页 `next_offset:null`。DTO 使用已有 `HealthDTO` 的额外字段拒绝约束。

当前 service/repository 继续拥有身份关联、字段授权、撤权、幂等和事务。普通咨询创建只形成业务绑定、Conversation 和 Project；这些入口不调用模型或创建处理同意、Message、AgentRunRequest、AgentRun。模型处理授权继续由实际 Run 提交及执行边界检查。Task 的业务结果分类由现有 `health_task_types.py` 拥有。

[客户端交接说明](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/docs/家庭营养师-Agent交付与待对接.md)以正式 App 源码和主服务路由为依据，记录模拟页面、成员桥接、请求头、错误解析及微信后台待合入范围。现有账号密码登录工程可用于接口联调。正式 App 页面、微信身份及真机验收由对应负责人处理。

## 替代方案

仅维护人工字段表无法在 OpenAPI 中发现响应结构。一次性类型化所有健康 API 会扩大兼容和验收范围。Task 的业务 `data` 包含初始、家庭及安全配餐等不同结果，保持既有 Owner 能避免用普通餐单类型压缩这些语义。

## 后果

调用方可以从 OpenAPI 获取四个成功响应定义。服务返回缺字段、额外字段或错误固定值时，FastAPI 拒绝该成功响应。认证、输入校验和健康业务错误仍由各自现有 Owner 返回；调用方按实际错误载荷解析。

正式 App 的微信后台位于另一个工作目录，主服务仍为 schema 12。合入微信后台、部署配置及完整专业档案属于待对接范围。响应类型不改变成员访问权、个体化建议的专业校验或模型执行政策。

## 验证

- 定向 unit 共 44 项通过，其中新增响应契约 22 项；独立 Reviewer 另行运行新增 22 项通过。测试使用独立字面量核对 OpenAPI、wire、必填 null 和无效服务返回。
- 三批 unit 负向验证分别移除四个响应模型、丢弃 null、给未绑定 DTO 增加家庭字段，相关 oracle 分别产生 13、5、1 个预期失败。
- `test/integration/services/test_health_family_profile_http.py` 的真实 TCP HTTP 和 PostgreSQL 验收 17 项通过。数据库回读确认一个档案关联、两个幂等咨询及对应 Conversation/Project；跨账号、撤权、错误重试拒绝后无新增事实。普通咨询没有模型执行或处理同意副作用，各测试的独立 schema 删除后在目录中不存在。
- 六个 HTTP 字段负向验证分别在目标精确响应断言失败，每个恢复后对应测试通过。分页偏移、列表业务日期和列表时间的三个额外 HTTP 负向运行未执行；对应字段由新增 unit 的精确响应及错误边界用例覆盖。
- 主服务 `/openapi.json` 回读四个成功 schema；四个真实未登录请求均返回 401。正式 App 与主服务微信路由的交接状态已对照当前源码。
- 后端全量 unit 在隔离服务安装依赖上通过：4443 passed、59 skipped、6 warnings。执行 `uv run --no-sync --group test pytest test/unit -m "not slow" -q -p no:cacheprovider --durations=8`；测试进程将 `LANGFUSE_ENABLED`、`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY` 设为空，现有追踪测试使用其自身假客户端及假凭据。隔离服务原有关闭追踪的环境会使该模块八项失败或报错；服务环境和生产代码保持原样。
- 工程信任检查及其 63 项 unittest、五个 Python 文件的 Ruff check/format、两个改动文档的 48 个文件目标链接检查、文档构建及 `git diff --check` 通过。

Worker、云模型、正式 App、微信后台合入、真机及专业内容验收不属于该响应契约变更的验证范围。
