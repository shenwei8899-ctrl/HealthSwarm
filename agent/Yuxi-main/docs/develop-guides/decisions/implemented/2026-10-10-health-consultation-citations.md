# 成员咨询最终引用的受权读取

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_evidence_service.py

## 问题

成员咨询的最终答复使用当前Run引用回执，但公开结果接口只返回字符串。客户端无法在不接触工具审计的前提下读取实际采用的原始片段、来源版本和当前有效性。[本人营养咨询接入](../implemented/2026-10-10-miniapp-nutrition-consultation.md)保留了正式引用范围。

## 决策

### 实现方案

`GET /api/health/v1/consultation-runs/{run_id}/citations`由已认证账号读取一个完成的专属咨询Run。证据service复用Run与成员授权，repository额外核对Conversation当前actor、线程和专属角色，严格使用该Run的`output_message_id`及同Run、同Conversation、同Request的完整正式assistant Message；没有指针或指针无效时明确失败，不启用通用历史completed Run的兼容回退。该新增接口面向当前可证明的引用，既有通用结果接口的历史兼容政策保持在原Owner。

最终文本中的`[证据:UUID]`决定公开引用集合和顺序，重复引用只出现一次。repository复用既有actor、成员、Conversation、Run、来源hash、撤回和有效期验证，返回正文、来源、版本、审核日期及`general_education`范围。引用查询不返回最终答复正文、不公开未被答复采用的检索结果，也不把引用有效性等同于医学结论审核。读取权限依赖当前健康授权，管理员不具有旁路。

输出包含Run、Request、线程、成员与最终Message标识及明确的`cited`或`not_cited`状态。非专属咨询或无权访问返回404；Run未完成及无权威最终消息返回409；引用归属或标记异常返回409；撤回、过期或正文hash变化返回410，错误不包含健康正文。接口不创建引用、不使用执行lease、不调用模型，不改Schema或页面。

## 替代方案

公开本Run全部引用行会泄露只检索而未采用的来源。读取通用工具审计扩大健康客户端所需权限。只返回最终文本中的UUID无法证明当前来源有效性。兼容猜测最后一条assistant可能读取审计或缺少明确结果发布事实，因此新接口要求现有权威指针。

## 后果

客户端获得实际采用片段及明确来源，证据读取不扩大工具审计权限，也不产生新的引用或健康事实。无权威指针的旧咨询不能使用这个新增投影；通用结果Owner保留其原有兼容政策。来源有效性与响应在当前查询事务内核对，响应发出后的撤回由下一次查询反映，不承诺客户端已缓存字节可远程撤回。一般科普的审核来源不授权个人诊断或治疗。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 只公开最终答复采用的同Run引用 | 工具检索集合、相邻输出 | evidence service/repository | 专属unit、真实HTTP/PG、nutritionist worker E2E | 3条检索只采用2条、旧Run、错误指针、审计消息、未完成 | Passed |
| 账号、成员、线程和来源保持当前有效 | HTTP与PG | health授权及evidence repository | 真实HTTP/PG回读与负控 | 跨账号/成员/线程、admin/superadmin、撤权、撤回/过期/正文hash篡改 | Passed |
| 只读响应与稳定Schema | 协议、持久化 | evidence DTO/service、health router | 严格DTO及真实HTTP字段与no-store、PG引用回读 | 无引用、重复引用、非法标记、无pointer | Passed |
| 当前真实角色工具oracle有效 | shipping Skill/worker | nutritionist E2E fixture/oracle | 实际11工具Skill与本地合成模型Run、PG最终Message | 删除四个正式记录工具中的任一个时oracle失败 | Passed |

2026-10-10在既有`health-diet-analysis-e2e`隔离槽位执行：

```bash
docker exec health-diet-analysis-e2e-api-1 pytest test/unit/services/test_health_consultation_citations.py test/unit/services/test_health_consultation_replay.py -q -p no:cacheprovider
# 99 passed，21.07s
docker exec health-diet-analysis-e2e-api-1 pytest test/integration/services/test_health_consultation_citations_http.py -q -p no:cacheprovider
# 2 passed，16.96s
docker exec -e HEALTH_CONSULTATION_E2E_ISOLATED=true -e TEST_BASE_URL=http://localhost:5050 health-diet-analysis-e2e-api-1 pytest test/e2e/test_health_nutritionist_e2e.py -q -p no:cacheprovider
# 1 passed，29.66s
```

六个相关源码/测试文件的ruff check与format --check通过。真实Worker通过FIFO/SSE完成咨询，回读PG `Run.output_message_id`及最终Message后，引用HTTP返回相同Run/Request/Message和实际来源；伪造引用的Run失败并在引用接口返回409，撤回来源后返回410。fixture精确清理后PG本次测试账号、Run、引用、来源及临时模型供应商全部为0；处理政策、咨询模型和审批处理方回读为空，本次本地8766重放进程已停止。主服务与正式云审批未修改。

当前证据来自合成数据与本地确定性模型；生产专业语料、真实供应商和正式页面独立验收。
