# 饮食分析师显式绑定当前批准个人目标

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_agent_personal_target_service.py

## 问题

个人目标HTTP由原Owner读取当前批准来源并计算目标范围。普通饮食分析师的三个工具只提供确认记录事实，缺少用户明确选择目标后的受控读取；模型不能选择规则或档案版本，也不能把当前目标应用为历史目标或自行计算差额。

## 决策

### 实现方案

`POST /api/health/v1/members/{member_id}/diet-analyst`接收可选`target_selection`，仅含`rule_code`、`rule_version`和`profile_version`。consultation service/repository创建整线程不可变绑定并校验派生Run摘要；新Agent目标service在同事务内调用原个人目标Owner，固定当前完整来源摘要并输出最小目标。analyst Graph、toolkit及内置Skill装配第四个无业务参数工具；diet analysis service/repository重验确认事实、目标工具历史与最终发布。HTTP只处理认证与DTO，原计算、专业来源和授权Owner继续拥有对应事实。

选择只适用于普通`health-diet-analyst`，反馈、咨询、配餐、质量及采购模式拒绝夹带。没有选择的普通三工具模式和原反馈二工具模式保留原入口。初次目标必须`ready`：来源版本冲突沿用409，专业依赖缺失返回503；没有`profile_view`或当前成员授权返回404。绑定不调用模型；执行继续要求已审批的`diet_analysis`处理用途及当前处理同意，没有管理员旁路。

### 固定来源与持久化

`health_consultation.personal_target_selection`是可空JSONB，旧行保持NULL。内容只有用户选择与原Owner完整返回值的规范SHA256：

```json
{
  "selection": {"rule_code": "用户明确所选规则", "rule_version": 2, "profile_version": 2},
  "source_hash": "完整当前目标返回值的SHA256"
}
```

不保存第二份目标正文，不建立计算或目标依赖表。完整结果只在服务器本事务内核验。相同幂等键不能改变、新增或移除选择；来源改变后需要新线程。每个Run的既有`health_processing`快照包含该绑定的`personal_target_selection_hash`。全部绑定Run均依赖目标，即使模型未调用目标工具，删除绑定、改变摘要或跨角色历史也返回410。

原`read_personal_targets`提取同语义`personal_targets_in_session`，HTTP wrapper继续调用它。绑定、读取和发布使用调用方事务，复用成员、本人档案/选定体重、规则锁序与既有最高版本、payload/审核依据hash、撤回/过期及更正来源校验。绑定后当前来源不就绪、版本或完整摘要变化均为410，不返回健康正文。

Health Schema为23，正式migrator允许22增量升级，使用幂等`ADD COLUMN IF NOT EXISTS`；已有绑定字段和采购选择保持。新增ORM列在根协调维护窗口内随版本门禁一起上线，主服务和隔离服务均通过正式22→23迁移后恢复。迁移未重新创建数据库，也没有改变处理配置。

### 模型输入与事实发布

绑定模式的固定四工具为`list_analysis_meals`、`analyze_confirmed_meal`、`analyze_confirmed_period`及`get_bound_personal_targets`。目标工具没有模型业务参数，actor、成员与选择均取自ToolRuntime和PG；模型不能传入规则、版本、身体参数或营养值。Graph、Run manifest及内置Skill使用相同真实注册工具，不开放通用工具、MCP或规则搜索。

目标投影只有当前能量、范围、单位、必要来源ID/版本/hash及完整结果摘要；原始`inputs`、身体参数、formula和完整attestations不进入模型。成功工具正文及持久化最终分析逐次与当前最小投影核对；checkpoint解析和来源验证在模型调用前执行，发布事务再次重验当前授权、来源和确认记录事实。

最终结果的可选`current_personal_targets`明确`scope=current_personal_targets`、`applied_to_record_window=false`。原分析`personal_target=null`、`personalized=false`保持记录事实语义；单餐和1/7/30日窗口均不产生达标、差额、疾病结论、趋势或全天完成声明。未知值保留null，已知部分和完整摄入分开。追问结果仍为Run completed与业务`needs_input`。统一健康任务结果复用原`validate_analyst_publication`，继承相同校验。

## 替代方案

仅通过提示词调用目标HTTP会让模型选择规则与版本。将当前目标乘7或30没有历史有效期和全天记录事实。会话metadata不能承担固定业务来源；新增目标依赖表在整线程选择下重复绑定事实。另建营养计算会改变A的语义Owner，因此复用原in-session读取。

## 后果

普通分析师可以在用户明确选择后解释当前批准目标，并同时展示独立确认记录事实。整线程来源依赖使新版档案、规则、实测更正及撤回阻止旧上下文和旧结果继续使用；来源更新后需要新分析线程。目标绑定额外要求`profile_view`，不影响无目标模式的原授权。

正式公式、适用人群、完整专业档案与生产来源由A交付。历史目标有效期、每日完整摄入确认、差额/达标规则、趋势分类和最低样本仍待专业契约。正式页面由其Owner对接。合成工程回放不能代表医学结论、生产云审批或真实模型质量。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 用户明确选择与最小不可变绑定 | HTTP/PG及幂等 | target DTO、consultation创建 | 目标HTTP9、私Schema1、专属unit22 | 同键改变/移除、额外目标值、无目标缺profile_view仍兼容、其他模式夹带 | Passed |
| 目标来自原程序Owner和当前批准来源 | 当前来源与授权 | personal_target及原profile/quality Owner | 原目标HTTP11、目标HTTP9、真实体重来源2 | 档案/规则撤回、过期、attestation或正文篡改、体重更正/作废、admin无读取授权 | Passed |
| 固定四工具与派生历史依赖 | Graph、manifest和结果 | analyst Graph、target绑定及发布Owner | 实际Graph unit、四项工具移除oracle、真实Worker/SSE/PG | 模型规则参数、未调用目标工具仍有依赖、删除绑定、来源撤回隐藏六个已完成结果 | Passed |
| 当前目标与历史确认事实独立 | 模型输出与最终Message | diet analysis/publication | Worker单餐、1/7/30日、追问及伪造输出 | 模型附加营养值/差额、未知钠值零填、今日目标套历史窗口 | Passed |
| 版本22正式升级且幂等 | migrator版本门禁及DDL | storage_migration、PG manager | 私Schema formal migrator两次、根主/隔离正式迁移 | 旧行NULL、原字段保持、JSONB无默认、第二次保留已写绑定 | Passed |

2026-10-10在`health-diet-analysis-e2e`独立合成槽位执行：

```bash
docker exec health-diet-analysis-e2e-api-1 pytest test/unit/services/test_health_agent_personal_targets.py -q -p no:cacheprovider
# 22 passed，40.77s
docker exec health-diet-analysis-e2e-api-1 pytest test/integration/services/test_health_agent_personal_targets_http.py test/integration/services/test_health_agent_personal_target_weight_sources.py test/integration/services/test_health_agent_personal_target_schema.py test/integration/services/test_health_personal_targets_http.py -q -p no:cacheprovider
# 23 passed，164.71s（9+2+1+11）
docker exec -e HEALTH_CONSULTATION_E2E_ISOLATED=true -e TEST_BASE_URL=http://localhost:5050 health-diet-analysis-e2e-api-1 pytest test/e2e/test_health_agent_personal_targets_e2e.py -q -p no:cacheprovider
# 1 passed，62.29s（七模式，六个completed及一个明确failed）
```

此前目标18项与原目标、单餐/周期分析、反馈及consultation相关回归共100项通过（66.31s）；随后新增四项独立注册工具移除负控，专属22项重新通过。无效模型答复没有权威输出指针、公开output或非审计最终assistant Message；失败模型/工具审计按原Owner保留。成功Run均回读PG最终Message与HTTP结果、绑定摘要、四工具manifest和原DietLog不变事实。

fixture清理后只读核对所有模型/审批处理方/政策为空，测试账号、成员、来源、Run/Request、临时provider及私Schema计数为0，非终态与lease为0。8775本地回放进程按准确PID停止，TCP端口已关闭。根协调的主服务迁移配置哈希前后相同；本阶段未启用主服务模型或调用云模型。专属源码与测试ruff检查及`git diff --check`通过。专属真实checkpoint篡改和每个错误lease组合未单独进行HTTP注入验收，执行所有权沿用原Run Owner及其回归；生产专业语料与正式页面仍未验收。
