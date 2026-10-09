# 本人选定实测体重与批准营养目标的来源联动

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_dependency_service.py

## 问题

本人实测体重能被咨询读取，批准目标与配餐使用的专业投影却不能证明其体重参数对应哪条测量。更正或作废被选记录后，旧专业批准与正式采用不能继续作为当前结果。

## 决策

### 实现方案

ProfileImport的可选weight_measurement_source只接受明确选定的record_id与严格正整数version，并要求同时提交family_profile_source。健康授权与管理员导入权限沿用现有服务；在健康成员锁后取得家庭来源锁，以本人关联身份读取选定的有效weight记录，核对版本、非未来测量时间及与专业payload.weight_kg的Decimal等值。服务端把来源坐标、kg单位、测量时间、来源与真实内容摘要写入已有attestation，不接受客户端提供来源摘要或覆盖专业体重，不新建表或迁移。

HealthQualityRepository统一重验选定来源及专业参数，来源变化时返回not_ready、隐藏专业正文且不退回旧版本。正式关联投影缺少明确体重来源时，批准公式只在实际使用非零体重系数时返回selected_weight_measurement_required；零系数不要求未使用字段，未关联的独立外部专业投影保留原契约。个人目标与质量计算使用相同约束，个人/家庭初始生成、换菜、重生成、参与者调整、Planner、复核与正式采用继续消费现有质量边界。

FamilyService更正或作废选定记录时，在拥有家庭事实的同一事务中精确失效相关审核与正式采用，不反向取得健康成员锁。无实际更正、重复作废、新增或修改未选记录不改变旧绑定；异常时测量与失效写入一起回滚。停用关联成员使当前投影和目标不可用，并在停用事务内失效旧审核及采用；恢复成员后当前来源可再次就绪，旧审核及采用仍保持失效。选定记录变更后的重算要求新专业确认版本及新的检查、批准和本人采用。

本决定扩展[正式本人档案与营养安全投影的来源关联](./2026-10-08-family-nutrition-safety-source.md)，明确绑定一个实测参数；其余身体参数、疾病/过敏编码及专业含义继续由专业方确认。来源证明本身不表示安全检查通过，原始档案的full_health_profile_available及nutrition_safety_ready继续保持false。

## 替代方案

自动采用最近记录会隐含选取时效与业务确认。由模型覆盖专业体重会绕过确认。只为目标接口增加临时测量参数会使目标、配餐及复核使用不同依赖；复用专业投影和统一质量入口，使业务快照、Run与最终结果仍绑定同一专业内容摘要。

## 后果

已关联但未登记选定来源的专业投影，在非零体重公式下明确未就绪；专业方通过受权导入接口登记新的确认版本。明确选择较旧的有效非未来记录仍受支持，不从近30日列表自动取最新记录，不自行设定体重有效期。

本阶段交付接口、来源证明、计算消费与失效保护。[专业档案导入与明确体重选择后台入口](./2026-10-09-professional-profile-weight-entry.md)已提供受权来源读取、明确体重版本选择、专业导入、目标展示和餐单失效回跳。完整sex/age/height/activity参数语义、适用人群及生产专业公式、生产资料、完整多人联调、小程序和真实外部模型质量仍待交付。合成测试公式不构成临床规则；完整健康档案、角色及产品父项仍部分完成。本地Word、Excel及记录Skill独立维护，不提交或上传。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 本人明确记录、版本、原值与服务端摘要绑定 | 他人/错误类型/作废/未来记录、伪造摘要、无关联或值不符 | DTO、dependency service、family profile repository | 新来源unit及test_health_weight_targets_http.py | 客户端摘要与布尔版号拒绝，旧记录不会自动切换到新记录 | Passed；真实HTTP/PG与独立摘要 |
| 目标与配餐检查消费同一依赖 | 目标单点修改、缺源继续计算、零系数误阻断、旧投影回退 | personal targets、quality checks、quality repository | 相关unit、个人/家庭初始生成及保存计划质量HTTP | 非零缺源not_ready/unknown，零系数与未关联旧契约保持 | Passed；独立手算330→335 |
| 变源同事务精确失效且不复活 | 延迟GET才失效、无关记录误失效、异常部分提交 | family service与repositories | 真实HTTP写入后立即PG读取review/adoption及不可变快照，回滚与成员停用/恢复 | 更正/作废与停用后立即失效，无变化/未选记录不失效；恢复不复活 | Passed；直接持久化结果 |
| 来源读写使用真实家庭锁顺序 | 并发更正在读取期间修改已选来源 | family profile repository与family service | 来源读取Owner真实PG事务持家庭锁，实际HTTP更正的pg_blocking_pids指向该事务 | 释放后更正提交，旧目标不可用，新专业版本目标335 | Passed；来源Owner PG持锁、HTTP更正等待 |
| 历史、checkpoint和最终发布拒绝旧来源 | 旧Run继续读取、恢复同意或迟到发布复活旧输出 | 现有quality运行/发布与来源边界 | test_health_weight_targets_e2e.py真实Worker两轮、SSE、工具审计、PG Message/check与checkpoint | 更正后旧请求、结果、历史与checkpoint拒绝，种子PG执行Owner迟到发布拒绝 | Passed；实际Worker与补证分别记录 |

281项相关单元测试通过，由103项目标/投影/质量/初始生成、98项家庭/参与者/Planner/采用/营养师消费回归、63项新增体重来源及17项写入失效测试组成，四组无重叠。冻结源码与测试后，完整真实HTTP/PG批次28项通过（541.93秒），包括成员停用/恢复、精确PID锁等待、立即失效、不可变历史、无变化/未选记录及事务回滚。10个业务模块与4个测试文件在最终HTTP批次前后保持相同SHA-256。早期失败批次和定向复验不重复计入完成数量。

隔离Worker E2E共1项通过（49.39秒），包含实际质量Worker两轮、SSE、真实工具审计、PG检查与Message及实际checkpoint；合成公式独立手算30+5×60=330。体重更正到61后，旧请求、历史、结果、checkpoint与种子PG执行Owner迟到发布被拒绝；重新导入专业版本后，真实目标HTTP得到335。新335目标没有额外Worker执行，真实外部模型质量仍待验收。

5项独立进程负向控制分别恢复目标缺源旁路、当前来源解析旁路、质量计算缺源旁路、导入原值不一致旁路及更正即时失效缺陷，均在对应业务断言失败，符号恢复不修改生产文件。初次导入负控的harness授权失败不计入有效证据。14个相关Python文件Ruff及格式检查通过；工程门禁106份决策/241份文档与63项检查器unit通过。

隔离PG清理回读active_runs、leased_runs、合成账号、家庭及测量均为0。E2E使用已有合成回放，生产专业资料、真实外部模型、完整多人产品入口和Word分页未验收。

验证入口：默认Compose API内执行`uv run --no-sync --group test pytest`对应单元文件及`test/integration/services/test_health_weight_targets_http.py`；隔离`health-diet-analysis-e2e`项目API在`HEALTH_CONSULTATION_E2E_ISOLATED=true`下执行`test/e2e/test_health_weight_targets_e2e.py`。测试使用独立Schema或隔离合成槽位，未使用真实健康资料或生产专业数据。
