# 从本轮已读原谱装配参考餐单

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/reference_meal_selection_service.py

## 问题

参考配餐已读取并解析完整菜谱，仍要求模型重抄全部菜名、食材、步骤和采购原文。多菜及英文译文重复生成容易遗漏或改写，导致原文校验拒绝；放宽来源校验会使未读取或修改的资料进入餐单。

## 决策

### 实现方案

在既有保存工具增加明确选择 `use_read_recipes=true`、`auto_purchase_matches=true` 的输入。模型只选择餐次、本 Run 已打开的文件与分片、可选中文译文、估时及明确 SKU 包装数量。新 service 在当前授权 Run 内重读已完成的工具回执、完整原文和版本，以既有 parser 装配标准原文，以已读商品匹配结果装配采购对应和真实缺口。没有明确包装数量不猜测数量，未读取商品拒绝；同一食材选择多个有效规格仍拒绝。与原谱食材无关的模型附带商品不进入采购建议，见[后续决策](2026-11-07-reference-unused-purchase-selection.md)。

返回现有 `ReferencePlanDraft` 后仍调用原保存 service。原文版本、未核实章节、限制、译文、商品、库存与最终发布由既有 Owner 再次核验。缓存译文仅在来源及引句键一致并通过原译文校验时复用。新入口不接受显式原文，旧原文入口继续严格校验，不覆盖其错误输入。

## 替代方案

- 只增加提示及重试：仍要重复生成大量既有事实，无法消除抄写失败。
- 放宽逐字、同 Run 或翻译校验：不能保证真实来源，拒绝。
- 自动猜测包装数量或省略采购缺项：改变用户选择及采购事实，拒绝。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 新入口只接收明确选菜及包装数量 | 混入模型原文或默认启用 | 新 service 的 HealthDTO | `pytest test/unit/services/test_reference_meal_selection.py` | 缺少两个明确开关、原文字段、重复餐次及 SKU 拒绝 | Passed |
| 仅装配本 Run 已打开且未变的完整原文 | 跨 Run、未打开、源变化及附注失效仍通过 | 新 service 与原文 service | 同上；生产真实 Worker 三餐保存并回读 ready v1，单换晚餐 v2 且早午餐保留 | 未打开文件、变源、待核实章节拒绝 | Passed |
| 采购对应和缺口来自真实匹配 | 漏填包装数、额外 SKU、忽略食材 | 新 service 与匹配及保存 Owner | 同上及后续决策 | 缺少明确已匹配 SKU 数量、未读和同食材多规格拒绝；无关 SKU 被剔除 | Passed |
| 原保存及译文边界保留 | 新分支跳过旧校验或复用过期译文 | 原保存 service、translation service | unit；生产真实保存/回读；HTTP 当前 63 项分轮修复合并通过 | 英文无合法译文仍拒绝、错误缓存不作为有效译文 | Passed |

当前后端 5609 个单元 case 经分轮修复和逐项收据合并全部通过，运行源码一致，并非单次全量全绿。生产最终结果及测试收据保存在 `agent/.tmp/miniapp-three-meals-20261106/` 的 `live-status-latest.json`、`units-current-combined-receipt.json` 与 `http-current-combined-receipt.json`。API/Worker `94220a0ad8ee` 和正式 H5 r2 `a42f03401889` 已部署健康，App 最终 1379/1379 通过，H5/MP 正式 r2 构建通过。

上述生产结果属于基础样例。新增限制组合早餐请求未通过：保留“麸质谷物”“大豆不耐受”“牛羊肉”“少吃重油重盐”后，真实 Run 仅支持牛羊肉，其他三项为 unsupported。真实蛋、米、薯 SKU 的 `ingredients`、`allergen_codes` 为空，`data_completeness=partial` 且标记 `allergen_information_missing`。缺少真实配料、交叉接触信息、受控分类及医嘱解释，已请求补充真实原料资料；不得自动编造标签或审核状态。对应收据为同目录的 `live-restriction-diagnosis.json` 与 `live-restriction-materials.json`。

## 后果

新分支的模型输入契约已同步到工具 schema、调用及集成测试。生产基础 Worker 与每日三餐回读已有验收证据，新增限制组合尚未跑通。官方本地 CLI 已以 AppID `wx53a82377416871bc`、版本 `2026.11.06.2` 上传微信 r2，upload 与 preview 编译均 exit 0，上传信息及预览二维码已生成。微信尚未审核发布；CUA 访问公众平台被站点安全策略拒绝，未绕过。模拟器 runtime 查询 Timeout/空白；真机截图仅证明可以发送请求，该组合被限制规则挡住，没有真机全链路通过结论。ASR 当前暂用文字输入，正式营养和专业审核状态保持既有边界。
