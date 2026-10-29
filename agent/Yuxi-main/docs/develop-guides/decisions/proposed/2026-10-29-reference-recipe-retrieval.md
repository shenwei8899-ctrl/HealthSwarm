# 日常参考配餐召回完整资料并约束工具调用

状态：proposed
类型：bug-fix
Owner：backend/package/yuxi/agents/buildin/health_meal_planner/graph.py

## 问题

日常参考配餐的标题检索只要有命中就跳过其余召回，目录和疾病食养资料会挤占完整烹饪文档。修复检索并正式发布后，普通合成账号的真实输入已能读取档案和菜谱、完成一次保存工具，但模型随后继续检索和调用保存，最终达到图循环上限。Preview 已写入不等于日计划已发布；该次 Run 失败、没有最终输出消息，今日餐单仍为 version 0、空餐次。

追加保存收尾并发布 `42f9ae5` 后，新的真实请求在保存前失败：30 次并行检索调用的参数为空、缺少必需的 `query`；随后四次有效检索均返回候选，但此前重试已耗尽流程步数。这次没有读取或保存回执，不能据此判定保存后收尾再次失效。

## 提案

### 实现方案

已发布的检索服务保留成员授权、固定知识库和当前 Run 回执，先查完整烹饪与 USDA 家庭菜谱标题，再用同类文档正文补充。每文件仅返回首个实际命中分片，最多四项；没有普通菜谱命中时使用既有语义检索 Owner。模型按明确偏好选择实际原文，保存仍逐字核验菜名、食材和步骤。

本次追加的收尾修改只作用于 reference 模式。配餐中间件在带当前服务器 request_id 的最新 HumanMessage 之后查找唯一成功保存回执，并通过原 `planner_final_result` 重验当前 Run、完成工具审计、成员权限、选择和菜谱来源。确认后仍调用一次真实模型，但关闭工具入口，只完成最终回复。随后保留真实模型消息 ID、用量和审计身份，沿用原权威快照装配和发布事务，不合成 AIMessage，不把旧 tool-call 消息改成最终答案。

失败保存不形成候选；相同 Preview 可归一，多个不同 Preview 明确拒绝。旧请求、旧轮次或其他模式不触发收尾；缺少完成审计、来源失效或最终模型仍返回工具调用时失败关闭。没有成功保存回执时维持原配餐或具体补充问题路径。服务不新增数据库、依赖或配置，不修改营养计算、专业状态、权限、循环上限与发布 Owner。代码完成不代表真实双轮验收通过，状态继续保留 proposed。

本次再收窄 OpenAI 兼容模型的 reference 准备阶段：仅在仍有工具且模型是 `ChatOpenAI` 子类时，经原 handler 合并 `model_settings`，显式传入 `parallel_tool_calls=False`。原参数设置保留，必需 `query`、来源和授权校验不变；其他模式、其他模型和保存后的无工具收尾不注入该参数。不为缺失参数补造关键词，也不通过增加步数掩盖重复失败。并行调用本身是否导致空参数仍需真实供应商验证，该改动不能预报配餐成功。

## 替代方案

保留标题短路或单纯增加召回数仍会读取无做法资料。放宽引文和偏好会产生无法核对的结果。提高循环上限只延后同一失败；仅修改提示词不能阻止已保存后的再次工具调用。`return_direct`、直接结束图或合成最终 AIMessage 无法单独满足当前 Run 的真实 Model 审计关联，因此复用已有无工具最终模型调用模式，不另建发布通道。

## 验收标准

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 完整普通菜谱优于目录和疾病资料 | 目录标题占满候选 | search_reference_recipes | 真实 PG 检索 integration | 目录命中而普通菜谱仅正文命中 | Passed |
| 同一文档仅返回一个实际命中分片 | 长文重复候选 | search_reference_recipes | 真实 PG 检索 integration | 多分片同词占满结果 | Passed |
| 固定库、当前 Run 和引文边界保留 | 来源伪造 | read_reference_recipe / checked_reference_meals | 相关 unit 与 integration | 未检索读取及伪造引文继续被拒绝 | Passed |
| 成功保存后只进行一次无工具最终 handler 调用 | 模型继续检索直至循环超限 | MealPlanResultMiddleware | pytest test/unit/middlewares/test_reference_meal_finalization.py | 受控模型在工具仍开放时持续请求保存 | Passed |
| 当前请求、唯一回执和最终消息身份的回归边界保留 | 沿用旧回执或伪造最终 AI | planner_final_result / 原消息发布事务 | 受控生命周期 unit 与真实 PG/HTTP 服务测试 | 旧请求、失败保存、多 Preview、缺审计和失效来源 | Passed |
| OpenAI reference 工具准备请求透传串行参数且不污染其他分支 | 并行空参数持续重试 | MealPlanResultMiddleware / 原模型适配器 | 真实适配器的本地 wire 回归 | 非 reference、非 OpenAI、无工具和最终收尾不注入 | Passed |
| 真实用户流程完成保存与单餐调整 | 模型未保存 | Worker / daily plan service | 普通合成档案真实 E2E 与回读 | 不以问题正文或 completed 状态替代保存事实 | Not run |

main `b8946bd` 的正式候选实际执行 `pytest test/unit -m "not slow"`：5294 passed，收集错误和跳过均为零。真实隔离 PostgreSQL 上完整执行 `pytest test/integration/services/test_reference_meal_plan_http.py test/integration/services/test_onboarding_preparation_http.py`：34 passed。正式流程分别取得停止请求 ACK、原 PostgreSQL 进程退出码 0、自动移除和发布资源复核，随后 API/Worker 发布及健康、运行源码核对通过，其他服务未改变。

该版本的普通账号真实 E2E 随后失败：当前档案已读取，三份菜谱原文完成读取，保存工具有一份 completed 审计；模型仍继续调用工具，最终 `unexpected_error` 包含 recursion 错误，日计划没有完成发布。此失败是本次收尾修改的直接依据，不能用 5294 项单元或 34 项数据库测试替代真实配餐成功。

追加收尾代码的首次 Linux 完整单元结果为 5314 passed、1 failed，无收集错误或跳过；新增 21 项中 20 项通过。唯一失败把 LangChain 流末尾的空结束块当成正文消息，而实际正文与最终 State 的 provider ID 一致。测试现按精确非空正文选择唯一 chunk，并保留消息身份、用量与调用次数断言；本地原样 AST 诊断单例仅用于定位此 fixture，旧失败记录不改写。

修正后的冻结验证快照已实际执行完整 Linux `test/unit -m "not slow"`：5315 passed，新增收尾回归 21 passed，收集错误和跳过均为零；运行时 graph 已编译、实际导入且哈希一致。相同候选上完整执行上述两个真实 PG/HTTP 文件：34 passed，探针退出码 0 并自动移除。数据库清理分别核对正常停止 ACK、原进程退出码 0、自动消失和完整资源复核。首次 PG 入口曾因业务活动 gate 暂停；只读核对三项计数归零、PG intent 未写入、无遗留 slot 和精确基线未变后，才从原入口执行，暂停回执仍保留。

这些结果证明受控模型下的真实 graph/handler 生命周期及服务数据库边界；unit 使用服务 oracle，并不单独证明生产模型审计持久化或供应商调用。正式候选尚须绑定干净 main，并自行通过完整 Linux 单元和 PG/HTTP 发布门槛；真实普通账号双轮保存回读仍未通过，不能以 5315/34 项测试代替。

`42f9ae5` 的干净正式候选已自行通过 5315 项 Linux 单元与 34 项真实 PG/HTTP，正常清理、API/Worker 发布、健康和六个运行文件的哈希核对均通过，其他服务与内置 Skill 未变。其新普通账号 E2E 仍失败：30 个空参数错误全部为缺失 `query`，早期模型输出反复包含三个并行空参数检索；后来四个合法单次查询分别返回 4、4、1、1 个候选，均为 `ok`。日计划仍为空，未运行 read/save，原失败及暂停记录继续保留。

串行参数修改的冻结验证快照已实际通过完整 Linux 单元：5324 passed，其中本文件 30 项全部通过，收集错误和跳过均为零。新增六个 SDK wire 用例通过真实 `ChatOpenAI` 和仓库适配器，在内存 HTTP 边界检查载荷顶层参数；另三个排除边界用例通过。这不是供应商请求。相同候选的两个完整真实 PG/HTTP 文件共 34 passed；正常停止 ACK、原数据库退出码 0、自动移除、消失确认及资源复核通过。正式干净 main 候选仍须自行通过发布门槛，真实普通账号双轮保存与晚餐替换仍未通过。

此前隔离数据库验证曾在业务测试通过后以 `command_failed_docker` 结束，缺少原数据库退出码；该整体失败记录仍保留，没有因后续正式流程通过而改写。更早的 Windows/Linux 收集失败和局部测试记录同样保留。上述 5294/34 项结果绑定已发布的 `b8946bd`，不预报当前新增收尾代码已通过。

## 风险

正文匹配仍可能扫描固定库，返回四项不等于仅扫描四项。收尾仍需要一次真实模型调用，供应商超时不能改记成功；没有合法保存回执时也不能跳过资料缺口。工具完成审计必须在最终模型前可见，真实生命周期回归与 PG/HTTP 需继续核对这一顺序；缺失时失败，不忙等或补造。双轮真实测试须证明三餐已发布，以及仅换晚餐后早餐和午餐完整内容与来源保留，不能只比较状态或 Preview ID。
