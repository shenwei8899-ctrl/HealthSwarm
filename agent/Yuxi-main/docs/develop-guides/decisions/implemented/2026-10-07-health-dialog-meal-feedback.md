# 明确选餐后的对话反馈写入

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_dialog_feedback_service.py

## 问题

六Agent工程目标要求在对话中明确关联餐次并幂等保存反馈。模型不能把模糊的“午餐”猜成任一记录，也不能复制旧消息或将自述改变为营养值。读者为健康后端及小程序联调维护者。

## 决策

用户经业务API显式选择一条有效确认餐次及来源版本，服务器建立不可变反馈会话绑定，复用饮食分析师的独立用途和Run引擎。该会话只开放读取选定餐次上下文、保存本轮原文反馈两个工具；普通分析会话无写权限。工具不接受成员、餐次、Run、消息ID或标签解释。

保存须逐字匹配当前Request的PG用户消息，且用户显式以“记录这餐反馈：”或“更新这餐反馈：”开头。可用“吃完程度：一半；口味：偏咸；自述：……”明确填写结构字段；自由自述原样保存，不猜测结构标签。更新未明确的结构字段时保留已有值。反馈版本须匹配，收据键从服务器Request派生，重放不增加版本或恢复撤回。一次反馈会话仅处理一个写入请求；后续修改可用既有管理API或重新选择该餐建立新反馈会话。

Schema9新增选餐绑定和写入来源表，复用原反馈/修订/权限Owner，不修改DietLog。来源记录绑定原消息、Run及修订，最终模型只返回feedback_saved或补充问题；服务器从本Run收据投影结果。发布事务重新校验审批、同意、来源和反馈版本，修改撤回使旧结果及后续模型输入失效。模型正文不直接发布。

反馈写入与管理写入均先取得Request派生的幂等advisory锁，再取得成员授权锁。执行者校验仅锁AgentRun行，避免加入Conversation行锁后与请求提交的成员→会话锁序互相等待。已取得本Run写入收据时，最终结果始终投影已保存；模型补充问题不能隐藏已提交副作用。反馈模式的LangGraph有限节点预算为40，普通分析保持20；授权、计量与投影节点同样计步，反馈读取、保存和幂等重放须在正常链路内完成。独立质量模式的预算由[质量阶段决策](2026-10-07-health-quality-review.md)说明。

## 替代方案

模型自由传餐次ID缺乏用户选餐依据。仅在prompt要求明确来源无法阻止绕过。把聊天原文直接映射长期健康限制会扩大单餐自述语义。固定选餐会话和当前消息收据复用已有反馈模型，并允许后续入口添加餐次选择UI。

## 后果

后端选餐关联与受控反馈写入已交付，饮食分析师预加载Skill版本为2026.10.07.3。一次会话的写入Request完成后，后续修改使用管理API或建立新的用户选餐会话；旧反馈修改或撤回后，旧Run结果不可继续展示或作为模型输入。选餐与分析页面、持久派生刷新、专业统计规则及真实供应商质量仍待交付。整个角色及[六Agent目标](../proposed/2026-10-07-health-agent-engineering-completion.md)保持未完成。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 用户选餐不可被模型替换 | 跨成员、草稿、旧确认、错用途 | 选餐绑定与反馈服务 | test/integration/services/test_health_dialog_feedback_http.py及tool schema unit | 未选餐、伪造身份、同键改餐、无权限、metadata篡改 | Passed |
| 写入有本轮原文依据且幂等 | 旧消息、模型编造、重放恢复 | Request原消息、反馈修订及来源表 | test/unit/services/test_health_dialog_feedback.py及反馈E2E PG回读 | 无显式写意图、原文不符、过期版本、撤回重放 | Passed |
| 最终结果属于本Run并仍有效 | 别Run收据、反馈更新后旧正文外流 | 最终投影及发布事务 | test/e2e/test_health_dialog_feedback_e2e.py的实际worker/SSE及PG负控 | 伪造成功、发布前撤同意/源/反馈、原消息或checkpoint篡改、已写后提问 | Passed |
| 并发锁序一致 | 执行者会话锁或成员锁先于advisory导致死锁 | consultation repository及反馈服务 | 同一真实PG E2E的两项并发负控 | 锁Run后可按成员→会话取得锁；等待advisory时成员锁仍可用 | Passed |
| 增量Schema保留旧数据 | 旧行丢失、重复迁移失败 | PG迁移Owner | test/integration/services/test_health_memory_schema.py | Schema4–8既有成员和撤回记忆保留、重复DDL | Passed |
| 普通分析用途与工具保持有效 | 反馈权限泄漏到普通模式或发布回归 | analyst graph及publication | test/e2e/test_health_diet_analysis_e2e.py | 普通会话不能写反馈、单餐/周期/伪造/跨成员/旧版分支 | Passed |
| 专业规则及真实模型质量 | 合成协议被当作正式质量验收 | 外部内容和模型评审 | 独立生产验收 | 尚未执行 | Not run |

71项相关unit、1项真实HTTP/PG、5项Schema升级及重复迁移、10项反馈PG/实际worker/SSE和11项普通分析E2E通过；预算修订后的37项周期/反馈/咨询unit通过，与前述unit集合有重叠。合成协议回放按独立预期检查反馈版本、字段、原消息及Run来源，管理API修改v2使旧Run失效，新选餐会话更新v3，原DietLog快照不变。独立源码复核通过。真实模型意图质量、专业趋势规则和完整档案未验收。
