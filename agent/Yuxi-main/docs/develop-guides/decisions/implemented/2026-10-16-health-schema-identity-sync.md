# 健康流程升级与身份整合的迁移兼容

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/storage_migration.py

## 问题

健康流程使用 Schema 26，既有身份整合使用 business 13 和 health 24。正式迁移入口的健康版本白名单及升级分支截至 23，既有 24 和中间版本 25 无法进入升级流程。

## 决策

### 实现方案

保留[身份整合](./2026-10-15-miniapp-identity-commerce.md)的路由、业务模型及 business 13 迁移，将健康版本 24、25 接入既有 `create_health_tables` 幂等升级及版本登记流程。HTTP、权限、Worker 和生产配置保持既有语义。同步源码不执行生产数据库迁移。

独立微信身份 HTTP 测试的模块级 fixture 明确不使用共享 API、沙盒或知识库清理；`environment` 继续创建并回收随机独立 schema，使用实际路由、TCP、JWT、PostgreSQL 与 Redis。共享应用测试的清理前置条件保持原样。

## 替代方案

仅覆盖健康域代码会丢失身份整合；仅修改版本号不能补齐旧表。复用既有迁移 Owner 可保留身份表和健康历史事实。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 24、25 经正式迁移入口升级到当前健康版本 | 白名单拒绝或跳过建表 | storage_migration.main | test_storage_migration 的既有版本参数用例 | 修复前仅 24、25 失败；修复后通过 | Passed |
| 身份业务版本与当前健康流程同时保留 | 覆盖版本常量或身份路由 | postgres/manager.py、wechat_auth_router.py | 身份及迁移51项单元测试，健康11项及身份7项真实 TCP/PG 测试 | 跨成员拒绝、版本冲突、并发幂等与账号冲突 | Passed |

独立 Linux 容器执行 `python -m pytest test/unit/services/test_storage_migration.py test/unit/services/test_wechat_login.py`、`test/integration/services/test_health_diet_correction_http.py`、`test/integration/services/test_health_independent_workflows_http.py` 和 `test/integration/api/test_wechat_login_http.py`。微信外部供应商使用合成响应。相关 Python 文件 Ruff 检查和格式检查通过；工程契约检查通过。

## 后果

健康表升级与降级边界沿用现有健康更正文档。未运行的生产、微信及真实模型验证不属于本次源码同步结论。
