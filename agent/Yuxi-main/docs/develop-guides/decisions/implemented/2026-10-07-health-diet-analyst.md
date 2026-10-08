# 已确认单餐的独立饮食分析师

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_diet_analysis_service.py

## 问题

已确认饮食具有不可变营养快照，独立分析需要明确成员、来源、处理用途和最终输出边界。读者为健康后端维护者。完整档案与专业目标尚未交付，单餐工程范围包括事实投影、缺失说明和餐次选择。

## 决策

HealthDietAnalystAgent、health-diet-analyst预设和family-diet-analyst内置Skill复用[成员绑定](./2026-10-04-health-consultation-binding.md)、PG Request/Run及worker。固定工具为有效餐次列表和确认餐次分析。diet_analysis用途单独配置模型、审批和处理同意；授权需要ai_use与diet_edit。纯事实读取接口只需要diet_edit，读取有效确认快照且不外发模型。

模型最终只提交记录标识与确认版本或补充问题；服务端重新读取确认来源，输出已有五项营养、份量比例、原计算来源和缺失说明。未知保持null，内容没有个人目标或临床适用性判断。流式正文片段受到过滤，最终正文使用服务器投影。原饮食快照保持不可变，不增加分析回执表或健康Schema版本。

健康repository验证历史完成输出及所有成功分析工具审计的来源，包括失败运行、补充问题和未被选作最终结果的餐次列表。旧来源失效后整个分析线程拒绝继续读取或外发；用户需要重新进入分析。通用输出持久化服务在当前Run lease锁内，使用同一事务重新核对审批、同意、授权与来源，重新投影并比较最终正文；成员锁持有到消息发布、output_message_id和completed共同提交。拒绝时回滚正文与终态写入。

## 替代方案

复用营养师自由文本会扩大原角色的用途和输出边界；增加分析回执表会维护一份重复的单餐事实。独立角色及只读投影复用已有持久化链路，周期派生结果未来需要单独设计失效和重算。

## 后果

日、7日、30日与反馈趋势、对话反馈写入、分析页面及真实模型质量仍待交付。个人目标和专业规则等待外部交付；单餐运行成功不代表完整角色或产品闭环完成。审批默认关闭，测试只配置独立Compose中的内部合成服务。管理配置页面尚无分析模型字段，前端对接需同时保留全部用途配置，避免完整替换时清空已配置的模型。

历史审计包含来源，源撤回会使整个线程不可用。成员锁对发布与撤回排序：先提交的有效输出可完成，先提交的撤回阻止后续发布；已外发内容无法追溯撤回。服务器完整投影比较使营养、缺失和边界字段不由模型或checkpoint任意改写。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 来源与缺失准确 | 模型伪造营养/来源 | analysis service、types | test/unit/services/test_health_diet_analysis.py；test/integration/services/test_health_diet_analysis_http.py | 空值、无份量、版本不符、跨成员 | Passed |
| 独立审批与固定资源 | 咨询同意冒充分析用途 | consultation service、preset | test/e2e/test_health_diet_analysis_e2e.py | 未审批、不同用途、失效执行者；Skill及两工具manifest回读 | Passed |
| 发布与撤回同事务 | 投影结束后同意/来源撤回 | chat service、analysis service | test_analysis_withdrawal_blocks_publication_and_all_successful_audits | 投影后真实PG撤回同意/来源，再调用输出Owner；无正文及完成状态 | Passed |
| 历史工具来源有效 | 失败/提问/未选中的列表来源失效 | analysis repository | 同一真实PG参数化测试 | 三种成功工具审计在撤回后均拒绝读取 | Passed |
| 实际模型选择质量 | 模糊意图/选择不当 | 供应商与业务评审 | 独立质量样本与真实用途审批 | 合成回放不能证明语义质量 | Not run |

定向unit五个文件64项、真实HTTP/PG一项通过；独立Compose中真实PG与worker/SSE六项通过。共享chat stream服务31项回归通过。独立源码复核通过。

手算oracle使用合成食品：150g乘摄入比例0.4，再按200kcal/100g得120kcal；蛋白质6g、脂肪3g、碳水15g、钠null。真实worker覆盖成功选择、补充问题、伪造营养、跨成员及旧版本五个模型分支，最终Message、Run输出与源快照从PG回读一致。真实供应商、分析前端与专业质量验收为Not run。
