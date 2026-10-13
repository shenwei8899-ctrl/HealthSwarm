# 审核科普按登记范围供固定 Agent 使用

状态：implemented
类型：feature
Owner：backend/package/yuxi/repositories/health_evidence_repository.py

## 问题

计划 TODO02.1 要求专业资料的来源、许可、版本、审核依据和使用范围。不可变审核片段、词法索引、同 Run 引用及校验后发布已具备，但四个教育角色曾从同一审核池检索；来源存在不能证明该资料已获准供某个指标角色使用。资料的领域与适用条件也需要结构化发布记录。

本决定补齐显式登记范围的工程边界，复用现有来源、引用、事务和固定角色。真实专业材料、许可真实性、内容正确性、专项人群字典与匹配规则由原负责人提供并审核；02.1整体仍为部分完成。

## 决策

### 实现方案

管理员发布 DTO 提供可选的 `reviewed_scope`，登记 `domains`、`population_category`、`population_description`、`exclusion_conditions` 和 `license_ref`。领域对应普通咨询及三个指标角色；模型工具只接受 query，service 从真实 Run 传递角色。范围随不可变资料版本发布，调整时发布新版本并按现有机制撤回旧版本。

PostgreSQL 健康 Schema 24 增加来源的 `reviewed_scope` JSONB、来源和引用的 `scope_hash` 三个可空字段，保留旧正文、引用与用户资料。摘要对全部登记字段做规范 JSON SHA-256，随引用持久化。未登记范围的旧来源延续原普通咨询通用科普语义，指标角色须有明确登记。已登记资料只有 `general_education` 且排除条件为空时进入当前教育流程；需专业人群选择或有排除条件的资料等待正式匹配契约。

repository 在索引前按真实角色、领域和通用适用类别筛选，命中后使用 `FOR SHARE` 与 `populate_existing` 读取当前来源，复核正文、版本、范围和摘要。引用校验同时连接真实 Run 与 Conversation 归属；最终提交、当前结果、引用、历史及 checkpoint 工具历史均重新校验当前角色与范围。模型不提供角色、人群或批准标记，原管理员发布与撤回权限沿用现有 Owner。checkpoint 失效在 Worker 模型执行前拒绝旧引用；入口已经接受 Request 时以 Run 最终状态表示失败。

## 替代方案

只在提示词或前端标签中约束领域无法保护工具调用和历史复用。根据查询词、健康指标或生日推断专业适用性缺少批准规则。将旧片段默认共享给所有角色会扩大原审核范围。显式记录使用范围并复用现有 PG 校验保持一条来源链；代价是专项资料在专业匹配条件就绪前不能用于解释。

## 后果

通用咨询兼容未登记范围的旧资料，三个指标角色只用明确登记本领域的通用片段。`has_current_sources` 和成员就绪诊断仅表示目录存在，不能证明某一角色有匹配片段。范围登记与摘要核对保证工程使用边界，许可和医学语义仍需专业审核。缺资料时可追问；范围失效后旧正文、引用和 checkpoint 不能继续供模型或普通客户端使用。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 当前角色只取得允许的通用片段 | 跨域候选、旧范围缓存或受限人群进入索引 | evidence repository / search service | 范围单测、真实 HTTP/PG 与四角色 Worker 回放 | 检索前/后范围哨兵；异 Session 改范围后缓存回读 | Passed：218项定向单测、3项真实HTTP、4项Worker E2E通过，均零跳过；缓存真实PG正向通过，关闭fresh的负控命中 |
| 引用、终态与历史重验登记范围 | 旧引用、跨角色与 checkpoint 绕过范围 | evidence validation / consultation history | 实际 Run、Message、Task、result、history 和 checkpoint 回读 | 改范围、跨角色、需专业选择、带排除条件 | Passed：四角色最后20个真实Run中8完成、12失败；失败无权威Message或输出指针，旧正文拒读，checkpoint失效在模型前关闭 |
| 旧数据保留且不扩大历史审核 | 迁移删数据、默认指标共享、重复迁移 | health schema migration / models | 真实PG23→24及重复执行、旧正文/引用回读 | 旧普通咨询引用有效，指标旧资料拒绝 | Passed：真实PG升级两次，10表合成事实保全；旧普通咨询兼容、三指标拒绝；新增3列为SQL NULL |
| 工程复用和专业交付状态准确 | 重做既有发布或把合成资料当首包 | owning docs / local Word and Excel | 独立Review、工程gate及双份文档回读 | 02.1整体部分完成，专业资料和许可审核仍待交付 | Passed：工程gate与63项规则单测通过；Word V1.66及Excel已回读，02.1部分完成未勾、DONE76独立摘要、原状态和公式保全 |

范围回归的七类缺陷恢复在18项目标断言上失败，零 setup error 与跳过；缓存强制刷新关闭后另有8项目标断言失败，真实PG缓存负控也在旧正文被错误接受的位置失败。隔离回放只用合成资料与模型，不证明真实供应商模型效果或专业知识准确性。完整专业首包、许可真实性、人群匹配字典及专业质量继续按 TODO02.1、02.2、14.1、03.2 验收。
