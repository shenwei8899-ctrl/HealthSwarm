# 家庭配餐Agent的成员范围和预览执行

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_family_planner_service.py

## 问题

家庭餐单、安全改版、共同采用和参与调整已有后端用例，配餐Agent仍只有单成员通用草稿工具。需要让家庭用户在实际Run/worker链路中获得当前档案、质量依据和预览，并保证其他参与者的权限、用途同意及来源不被入口成员替代。读者是健康后端与小程序接口维护者。

## 决策

家庭配餐线程由用户明确选择原家庭餐单、版本、批准规则版本及全部涉及成员的档案版本。全部原参与者必须包含在选择中；可增加拟加入成员，但模型不能扩大选定成员集合。服务器保存不可变选择与来源摘要，拒绝同键改选，不从用户文本、模型参数或客户端会话metadata读取身份。绑定保存在现有健康会话上，删除方案或选择不可解析时失败，不能自动成为单成员模式。

创建、请求入队、运行资源准备、每次模型及工具调用、checkpoint复用、最终Message发布和私有历史读取均检查全体成员当前权限与meal_plan同意。成员按ID排序持锁，包含ai_use、diet_edit和profile_view；检查当前模型处理方/政策和固定内置Skill。餐单、档案或规则版本及来源变化需要用户重新选择。

家庭模式固定四个工具：读取选定家庭上下文、共同换菜候选、整份安全重算预览、参与者/份量调整预览。后端从固定选择构造已有业务DTO，工具参数只包含明确菜位或三餐分配；不提供账号、模型、Run、来源版本、营养、医学目标和审核状态字段。候选与预览复用既有业务Owner，缺依赖、冲突或预算耗尽如实返回；工具只持久化当前Run的预览收据，不保存修订、采用、专业批准、采购或DietLog。

最终输出只允许选择本Run家庭预览收据或补充问题。服务器在相同来源及权限/同意锁内重新运行预览，核对完整结果后投影；发布Owner再次复算再提交Message。跨Run、跨线程、过期执行Owner或伪造结果不能发布。历史tool消息按收据及所属Run重验，不要求旧收据属于新Run，但要求其原线程、选定来源、当前权限/同意和完整内容仍一致。

健康Schema13增加家庭选择列和家庭预览收据表，保留既有单成员会话与回执。正式迁移与重复DDL在隔离PG中验证，默认与隔离环境执行增量迁移。批准初始生成、日终/次日联动及家庭页面由[六Agent工程目标](../proposed/2026-10-07-health-agent-engineering-completion.md)继续交付；本阶段把已有家庭用例接入运行引擎。红阳完整档案、生产专业资料与真实供应商质量仍待外部交付或验收。

## 替代方案

直接向现有单成员工具提交家庭Spec缺少服务器固定范围与其他成员同意。新增通用工具会允许模型改选对象、来源或自行保存。复用配餐后端和预设的家庭模式，把额外选择与只读业务工具接入当前执行Owner，保留单成员草稿的独立资源协议。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 家庭选择及全员范围不可变 | 同键改选、漏成员、模型扩大范围 | 健康绑定及家庭选择parser | 家庭HTTP/PG固定选择及拟加入者验证；迁移回读 | 跨账号/对象/模式、漏原成员、额外字段 | 通过 |
| 全员同意与权限覆盖执行和读取 | 只检入口、撤权后继续模型或发布 | 绑定授权与meal_plan处理门禁 | 家庭HTTP/PG、锁等待和实际worker完成结果撤同意 | 第二成员无同意、撤权/撤回、错用途/处理方 | 通过；无新增Request/Run/Message |
| 四个工具返回当前服务器事实 | 模型伪造来源/结果、工具产生正式状态 | 固定工具与既有家庭业务Owner | schema unit、实际API/worker/SSE、PG快照回读 | 注入身份/目标、未知来源、预览与保存混用 | 通过；360/365/450kcal独立对照、原计划未改 |
| 收据及checkpoint不能跨Run或改源 | 自由正文、旧收据、失去执行Owner | 家庭收据及Message发布Owner | 实际worker连续Run；自然租约到期及发布事务PG负控 | 跨Run/线程、伪批准、过期lease、来源变化 | 通过；过期零收据、失败无Message/完成状态 |
| 迁移保留单成员及当前业务行为 | 旧列查询失败、重复迁移或旧协议损坏 | health schema迁移与单成员Owner | 正式12→13迁移两次、旧绑定及时间戳回读；既有回归 | 旧绑定无家庭字段、原快照保持 | 通过；默认及隔离环境Schema13 |

相关unit六文件110项通过：家庭配餐、迁移、单成员配餐、营养师、咨询及质量；角色unit另13项通过。家庭HTTP/PG的13项覆盖真实成员锁等待、餐单刷新顺序、授权等待及预览计算后自然租约到期。两个租约负控均重新读取零回执；直接调用最终发布Owner的负控重新读取Run仍running、无Message或输出。正式迁移测试在真实PG从12执行到13两次，保留旧单成员绑定、时间戳和记录。

HTTP/PG共46个不同案例通过：新增家庭13项、既有配餐/质量/Schema32项，以及受共享配置并发影响的一项配餐HTTP在最终顺序批次复验通过。失败的并发批次不作为整批通过证据。Schema覆盖其中9项。最终顺序运行家庭配餐、单成员配餐和质量E2E及该HTTP复验，11项通过；其中10项E2E为4项实际worker回放和6项真实PG发布/checkpoint边界。家庭回放在同一线程执行参与调整、换菜、重算、问题、伪造最终输出及跨Run收据，核对实际四工具/Skill、持久化输出、来源、checkpoint和原计划。撤同意使用首个实际完成Run，验证结果返回run_not_found，SSE为200且仅发送error事件，历史404、新请求403且无新增数据。

家庭HTTP/PG与正式迁移证据分别由`test/integration/services/test_health_family_planner_http.py`及`test/integration/services/test_health_family_planner_schema.py`承载。最终顺序命令在隔离API工作目录运行，E2E设置`TEST_BASE_URL=http://localhost:5050`及`HEALTH_CONSULTATION_E2E_ISOLATED=true`，运行`python -m pytest test/e2e/test_health_family_planner_e2e.py test/e2e/test_health_meal_planner_e2e.py test/e2e/test_health_quality_e2e.py test/integration/services/test_health_meal_planner_http.py::test_unknown_amount_invalid_recipe_role_binding_and_model_approval -q -p no:cacheprovider`。定向Ruff check和format覆盖20个相关源码/测试文件通过。独立Reviewer对照源码、真实负控及最终回放审查，未发现剩余具体问题。

## 后果

选定餐单或任何涉及成员来源改变后，原线程需要重新选择；这是来源固定的使用约束，接口须返回明确错误。家庭预览与Agent结果需要全体授权，不把逐人输出拆开旁路其他人的授权。合成批准资料及模型协议回放仅证明工程；专业质量及生产资料保持独立验收。
