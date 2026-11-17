# 账号私有家庭记忆

状态：proposed
类型：feature
Owner：backend/package/yuxi/services/health_memory_context_service.py

## 问题

单成员记忆不能覆盖本人对家人的陈述，普通咨询及参考餐单也缺少自动提供上下文的共同入口。

## 提案

### 实现方案

账号拥有私有记忆，事实关联当前家庭中已建档的真实成员。普通咨询与参考配餐在运行前使用预算模型语义提取当前持久化用户原文，后端核对实际目录、授权、原文和租约，再将事实与请求处理收据同事务提交。每次模型调用自动读取授权档案和当前记忆，记录实际版本依赖；发布事务再次验证。记忆保存来源快照，原家庭记录仅供所有者查看和删除，停止召回。管理列表按账号分页并标注主体。

## 替代方案

只放宽句式无法解决跨成员对象错误及配餐入口缺失。合并进正式档案会混淆用户自述与确认资料；独立版本事实保留其语义。

## 验收标准

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 自然表达与实际成员 | 模型输出边界 | health_memory_context_service | test_account_family_memory.py | 不存在对象不写 | Passed |
| 账号管理和原家庭隔离 | HTTP / PG | health_memory_service | test_account_family_memory.py | 其他账号不能读删 | Passed |
| 当轮读取及版本失效 | Agent / PG | health_memory_context_service | memory unit / integration | 撤回不能发布旧结果 | Passed |
| 统一页面 | Vue | CloudMemories.vue | memory-management.test.mjs | 迟到账号响应被清空 | Passed |
| 完整执行与恢复 | Worker / 队列 / 模型 | run_worker / health_memory_context_service | 独立 Compose E2E | 恢复不重复保存、旧版本不发布 | Not run |
| 真实自然表达识别 | 模型语义 | health_memory_context_service | 真实模型验收 | 关系含糊不写、临时要求不写 | Not run |

## 风险

语义提取增加一次受预算与总执行时限约束的外呼。有限词汇无法核实的硬限制继续阻止未核实配餐。现有菜谱限制核对词汇仅覆盖牛羊肉；例如明确“不吃香菜”会保存，但餐单须等待限制核实，不会把未命中解释为安全。真实模型语义质量与完整 worker 链路需要进一步验证；测试不替代专业审核。源码已实现上述服务、迁移和页面，完整运行验收通过前记录保留为 proposed；线上部署尚未执行。
