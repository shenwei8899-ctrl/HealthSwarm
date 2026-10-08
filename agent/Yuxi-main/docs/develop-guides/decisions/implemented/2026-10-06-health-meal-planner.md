# 基础配餐师与餐单草稿

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_meal_plan_service.py

## 问题

用户要求在红阳完整健康档案未交付时开发配餐师，复用现有Agent、菜谱版本和营养计算，交付三餐草稿、换菜重算及版本保存。读者为健康后端维护者；完整个性化配餐仍依赖档案与专业规则。

## 决策

固定工具的HealthMealPlannerAgent与成员绑定入口复用Request、Run、worker及PG checkpoint，预加载发布的family-meal-planner Skill。配餐模型使用独立meal_plan用途审批与处理同意。模型检索已发布菜谱，提交菜谱版本及计划份量的三餐结构；服务端计算、保存运行预览回执，最终结果仅接受本Run回执或补充问题。用户通过健康接口显式保存草稿或按当前版本换菜，当前行、不可变修订和幂等收据在成员锁下同事务提交。

本记录的单成员入口返回计划草稿，未知营养保持缺失，完整档案和审核规则显式未就绪，不能直接采用为个体审核方案或购买。已有家庭餐单的固定来源、全员同意及四工具运行协议由[家庭配餐运行](./2026-10-08-health-family-planner-runtime.md)拥有。21天计划、采购和完整健康档案仍为后续范围。后台页面由[餐单草稿工作台](./2026-10-06-health-meal-plan-workbench.md)记录。现有咨询工具和自述写入边界保持原范围。

配餐后端保留消息和工具审计；发布端过滤原始模型正文片段，只通过核验后的checkpoint输出餐单。通用Dashboard列表、筛选和统计排除健康角色，会话及Run访问仍核对成员授权；超级管理员身份不提供健康数据读取旁路。健康Schema 8增量创建预览、计划与修订表，兼容既有版本1至7。

## 替代方案

仅在原咨询prompt加入配餐会扩大其用途和工具边界；由模型提供营养数值无法独立复算；等待完整档案会阻止独立的草稿工程交付。采用独立角色、用途和确定性计算，复用已有运行引擎。

## 后果

真实模型选择菜谱和理解份量的质量需要单独验证；回放只证明工程装配。草稿计划量不能作为实际摄入记录。专业知识、完整档案和临床规则未交付，个体适配、审核与购买始终不可用。Schema增量要求迁移进程先执行，API和worker只检查版本。

配餐流保留工具状态和终态，正文在核验后一次发布。健康会话不计入通用管理统计；健康业务分析使用独立授权接口。个人健康审批默认关闭，隔离测试只审批内部合成服务；开发环境没有启用真实配餐模型。

## 验证

相关后端unit分两组运行：配餐、咨询、角色发现、迁移、记忆、反馈、Run及消息审计10个文件157项通过；Dashboard、流式审计、清单、Request及队列、会话与记忆检索7个文件144项通过。新增配餐unit的手算oracle为300克合成菜谱产生300kcal，缺失份量或营养保持空。

隔离Compose中，`python -m pytest test/integration/services/test_health_meal_planner_http.py -q`的5项通过；`test/integration/services/test_health_memory_schema.py`的4项通过。真实HTTP/PG验证保存幂等、同键异参拒绝、同版本并发一次成功、换菜后400kcal及原版300kcal历史、跨账号/超级管理员隔离与撤权；running状态下真实PG拒绝过期lease、错误worker及会话角色不匹配。真实PG升级版本4至7，重复DDL保留已有成员与记忆行；启动迁移进程把已有Schema 7增量升级至8。

`python -m pytest test/e2e/test_health_meal_planner_e2e.py -q`的1项通过，使用独立内部回放服务和实际API、worker、SSE、PG checkpoint，核对独立处理同意、服务器最终投影、伪造审核字段和跨Run回执失败、补充问题、原始模型正文不外流及已完成Run不能再次调用工具，生成不自动保存或写入实际饮食。既有咨询隐私HTTP与营养师、记忆、反馈worker回归另有7项通过。命令在API容器执行，测试缓存位于容器临时目录。

工程契约检查通过；`python -m unittest scripts.test_verify_engineering_contracts`的62项通过；`pnpm run build`的docs构建通过，Ruff与工作区空白检查通过。独立Reviewer静态复审没有未解决的P1/P2。

真实外部模型质量、正式菜谱数据、临床规则及小程序未验证，保留为后续交付范围。前端交互与真实手动餐单链路的验证由[餐单草稿工作台](./2026-10-06-health-meal-plan-workbench.md)记录。开发环境worker的既有10秒健康探针在并行验证期间超时，隔离环境使用60秒探针；实际worker协议链路的证据来自隔离运行，不能将该结果表述为生产健康或上线验收通过。
