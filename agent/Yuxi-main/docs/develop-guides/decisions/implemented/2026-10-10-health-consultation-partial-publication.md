# 咨询失败回退的正文发布边界

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/chat_service.py

## 问题

咨询执行中撤销模型处理同意会拒绝后续正式发布，但通用异常回退仍可能保存积累的模型正文，并绑定失败 Run 的输出指针。现有回退仅对已登记正式档案或实测来源的咨询禁用；未使用这些来源的咨询也受处理同意、知识引用及其他业务校验约束。真实 Worker 撤销测试已观察到 failed Run 仍有普通 assistant 正文。

## 决策

### 实现方案

`save_partial_message` 对全部固定 `health-consultation` 的非中断失败返回空结果，不写普通正文和输出指针。显式中断只保存空正文及固定`interrupted`、`is_error:true`、`咨询已中断`元数据；同一中断事务的Run错误也使用这两个固定值，积累正文、additional_kwargs、原错误及trace均不进入公开消息或Run错误；当前 worker/request 的锁与中断事务仍由既有 Run repository 执行。完整咨询结果继续通过现有来源、同意和引用校验后原子发布。普通 Agent 的部分输出及其他固定健康角色的规则保持其既有 Owner。

删除回退路径中按正式来源 Use 表判定是否允许咨询正文的查询，避免在错误收尾中重新拼装另一套发布许可。不删除历史消息，也不增加状态或持久化表。

## 替代方案

在失败回退中再次执行全部咨询发布校验会重复完整完成路径，并增加错误收尾中的授权锁、引用质量及状态协调。只补处理同意检查仍会使其他未通过校验的正文进入普通历史。统一禁用未校验失败正文覆盖这些失败面，客户端依据 Run 错误恢复。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 未校验咨询正文不进入普通历史 | 无正式来源 Use 时绕过 | chat service | 专属12个用例与相关回归合计126 passed；真实撤同意Worker定向1 passed，PG/HTTP无正文、无指针 | 仅在专属测试进程的函数副本关闭咨询guard，bare/有Use×partial/interrupt四项业务断言全部失败 | Passed |
| 显式中断仍原子收尾 | 把中断作为普通失败或泄露积累正文 | Run repository / chat service | 同一126项回归覆盖固定错误、空正文、普通Agent兼容与worker/request拒绝；无Use表查询 | 当前worker/request失效不得提交，原正文/additional_kwargs/trace/错误不能进入咨询中断公开字段 | Passed |
| 引用错误失败不发布正文 | 错误模型答案经通用回退保存 | 咨询发布 / 引用 Owner | `test/e2e/test_health_nutritionist_e2e.py`真实HTTP→Worker→PG 1 passed，3个Run；用例后24表与最终50健康表/运行事实零行 | invalid_evidence为failed、无普通text或输出指针，私有model_audit保留；来源撤回后旧引用410且新Run模型不外呼 | Passed |

直接命令与结果：

```sh
uv run --no-sync --group test pytest test/unit/services/test_health_consultation_partial_publication.py test/unit/services/test_health_family_profile_publication.py test/unit/services/test_health_weight_publication.py test/unit/services/test_chat_service_sync.py test/unit/services/test_chat_service_langfuse_stream.py test/unit/services/test_chat_stream_interrupt.py -q --tb=short --show-capture=no
# 126 passed；专属测试内的受控函数副本变异可单独启用：预期4项失败，禁止把失败当通过。
HEALTH_PARTIAL_MUTATION=disabled_consultation_guard uv run --no-sync --group test pytest test/unit/services/test_health_consultation_partial_publication.py -k bare_and_formal -q --tb=short --show-capture=no
```

真实Worker在原300秒`health_consultation_e2e`隔离配置运行；短预算撤同意路径复用[执行预算实验](2026-10-10-health-run-execution-budget.md)。原隔离项目使用`backend/test/support/health_consultation_replay_server.py`，在8766无占用时由测试创建进程，捕获精确PID；结束后核对该PID的cmdline仍匹配脚本再停止，不能停止外部既有回放。预算实验的Popen启动与精确PID停止命令可替换脚本名和端口复用；真实引用命令为：

```sh
HEALTH_CONSULTATION_E2E_ISOLATED=true TEST_BASE_URL=http://localhost:5050 uv run --no-sync --group test pytest test/e2e/test_health_nutritionist_e2e.py -q --tb=short --show-capture=no
```

该Worker命令1 passed /28.34秒，处理同意撤回定向1 passed /33.96秒。单元和Worker已有依赖警告保留，不声称无警告；模型为本地合成回放，无生产健康数据。实际命令、有效变异、原缺陷失败、PG最终回读和隔离恢复证据存于本地`agent/.tmp/agent-completion-20261010/health-consultation-partial-verification-final.json`及相应日志，均不随Git提交。

## 后果

旧客户端可能曾展示失败咨询的部分正文；固定咨询改为读取结构化 Run 错误。模型及工具私有审计仍遵循原访问控制，合成回放不能证明医学质量。生产模型、来源和用途审批不因本修复改变。
