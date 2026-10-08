# 固定初始个人与家庭配餐Agent运行

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_initial_planner_service.py

## 问题

[初始配餐后端](../implemented/2026-10-08-health-initial-meal-generation.md)能从批准目录生成初版，现有配餐Agent只支持通用单成员草稿或已有家庭餐单。需要在固定用户选择下执行首次个人/家庭三餐生成，结果可沿用显式确认保存，并证明实际Run/worker和消息发布边界。读者为健康后端与Agent维护者。

## 决策

独立初始线程绑定日期、个人/家庭范围、每餐参与者和全体档案/规则版本及实际目录来源摘要。与已有家庭选择互斥，任何参与者均须ai_use、diet_edit、profile_view及当前meal_plan用途同意。复用初始生成和质量Owner；代码没有新增医学阈值或默认份量。

固定两个工具读取已授权上下文和生成预览，不接受选择、身份、营养值、保存或审核参数。预览回执绑定当前Run、账号与线程，包含完整服务器结果；无解或预算耗尽也保留明确只读结果。最终只能选本Run回执或澄清问题，checkpoint历史核验原Run身份及固定来源。发布事务重新检查全员授权、同意、来源和完整结果，失败不发布Message或完成Run。正式保存继续由用户通过原初始确认Owner执行；非就绪回执显式拒绝保存。

Schema15增加可空初始线程选择及初始预览Run/线程关联，正式迁移保留已有HTTP预览、单成员和家庭线程。业务Skill增加两项依赖和明确模式说明，运行时按三种模式分别固定工具，元数据并集不开放其他模式工具。

结构化健康角色的校验失败、未经发布的审计指针与终态State工具历史均须隔离未核验正文。配餐、饮食分析与质量这三个结构化角色的非中断执行异常由Run错误和独立审计表达，不保存未经核验的部分正文；普通结果按实际Run排除这三个角色的审计，普通历史保留通用角色的State工具兼容，结构化健康角色只展示正式发布内容。验证回放工具调用携带非空未核验正文，失败Run无普通assistant Message，SSE/result/history均无该正文，恢复有效回执仍完成。

## 替代方案

用旧通用草稿工具生成会允许模型指定未批准份量；将新选择塞入已有家庭选择会混淆首次生成和改版对象。独立可空绑定保留既有语义，复用生成Owner避免第二套配餐算法。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 初始模式仅固定两个工具并复用批准生成 | 自由身份、份量或工具扩张 | 线程parser、context及graph | unit与实际worker manifest/结果/PG | 额外参数、非初始调用、未就绪不能保存 | Passed |
| 全员同意与固定来源贯穿运行 | 仅入口同意、变源后复用、旧租约写回执 | consultation及initial planner Owner | HTTP与真实PG等待/撤回 | 第二成员撤权/撤同意、规则/配方变化、幂等异参 | Passed |
| 最终与历史只接受真实回执 | 跨Run伪造、checkpoint推测、正文泄漏 | 结果与发布事务 | API/worker/SSE、PG消息回读 | 伪造/跨Run选择、发布前撤回、失败无普通Message/完成态 | Passed |
| 增量迁移与旧模式保持 | 旧预览/绑定丢失、旧工具意外启用 | 正式迁移与固定资源Owner | 13/14→15重复迁移PG及既有回归 | NULL关联旧HTTP预览、家庭/单成员固定工具 | Passed |

206项不同相关unit分组通过：初始/家庭运行、生成、咨询、迁移与发现118项，既有营养师/通用配餐/质量53项，结果Repository及State发布35项；回放3项属于118项，不重复计数。三个结构化健康角色的部分输出拒绝、正式结果/旧NULL兼容、通用工具审批和历史兼容分别核对。

26项不同HTTP/PG案例分组通过：初始运行18项及已有家庭替代工具1项，三个结构化角色的实际部分消息Owner3项，completed/failed旧审计指针与普通历史2项，正式13/14→15及重复迁移2项。授权等待及生成之后自然lease到期均重读零回执；实际发布Owner的失败不留下Message/完成状态，恢复来源和lease后可以正式发布。非匹配批准人群菜单保留not_ready回执，明确用户确认仍409且无Plan/Check/Review。

12项不同E2E分组通过，其中6项实际API/worker/SSE回放及6项直接PG发布/checkpoint边界。初始个人及家庭各执行两轮生成、澄清问题、伪造最终输出与跨Run回执，核对固定两工具/Skill、实际Run收据、权威Message和用户显式确认的初版。工具调用携带非空`UNVERIFIED_INITIAL_MODEL_TEXT`，逐轮SSE、结果与普通历史无正文；独立审计仍保存其事实。第二成员或个人用途同意撤回后私有结果/历史及新请求拒绝，恢复同意可显式保存。

最后顺序复验5项全部通过，命令为`python -m pytest test/e2e/test_health_initial_planner_e2e.py test/e2e/test_health_meal_planner_e2e.py test/integration/services/test_health_initial_planner_http.py::test_structured_health_audit_body_stays_private_in_pg -q -p no:cacheprovider`，环境为独立Compose API的`TEST_BASE_URL=http://localhost:5050`及`HEALTH_CONSULTATION_E2E_ISOLATED=true`。此前一个批次的个人初始fixture读取配置超时、旧通用配餐断言仍期待空错误Message，均不作为整批通过证据；顺序复验对应失败面通过，没有扩大超时。既有家庭及质量9项在相同源码的前一分组通过。27个相关Python文件Ruff与格式检查通过；工程契约及62项gate测试通过，独立Reviewer核对完整边界和负控。

## 后果

用户固定的日期、参与者或任何来源变化后需要重新选择线程。初始模式的预览与历史涉及全部选定成员，任意成员撤回授权或用途同意时整体拒绝访问。结构化角色失败以Run错误表达，原始模型正文仅在独立审计可见；普通聊天的部分输出和工具审批继续采用原协议。

合成资料与协议回放只证明工程；红阳完整档案、生产专业规则、真实模型质量及小程序仍待交付。六Agent总体继续按[完整工程目标](../proposed/2026-10-07-health-agent-engineering-completion.md)执行。
