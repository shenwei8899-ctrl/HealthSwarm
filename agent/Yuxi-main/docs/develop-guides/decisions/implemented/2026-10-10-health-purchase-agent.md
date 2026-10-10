# 有效采用餐单的受控采购需求 Agent

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_purchase_service.py

## 问题

已正式采用的个人及家庭餐单缺少可独立查询、解释的净食材需求。模型不能决定库存、换算商品毛重、编造 SKU 或交易事实；未确认库存和失效餐单不能成为可用采购候选。采购是独立模型处理用途，配餐同意不能批准它。

## 决策

### 实现方案

复用 Yuxi Request、独立 ARQ worker、PG checkpoint、健康私有会话和模型/工具审计，新增固定采购 backend/preset/Skill 与两项受控工具。用户通过业务入口明确选择当前有效采用、采用和餐单版本、同食品版本同烹饪状态的可食克数库存及库存确认标记，服务器原子保存不可变采购选择。模型仅接收服务端食材需求最小投影；工具由当前 Run 写入 PG 回执，最终只接受本 Run preview_id 或补充问题，发布事务重验全部来源。

采购用独立 purchase 模型配置、处理指纹和各参与者用途同意；主服务保持采购处理关闭，本地 replay 通过正常配置接口批准合成处理方。全部参与者授权、同意与采用来源在接入、模型前、工具、checkpoint/历史读取及最终 Message 发布边界复核。按 food_id 及 cooking_state 汇总配方可食克数，明确确认的同状态库存扣减至零；未知量不补零。候选明确表示商品毛重、SKU、价格、配送和交易待定。

库存确认覆盖当前采用的全部食材需求：未确认时库存与净需求保持未知；确认后未列出的食材库存为零，空集合明确表示全部没有库存。库存项只接受同食品版本和烹饪状态的可食克数。固定图沿用有限40节点预算，包含授权、计量及结果投影节点，使受控工具重复调用仍能结束；ARQ执行期限沿用既有运行底座。

HTTP 与版本化契约由 health router/types 拥有；业务重验和需求计算由 purchase service/repository 拥有；不可变选择及同 Run 回执由 health schema 拥有，迁移由 storage-migrator 执行。普通只读需求 API 复用同一业务服务，不强迫用户运行模型。

## 替代方案

只加角色状态或让模型自由输出清单无法证明当前来源与库存。直接复用配餐用途审批扩大已获同意范围。建设商城或另加计费/监控平台超出已确定接口与资料；本方案先闭合可食需求，保留明确外部缺口。

## 后果

共享注册、health domain schema 和健康会话生命周期需要协调并行编辑。真实采购模型审批、专业生产来源、SKU/包装/毛重换算/价格/交易接口与会计费用仍待定。合成 replay 仅证明实际装配、隐私和确定性协议，不证明生产模型质量或真实交易可用。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| 有效采用与明确库存形成独立可复算净需求 | 家庭重复累计、未知当零、错状态扣减 | purchase calculation/service | 独立 Decimal oracle unit、真实 HTTP/PG | 未确认库存、跨状态、缺量、重复食品、超量库存 | 21 unit passed；HTTP个人300−40=260g、家庭360−40=320g |
| 全成员独立采购用途、采用/餐单/来源版本必经 | 单成员授权扩张、配餐同意复用、旧来源复活 | purchase binding/health consent | 真实 HTTP/PG与迟到响应 Worker | 管理员无 grant、相同处理方meal_plan同意、缺一人同意、第二成员撤权、撤销采用、专业源新版本 | HTTP2与E2E6的合并8项验收通过 |
| shipping Run 的工具回执拥有最终结果 | 模型字段伪造、跨 Run receipt、重复工具创建新事实 | backend/register/worker/publication | 实际 Request、ARQ、manifest、attempt、PG receipt与权威Message回读 | 同线程checkpoint重用、同Run重复调用、假回执、前Run回执、伪造净量 | 正常/重复/问题3个Run completed；非法/伪造/跨Run3个Run failed且无权威Message；4种迟到来源变化均failed且无Message |
| schema 演进与已有健康链兼容 | 冷启动缺表、升级丢绑定、重复 DDL | storage-migrator | 真实 PG health21→22正式 main连续两次，旧绑定/时间与新选择保留、目录约束；既有safe20升级与未来版本拒绝 | 旧事实保留、JSONB、主外键、每Run唯一回执、health23拒绝 | 3项真实独立PG schema passed |

2026-10-10已执行的最小单元包为采购21项及营养师角色/Skill13项，合计34 passed。独立PG迁移与既有安全改版升级回归合计3项通过。真实隔离HTTP/Worker首轮6 passed、2 failed；失败原因是负控测试未配置meal_plan用途，以及采购重复调用达到20图节点上限。独立审批负控fixture和采购40节点预算修正后，仅两项失败用例复测为2 passed；上述8项结果由这两次实际执行合并。

清理只读回查54个具有账号归属字段的表为零、采购回执和合成providers为零、7个模型用途关闭、政策及采购审批为空、API ready200、8776回放进程停止。全局配置行保留管理员审计标记，其关闭的配置值已回读。命令及隔离前置条件由[测试规范](../../testing-guidelines.md#有效采用餐单采购验证)维护。

