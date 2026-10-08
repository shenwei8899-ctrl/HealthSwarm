# 家庭档案新版查询与 Agent 来源兼容

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/repositories/health_measurement_repository.py

## 问题

家庭档案的分页查询拥有有效测量的筛选和总数，独立实测 Agent 仍调用被移除的列表接口会在体重或血压读取时失败。停用成员的正式来源同样需要遵循家庭档案当前可见性。

## 决策

### 实现方案

共享测量 repository 使用正式 FamilyRepository.measurement_page，读取固定本人、固定指标和冻结的 30 个上海自然日，最多返回 20 条。查询默认排除作废记录，数据库有效总数决定截断标记；原始值、独立版本、单位及 JSON 摘要协议保持稳定。

档案关联和来源读取由 HealthFamilyProfileRepository 统一拒绝停用来源，家庭及当前本人身份校验继续使用正式家庭 repository。测量回执沿用当前来源重读，已引用的测量作废后，普通读取排除该记录，历史和 checkpoint 的原摘要校验失败。

storage-migrator 保留 business11 的家庭字段升级与 health18 的独立测量依赖，真实迁移测试同时检查两域版本、旧授权保留及失败后重跑。前端家庭面板测试显式注入所需 Vue API，避免将 Node ESM namespace 中的非标识符导出作为 Function 参数。

## 替代方案

恢复旧家庭列表 API 会增加重复查询契约，选择旧家庭 repository 会覆盖现有分页、作废与统计能力。使用正式分页接口能直接遵循当前数据 Owner，局部适配完成后即可验证，因而采用同一变更内的 implemented 修复记录。

## 后果

正式测量作废不会删除原值或审计，Agent 的可用输入以当前有效事实为准。成员停用检查也覆盖数据库已有的停用来源；家庭 Owner 停用本人的操作仍由正式业务接口拒绝。本决定接续[家庭档案交付](2026-10-08-family-archives-completion.md)、[体重读取](2026-10-08-member-weight-agent-read.md)与[血压读取](2026-10-08-member-blood-pressure-agent-read.md)。完整营养安全字段、专业规则和真实模型质量继续按原范围验收。

## 验证

相关后端 unit 150 项、全量 3504 项通过；59 项配置检查因容器未挂载仓库根目录跳过，当前真实配置快照的独立补验 66 项全部通过。真实 JWT/HTTP/PG 健康接口 32 项通过，覆盖测量作废后普通读取排除、原始事实保留、历史和 checkpoint 失效，以及停用来源的关联和读取拒绝。家庭迁移 5 项、正式档案接口 14 项回归通过。移除停用守卫的独立负向控制使两个来源测试按 HTTP 200 不等于 404 正确失败，正式源码保持不变。

相关前端 unit 22 项、lint 与构建通过；Ruff 检查和 347 个文件的格式检查通过。工程门禁覆盖 102 项决定和 237 页文档，门禁单测 63 项通过，文档构建通过。开发数据库先保留可读归档备份，再由正式迁移器升级至 business11/health18；API 与 Worker 恢复 healthy，readiness 接口返回 200。真实外部模型质量、生产数据库升级及远端 CI 未验证。
