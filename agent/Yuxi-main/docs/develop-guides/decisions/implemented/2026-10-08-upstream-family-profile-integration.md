# GitHub 家庭档案交付与本地 Agent 升级合并

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/health_agent_roles.py

## 问题

GitHub main 的 `2e40e8c` 交付家庭档案及 Yuxi 0.7.3 升级；本地 Agent 开发以 `b27dda7` 为基线，存在未提交源码与暂存记录。直接覆盖会丢失本地工作；上游移动 Skills 模块及提升 business schema 后，旧导入与运行数据库也不再兼容。

## 决策

将当前开发分支快进到该提交，先保存工作区字节、暂存补丁及包含未跟踪文件的安全 stash，再三方恢复本地修改。逐项解决九处冲突，保留本地三租约 worker 健康契约与上游其他升级；模型缓存统一 `from_provider` 工厂同时保留上游 `include_user_uid` 字段。健康服务改用上游真实 Skills service/repository 路径，测试同步真实 owner 与 provider 字段。

恢复原有暂存 blob，不将合并后的全部源码自动暂存。上游新增的根 AGENTS 从当前索引移出，保留上游指导和本地用户记录规则。用户指定 Skill、Word、Excel及备份继续仅本地维护。本轮不提交或推送。

开发库先执行完整逻辑备份，再由正式 storage-migrator 完成 business 7→10；health 15 保留。API/worker 仍只校验版本，不能在启动时修改 schema。

家庭档案 `/api/family` 使用 business `family_*` 模型，现有营养 Agent 使用 health 模型、grant、独立模型同意与安全投影。保持这两者的显式边界：家庭管理授权不替代 AI 用途同意，不自动复制疾病、目标、过敏原或成员身份。角色目录显示档案源模块已交付，同时保留 `integration_pending` 和完整档案对模型尚不可用状态。

## 替代方案

只 fetch 不整合无法满足项目拉取要求；丢弃工作区或一律选择某一侧会损失已交付的 Agent 安全边界或上游档案功能，均不采用。独立签入全部本地工作也超出本次授权。

## 后果

本次完成源码合并和开发环境恢复。后续需明确成员 ID、字段级授权、确认版本、指标来源与营养安全语义映射，再验证改版/撤回使下游旧计划及运行失效。专业规则、小程序、监护授权和生产部署不纳入本次完成范围。

本人显式成员关联、已确认档案读取及咨询来源失效由[本人档案 Agent 接入](2026-10-08-family-profile-agent-read.md)接续；该范围采用 health16 增量。完整安全编码、多人模型同意、测量来源及下游配餐失效传播继续独立验收。

## 验证

合并后相关单元分组验证模型缓存、worker/readiness、业务及健康迁移、内置发现和健康 Agent；配置测试在 Linux 中以当前 Compose/CI 文件验证真实入口和预算。家庭档案与迁移测试通过正式路由、JWT、真实 TCP HTTP 和独立 PostgreSQL schema 验证权限、历史、撤回、重放及升级重复执行。

200 项不同相关后端 unit 分组通过，63 项工程检查器 unit 通过；家庭档案 HTTP/PG 9 项及迁移 4 项通过，初始个人/家庭实际 API/worker/SSE/PG 两轮 E2E 2 项通过。上游迁移夹具原来按 `family_` 前缀排除表，会误删营养 Agent 的 `family_member` 而保留其引用表；现明确排除 `HEALTH_TABLES` 以构建旧 business baseline，迁移结果同时验证 health15。失败与被服务重启打断的批次不当作通过证据。

前端家庭数据变换测试 3 项、全量 lint 与构建通过，保留既有 chunk 体积提示。两套开发环境 ready 返回 200，API/worker 均 healthy。11 个变更 Python 文件 Ruff 检查及格式、工程契约检查通过。未执行全仓后端回归、真实模型产品质量验收或本轮浏览器交互验收。
