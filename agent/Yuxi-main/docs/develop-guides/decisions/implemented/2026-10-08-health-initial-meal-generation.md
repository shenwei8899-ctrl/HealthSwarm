# 批准目录驱动的初始个人与家庭配餐

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_initial_meal_plan_service.py

## 问题

现有安全重生成依赖已保存餐单及其菜位和份量，初次使用只能先建立通用草稿。需要在当前确认档案及批准规则下直接生成个人或家庭三餐，并在用户确认后创建初版和可提交专业审核的检查。读者为健康后端及档案/规则接口维护者。

## 决策

批准规则增加可选初始配餐目录：真实菜谱版本及配方摘要、允许餐次、菜品类型，以及逐人群/完整疾病组合的三餐布局和有限克数选择。代码不提供医学比例或默认份量。用户明确日期、规则/档案版本及每餐参加者，全部实际参与者须编辑及档案读取授权；个人模式只支持入口成员完整三餐。家庭相同餐次/类型共享一道菜，按各自批准菜单独立选择个人份量；不同类型分别分配给实际食用者。每位参与者的覆盖营养、过敏、医嘱及个人目标均复用质量Owner。

组合搜索复用有界确定性搜索；有限预算耗尽与穷尽无解分开返回。没有确认档案、完整规则、合法来源或匹配菜单时没有可保存结果。预览只保存独立服务器回执，Schema14新表保留既有预览和单成员/家庭数据。读取与确认均重新核对全员当前来源和完整结果；模型或客户端不能提交营养、身份、目标、方案正文或专业批准。

明确确认使用既有保存幂等锁和不可变修订表，初版、确定性检查及专业草稿同事务创建。仍需独立专业人员批准，正式采用及采购由其业务Owner控制。现有通用预览保存接口不能消费新回执。[固定初始配餐Agent运行](2026-10-08-health-initial-planner-runtime.md)接续模型执行与发布范围，本记录拥有初始生成后端及其历史验收证据；[六Agent完整工程](../proposed/2026-10-07-health-agent-engineering-completion.md)继续执行。

Plan和修订保存确定性营养快照及独立generation_origin依据。质量与家庭参与调整比较完整营养canonical，来源摘要同时覆盖origin。公开初始结果列出确认营养投影和规则版本，完整健康档案标为未交付；历史结果要求重查当前来源。专业批准后的采用与今日读取复用公开投影，采用持久化及批准门禁保持由原Owner拥有。新增可空目录缺失时不进入导入摘要，同版本旧批准规则保持可重放。

## 替代方案

复制一个通用草稿再重生成会继承未批准菜位和份量；让模型自行估计份量无法追溯专业依据。批准有限菜单与同一质量检查器为初次配餐提供可验证来源，目录未交付保持明确未就绪。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 初始三餐来自批准来源并满足逐人目标 | 默认医学系数、继承旧餐单、家庭总量掩盖个人不合格 | 规则parser及生成/质量Owner | test_health_initial_meal_generation.py与test_health_initial_meal_plan_http.py；330/396/429kcal独立对照 | 缺目录/档案、疾病菜单不匹配、过敏、部分覆盖缺比例 | Passed |
| 全员权限及来源覆盖预览/读取/保存 | 入口授权替代其他成员、旧预览被保存 | 生成context与确认事务 | 真实PG第二成员锁等待和HTTP拒绝 | 跨账号/对象、第二成员diet_edit/profile_view撤权、档案/规则/配方变化 | Passed |
| 保存仅经明确确认且幂等原子 | 客户端伪造方案、重复初版、未检查仍保存 | 既有修订和检查Owner | HTTP同键竞争及异参、末次真实检查失败后PG回读和恢复正例 | 伪造、旧回执、失败事务零新计划/修订/检查/审核草稿 | Passed |
| Schema升级及旧消费者保持兼容 | 新表遗漏、旧摘要变化、合法参与调整被拒绝 | 正式健康迁移、依赖导入及参与/采用Owner | test_health_initial_meal_plan_schema.py；实际批准/采用/今日及参与改版 | 旧预览绑定保留、同版本旧规则摘要、canonical营养篡改 | Passed |

2026-10-08实际执行：相关unit分组111、78、13及26项，共228项不同案例通过；真实HTTP/PG分组44及31项，其中一个初始家庭参与用例重叠，共74项不同案例通过。HTTP使用uv run --no-sync --group test python -m pytest test/integration/services/test_health_initial_meal_plan_http.py test/integration/services/test_health_initial_meal_plan_schema.py test/integration/services/test_health_plan_adoption_http.py -q -p no:cacheprovider，质量/家庭参与/安全重生成回归同方式分组执行。

既有家庭、质量和单成员配餐API/worker/SSE回归10项通过，含4项实际worker流程及6项直接PG发布/checkpoint边界。执行隔离槽位python -m pytest test/e2e/test_health_family_planner_e2e.py test/e2e/test_health_quality_e2e.py test/e2e/test_health_meal_planner_e2e.py -q -p no:cacheprovider，125.69秒；合成规则与协议回放证明工程链路。独立复核通过；Ruff、工程契约及62项检查、文档构建通过。完整全仓unit、外部真实模型与生产专业验收未执行。

## 后果

有限批准份量组合没有可行解时需专业资料调整；预算耗尽不声明无解。合成批准目录只用于隔离工程验证。红阳完整档案、生产专业规则、小程序及真实模型质量仍待外部交付或验收。
