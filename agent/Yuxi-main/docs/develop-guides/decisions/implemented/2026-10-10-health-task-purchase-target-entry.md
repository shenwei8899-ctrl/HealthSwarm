# 健康任务采购需求与个人目标选择

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_task_service.py

## 问题

首版Task入口覆盖四个角色的现有模式。采购助手的独立采用、库存和purchase用途，以及普通分析的可选批准目标来源，需要沿同一Task协议创建和查询；这些选择和权威回执必须由既有业务Owner验证，不能让模型提交身体数值、推算目标或声称交易就绪。

## 决策

### 实现方案

增加`purchase_requirements`任务类型，严格复用`PurchaseSelection`与`PurchaseInput`，通过现有`create_consultation`固定`PURCHASE_SLUG`和采购选择。缺选择不创建项目、线程或Request，齐全后仍由客户端明确提交既有消息入口。现有业务Owner负责有效采用、全员授权、独立purchase处理同意、版本和幂等。

查询只读取该Request对应Run的权威最终Message，并复用无需lease的`validate_purchase_publication`。结果用`ingredient_requirements`分类包装Owner完整回执；缺库存时保留回执内部的`needs_input`和`missing_fields`，未知净量保持null。模型追问独立返回`needs_input`，不替换已存在回执。商城SKU、商品库存/价格/配送、购物车、订单支付退款仍为外部待定，需求计算不意味着可采购或下单。

普通`diet_analysis`入口独立继承`TargetAwareAnalystInput`，只接受可选`PersonalTargetSelection`。所选规则和档案版本传现有创建Owner，现有分析publication validator复核当前授权与目标完整投影；其它任务类型拒绝混入目标，保留无绑定兼容路径。正常结果保留`current_personal_targets`独立字段，原通用目标不被替换，未应用的目标不声称达标。追问沿既有Task `needs_input`结构返回问题，Owner仍重验目标绑定和当前来源。Task不新增目标计算、不增加表或执行状态机，不修改专业规则Owner。

## 替代方案

- 模型自行选择采用或库存：扩大数据和用途范围，拒绝。
- Task复制采购/目标计算和数据库查询：形成第二结果Owner，拒绝。
- 将需求计算包装成可下单方案：商城契约尚未交付，拒绝。

## 后果

个人目标使用已迁移的Schema23及既有Owner；Task不拥有目标规则、授权或营养计算。采购未知库存时仍为计算结果内部的`needs_input`，需求量不能解释成净采购量，`purchase_available`和`order_available`保持false。客户端继续显式提交既有Request，并使用既有SSE和只读查询恢复结果。正式小程序页面、专业资料完整性、真实供应商模型效果、商城SKU、商品价格配送及交易仍为外部待定。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 采购和目标字段仅在相应入口接受 | 混模式、模型营养/库存输入、假任务 | Task DTO/现有创建Owner | test_health_task_projection.py | 目标混入其它模式、身体值及版本强转 | Passed |
| 采购只公开当前同Run权威回执 | 旧采用、邻Run、伪SKU/交易批准、撤同意 | purchase publication Owner | test_health_task_e2e.py中的个人/家庭采购实际HTTP→Worker→PG | 相邻回执、篡改最终结果、撤独立同意、采用失效 | Passed |
| 目标选择沿当前批准来源 | 身体数值混入、规则/档案失效、无目标退化 | personal target/analyst Owner | test_health_task_http.py、test_health_task_e2e.py中的目标入口与结果案例 | 规则revoked_at变化、删目标binding、无目标兼容 | Passed |
| 全部验收事实准确清理 | 残留账号、线程、Request、Run、Message/attempt、回执 | 既有health fixture/Task读回断言 | 每case准确UID与关联ID清理后24张表零行及最终50张健康表回读 | active lease和cleanup pending全0，配置/provider hash恢复 | Passed |

2026-10-10在`health-diet-analysis-e2e-api-1`执行专属Task单测56项，通过，37.23秒；真实HTTP/PG4项通过，34.84秒。Worker首轮10项通过，目标负控测试使用不存在的`status`字段而失败；仅将测试更正为真实`revoked_at`后，定向目标案例1项通过，46.58秒。合计11个唯一Worker案例通过，无skip，生产服务源码没有为该复验更改。首版32项unit、3项HTTP/PG、8项Worker的原始证据保留，见[首版决定](2026-10-10-health-task-projection.md)。

实际命令使用`docker exec health-diet-analysis-e2e-api-1 uv run --no-sync --group test pytest`，分别运行`test/unit/services/test_health_task_projection.py`、`test/integration/services/test_health_task_http.py`和`test/e2e/test_health_task_e2e.py`，Worker显式使用`-m e2e`；目标定向命令选择`::test_target_analyst_task_keeps_current_targets_separate_and_invalidates_history`。全部使用`-q --tb=short --show-capture=no -o cache_dir=/app/test/.tmp/health-task-projection/pytest-cache`。

每次运行核对同Request、Run、Worker attempt和权威最终Message，共31条实际Worker Run证据，22条completed、9条failed；其中包含目标定向复验。每case沿既有Owner清理后读取准确UID、Conversation与Run关联数据，共16轮、15个唯一案例，每轮24张表计数均为0。最终50张健康表、Request/Run/attempt/Message、合成账号/项目/线程、运行租约及待清理状态全为0；健康配置及24个provider完整行hash恢复。7个自有回放进程按准确PID停止，8766、8768、8769、8771、8772、8773、8775及fixture拥有的8776端口均关闭；API ready200、Worker healthy。
