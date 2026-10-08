# 已确认饮食的自然日周期事实分析

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_diet_analysis_service.py

## 问题

用户要求完成六个营养业务Agent工程范围。饮食分析师的单餐投影已交付，周期分析需要回答实际记录覆盖、营养缺失及餐后反馈。目标读者为健康后端及业务联调维护者。本记录只收敛周期事实阶段，[六Agent总体提案](../proposed/2026-10-07-health-agent-engineering-completion.md)仍未完成。

## 决策

周期按Asia/Shanghai实际摄入时间计算1、7或30个自然日，含结束日，不使用确认日期。输入拒绝未来日期及UTC不可表示的边界。新增无模型事实读取POST /api/health/v1/members/{member_id}/diet-period-analysis；独立分析Agent增加固定analyze_confirmed_period工具。Skill版本2026.10.07.2和最终选择器支持周期或单餐或补充问题，身份与Run仍来自服务器。

每个有效确认快照复用单餐来源校验和五项营养投影。仅全部记录已知时返回recorded_total；部分已知返回known_sum及缺失记录数；空窗口和无记录日期保持null。覆盖列出有记录日和未记录日，不推定每天三餐或用户没有吃饭。超过1000条记录显式拒绝，避免分页截断产生假全量结果。撤回源从新计算排除并计数；当前用户、成员与有效记录绑定的有效反馈只统计标签、摄入状态和分母，不修改原营养。批准统计规则未交付时不输出趋势方向或个人目标。

历史完成输出和所有成功工具审计均复核。周期采用完整窗口重投影比较，新增餐食或反馈也使旧结果失效。外发模型前直接校验当前checkpoint中的成功工具结果，不依赖工具审计异步写入已完成。最终正文由服务器当前数据投影，发布Owner在同一PG事务复核审批、同意、授权、窗口及反馈后提交；不接受模型提交营养值。旧线程失效后重新进入分析。

## 替代方案

按确认时间聚合会把补录餐食放错日期。只核对已列出来源ID无法发现窗口新增餐食与反馈；完整窗口重投影复用事实Owner，避免重复持久化一份可能过期的统计结果。保存派生状态与后台重算属于后续交付，本阶段读取实时计算。

## 后果

事实汇总及即时失效已交付。[明确选餐后的对话反馈写入](2026-10-07-health-dialog-meal-feedback.md)由独立阶段收敛。审核统计口径、最小样本和专业趋势判断、持久派生重算、页面配置与真实供应商质量仍待交付。完整档案保持外部TODO。窗口最多1000记录且逐条检查来源；后续容量需求应由真实消费者和性能证据驱动。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 真实日期、营养及缺失准确 | UTC跨日、未知当零、空日被算未进食 | analysis service/types | test/unit/services/test_health_diet_period_analysis.py | 1/7/30日、真假零、半选择器、最早日期溢出 | Passed |
| 来源、成员与反馈隔离 | 跨成员、错误反馈所有者、窗口静默截断 | analysis repository、HTTP入口 | test/integration/services/test_health_diet_period_http.py | 边界餐次、撤回、第二用户、未来日期、1001条拒绝 | Passed |
| 新增与变更使旧结果失效 | 只验证旧ID而漏掉新增记录/反馈 | analysis repository、consultation service | test/e2e/test_health_diet_analysis_e2e.py | 反馈改版、新餐、新反馈、只有checkpoint而无PG工具审计 | Passed |
| 最终输出同事务验证 | 计算后撤回或反馈变化仍发布 | analysis service、chat service | 同一真实PG参数化E2E | 修改后无最终Message或completed输出 | Passed |
| 实际worker投影准确 | 模型补营养、错误选择或漏源校验 | graph、fixed tools、server publication | 合成协议回放的period分支，PG/SSE回读 | 原单餐/提问/伪造/跨成员/旧版分支一起回归 | Passed |
| 专业趋势和真实模型质量 | 合成回放被当作专业评审 | 外部审核规则、模型质量评审 | 独立生产交付及验收 | 尚未执行 | Not run |

51项定向unit和2项真实HTTP/PG测试通过；隔离Compose中11项PG与实际worker/SSE E2E通过。独立手算7日窗口3条各120kcal得360kcal，2个有记录日、5个未记录日，未知钠保持null；1日两条得240kcal。独立源码复核三项修复后通过。未调用真实供应商、未完成六Agent整体目标。
