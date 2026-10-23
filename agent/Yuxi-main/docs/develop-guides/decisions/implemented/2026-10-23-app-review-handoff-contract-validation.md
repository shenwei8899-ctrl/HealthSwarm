# App专业复核与交接协议验收

状态：implemented
类型：testing
Owner：backend/test/integration/services/test_health_review_workbench_http.py

## 问题

正式App需要明确专业动作响应丢失后的恢复方式，以及主动交接确认后返回目标会话的边界。已有后台和HTTP/Worker验收不能替代客户端生命周期验收；客户端也不能由一次提交动作推断当前审核状态。

## 决策

### 实现方案

复用现有工作台HTTP/PG测试，增加提交响应未知、审核人随后退回、申请人原请求重放的场景。回读当前状态及不可变动作，验证原请求不会重复提交，改变正文或使用旧版本的新动作会冲突。交接E2E补充顺序重放及读取目标历史后会话、Request、Run计数不变的断言。请求样例和客户端验收步骤归入agent/docs既有交接文档，实际协议由service和路由拥有。

不修改App目录、专业状态机或预算实现，不部署生产，不启用真实供应商。仅在独立合成Compose内验证；该环境使用测试供应商时为其登记合成预算，不能据此批准真实价格。

## 替代方案

重复实现后台工作台没有当前缺口。只提供文字交接缺少真实响应未知恢复证据。直接把后台测试标为App验收会混淆客户端页面、导航和会话清理责任。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| 原审核请求重放返回当前状态且不新增动作 | 旧响应导致重复提交 | health_quality_service及PG动作表 | review_workbench及quality HTTP测试 | 同键异参、旧版本新请求 | 23 passed |
| 交接重放及返回读取不自动执行 | 重建线程或新增Run | health_handoff_service及consultation事务 | handoff E2E与PG计数 | 未确认、变更来源、目标缺同意 | 4 passed |
| App接入样例与当前协议一致 | 幂等头、版本或错误处理错误 | 路由与交接参考 | 5个样例正文通过当前Pydantic类型校验 | 明确剩余客户端验收 | Passed |

运行命令为 `python -m pytest test/integration/services/test_health_review_workbench_http.py test/integration/services/test_health_quality_http.py -q` 和 `python -m pytest test/e2e/test_health_handoff_e2e.py -q`。合成预算由已提交的隔离测试夹具准备，约束及重跑证据见[合成预算测试准备](2026-10-23-health-budget-test-fixtures.md)。工作台及质量HTTP23项、交接E2E4项已在专用环境重跑通过。日志及环境启动器保留在本地 `agent/.tmp/github-push-20261023/`。两个改动测试文件通过Ruff检查。数据库池弃用警告不影响上述断言。

## 后果

真实App生命周期、微信真机和专业资料质量仍待各自负责人验收。合成模型只证明工程连接与持久化语义。
