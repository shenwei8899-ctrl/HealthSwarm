# 日常参考三餐以已核验原谱完成保存

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/reference_meal_plan_service.py

最终 API/Worker `363b0da894de` 与 H5 r7 `c0e7a1f75863` 已部署并验证健康，微信 `2026.11.06.7` 已上传，尚未审核发布或完成真机全链路。

## 问题

小程序的日常参考餐单在消息失败、原文校验失败或保存工具长期未完成时，无法读到早餐、午餐和晚餐。服务端已经解析完整原谱，但模型仍须重新逐项抄写；保存预览之后等待可选图片生成，进一步延长工具完成和每日餐单发布。线上同时包含未合入当前 Git 主干的菜谱、翻译与商城核验，修复不能覆盖这些已运行边界。

## 决策

### 实现方案

先按共同 Git 基线合并已上线源码与依赖，保留最新主干的咨询改动；运行时继续沿用同一来源、授权、采购和发布 Owner。`save_reference_meal_plan` 增加显式选取本 Run 已读取原谱的输入：模型选择来源身份和餐次，程序从真实完成回执重验当前完整原文并形成现有参考稿。旧的显式引句分支保留严格校验。当前已读商品只能按真实匹配和明确整数包装选择形成采购对应，未知成分、译文缺失与待核实章节保持失败状态。

餐单保存不等待生成式图片。已有来源图和已缓存展示可继续读取，首次无图有明确缺失状态。每日计划仍只由同一 Run 完成事务发布。小程序仅在结果真实保存并版本推进后继续补齐缺失餐次，超时、追问及服务错误必须结束骨架并提供相应操作。

### 限制未核验时的做法资料候选

明确的麸质、大豆、牛羊肉与少油少盐限制全部保留。`get_reference_plan_context` 在有限的受控限制原文集合下可附带完整的公开来源做法整理稿；模型只能选择同 Run 目录中的编号和已选餐次，服务器重新核对当前档案、来源、目录及整理稿哈希后输出 `reference_candidates` / `cooking_reference`。整理稿区别于逐字原文，哈希覆盖整理稿自身。其他过敏原或医嘱不因局部词汇命中而开放目录。

候选仍标明个人适用性未确认、原料标签及交叉接触资料缺失，没有预览 ID、个人份量、营养计算或采购。候选发布不保存餐次或推进每日版本；真实请求提交可以建立每日 `pending` 请求索引，索引保存恢复入口，不表示餐次已安排。已完成候选通过同一任务校验后投影为 `reference_candidates` 终态，重开页面或跨设备读取能结束等待并进入原对话。客户端以 Task 的 `result_type`、`validation` 和 `data` 包装读取，历史消息以服务器保存的 canonical 业务内容恢复；两者不能使用同一个虚构的扁平响应 fixture。

### 授权、记餐主体与跨日恢复

普通咨询的独立同意约定由[咨询发布回归修复](./2026-11-06-consultation-consent-release-regression.md)取代，请求、Run、模型调用、历史和目录均遵循当前成员访问权限，运行时继续核对处理方及政策版本。配餐等独立用途分别校验当前处理同意。家庭报告代建者及其旧第三方 grant 不拥有该家人的 AI 处理权；来源转交只接受本人或有效监护身份的明确用途同意，转交时撤回当前主体之外的全部旧 grant，报告读取继续遵循原家庭报告权限。聊天“我”只解析当前账号唯一且已获记餐授权的“本人”，明确家人自述仍分别校验目标成员的 AI 使用及饮食编辑授权。候选恢复核对当前家庭、日期及完整任务绑定，旧日期终态不阻止新日安排。

## 替代方案

只修改提示词不能避免多菜原文和译文的重复生成错误。直接移除来源、采购或译文守卫会让未经核对的数据进入结果。将图片生成改成无 Owner 的后台协程无法形成可恢复执行事实；本修复只移除关键路径上的等待，不新增后台执行系统。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 合法选择可保存并回读三餐原文 | 模型重抄错误或假完成 | 参考餐单服务、每日计划发布 | 生产真实 Worker 保存并回读三餐 ready v1；仅换晚餐 v2，早午餐保留；`live-status-latest.json` | 未读、跨 Run、源变化拒绝 | Passed |
| 图片不可用不阻塞餐单保存 | 可选图片等待延迟工具完成 | 参考餐单保存 | `test_reference_meal_completion.py`；不可完成图片服务与恢复旧 await 的负控 | 保持图片不可用但任务完成 | Passed |
| 原文、译文和采购边界保留 | 缺失被当作有效 | 选菜装配、原有保存校验 | selection/completion 58 项；当前真实 HTTP 63 项经分轮修复合并全部通过 | 非法 SKU、错误译文、待核实章节拒绝 | Passed |
| 今日餐单结束加载并补缺餐 | 单餐 ready 被当成全日完成、合法慢任务提前报错 | App 今日餐单状态机 | App 全量 Node 1379/1379；目标 64/64；正式 H5/MP r2 构建通过 | 仅早餐、needs_input、150 次上限、跨设备终态及关闭迟到结果 | Passed |

当前后端 5609 个单元 case 有逐项通过证据，来自分轮修复后的收据合并，并非单次全量全绿；合并已核对运行源码一致。真实 HTTP 63 项来自同一运行源码的 60 项通过结果及修复后 3 项通过结果。收据保存在 `agent/.tmp/miniapp-three-meals-20261106/` 的 `units-current-combined-receipt.json`、`http-current-combined-receipt.json` 和 `live-status-latest.json`。

API/Worker 镜像 `94220a0ad8ee` 与 H5 r2 `a42f03401889` 已部署并通过健康检查；生产基础文字咨询、三餐保存和单换晚餐已有通过证据。部署收据为同目录的 `rollout-executor-receipt.json` 和 `h5-deploy-receipt.json`。基础文字咨询的来源与输出指针绑定同一 Run，未使用来源核验 fallback；这些证据不覆盖随后新增的限制组合早餐场景。

限制组合的已安排早餐请求未通过：确认保留“麸质谷物”“大豆不耐受”“牛羊肉”“少吃重油重盐”，原有保存核验只支持牛羊肉，另外三项保持未核验。蛋、米、薯 SKU 的配料与过敏原编码为空，完整性为 partial 并标记 `allergen_information_missing`。缺少真实配料、交叉接触信息、受控分类及医嘱解释，不能以伪造标签或审核状态放行。证据为同目录的 `live-restriction-diagnosis.json` 和 `live-restriction-materials.json`。新增做法资料候选不提升这些保存条件，也不宣称该请求已成为个人适用餐单。

候选首轮 App r3 的 1404 项 unit 虽通过，但实际 Task 包装和 canonical 历史协议与 fixture 不一致，独立 Review 发现后，用真实协议复现了 28 个失败；r3 未部署或上传。修正协议、跨设备候选终态及来源详情展示后的 r6 全量 1429 项通过，独立 Review 无剩余阻断项，正式 H5/微信构建通过。后端相关 Linux 单元集 604 项通过；真实 HTTP 76 个独立 case 有通过证据，来自首轮 75 项及修正活动 Run 测试夹具后 3 项负控的合并收据，并非单次全绿。发布的 10 个运行文件与该 HTTP 快照逐项哈希一致。

API/Worker 候选镜像 `9d0392dd9d14` 与 H5 r6 `413762b20f64` 已部署。启动时负载超过 4 核门槛，发布执行器在容器更新后停止；随后仅做只读复核，负载回落至 3.962、资源门槛通过，API/Worker 健康、191 层镜像与候选环境/挂载一致，没有重试更新。H5 校验全部 181 个网关文件及 5 个公开资源。真实普通账号通过正式入口保存全部四项限制，再经真实 Worker 完成明天早餐与三餐候选；两个结果均回读完整整理稿，来源属于同 Run 已完成上下文，未保存预览、餐次或采购，仅有版本 0 的请求索引。客户端任务流、候选校验器与历史函数直接消费两份实际 HTTP 响应均通过，无额外 POST 或轮询；该验证使用合成传输，不能替代真机交互。验证账号已软删除并撤销凭据，保留审计。

当前部署与 Worker 收据位于 `agent/.tmp/restricted-cooking-candidates-20261106/`：`post-startup-verification.json`、`http-current-combined-receipt.json`、`live-status-latest.json`、两个 `*-client-wire-verification.json` 及 `live-cleanup-latest.json`。H5 收据位于相邻 `restricted-cooking-candidates-h5-r6-20261106/`。这些候选证据不改变未核验限制、标签缺项和个人适用性状态。

提交前独立复核修复上述四类边界后，Linux 定向集分 17 个文件运行，638/638 通过，无跳过、无 OOM；App r7 全量 1436/1436 通过，正式 H5、mp-weixin 构建成功。反事实验证把新增测试用于旧运行源码：9 项同意定向用例有 8 项按预期失败、1 项正控通过；真实 PostgreSQL 报告归属 4 项有 3 项按预期失败、1 项正控通过；第一人称记餐 7 项有 6 项按预期失败、1 项正控通过。收据为 `agent/.tmp/miniapp-three-meals-20261106/` 下的 `targeted-gitFinalU1-result.json`、`targeted-gitGuardBASE-result.json`、`http-gitOwnerBASE-result.json` 与 `targeted-gitSubjectBASE-result.json`。

最终非 slow 全量按 36 组实际执行 5677 项，5676 项通过，唯一失败是 Skill 版本 `2026.11.06.1` 的旧测试预期；显式修正至当前版本 `2026.11.06.2` 后，整个文件 13/13 通过。逐项合并覆盖当前 5677 项，保留原失败，不能称为单次全量全绿。全量、补跑及当前 516 个运行文件哈希一致，629 个测试文件仅该版本断言一行不同；证据为 `agent/.tmp/git-final-verification-20261106/units-git-full-current-combined-receipt.json`。真实 HTTP 76 项与独立 PostgreSQL 批次 35 项共 111 项通过，无跳过、无 OOM；后者覆盖报告归属、咨询历史与目录撤回、预算事实及预算不替代处理同意。收据为前述验证目录中的 `http-gitFinalH2-result.json` 与 `http-gitFinalPG3-result.json`。

最终 API/Worker 镜像 `363b0da894de` 已部署且健康，readiness 通过；H5 r7 `c0e7a1f75863` 已部署并核验 181 个网关文件和 5 个公开资源。部署收据分别为 `agent/.tmp/final-consent-owner-repair-20261106/rollout-executor-receipt.json` 与 `agent/.tmp/restricted-cooking-candidates-h5-r7-20261106/h5-deploy-receipt.json`。

最终版本以新建合成账号完成早餐与三餐两次真实 Worker 验收，均单 attempt、无数据库错误：早餐是一道水煮全熟蛋，三餐含早、午、晚共四道完整来源整理稿。全部四项限制保留，canonical 内容与同一 Run 已完成的 `get_reference_plan_context` 一致；资料仍为 unresolved，采购 disabled，无预览，每日读模型为 absent、版本 0，`pending.status=reference_candidates` 绑定同一三餐终态请求，无已安排餐次或采购。早餐活跃期间的初次三餐提交被 423 计划锁拒绝；早餐终态后再提交成功，拒绝日志保留。

两份实际公开 HTTP Task 响应直接通过当前 App 任务流、校验器和历史函数，无新 POST、未调度轮询、无保存餐单或采购声称；使用合成传输，`real_browser_or_device_execution=false`。最终证据位于 `agent/.tmp/final-consent-owner-repair-20261106/` 的 `live-status-latest.json`、两个 `*-client-wire-verification.json` 与 `live-cleanup-latest.json`；验证账号已软删除、凭据撤销、审计保留。最终源码绑定收据 `agent/.tmp/git-final-verification-20261106/final-source-deployment-binding.json` 核对当前 288 个 App 构建源文件与 r7 一致，五个后端增量文件的 LF 哈希与已部署 `363b` 冻结记录一致。

## 后果

普通烹饪参考继续保持未作专业审核及营养未计算状态。微信 r6 已由官方本地 CLI 以 AppID `wx53a82377416871bc`、版本 `2026.11.06.6` 上传成功，upload 和 preview 编译均 exit 0，预览码已生成。尚未审核发布；CUA 访问微信公众平台被站点安全策略拒绝，未绕过；先前模拟器 runtime 查询 Timeout/空白，没有 r6 真机全链路通过结论。网页新版入口加载已实际观察；正式客户端没有新增登录旁路。ASR 当前暂用文字输入。个人餐单保存仍依赖真实原料、过敏原及交叉接触资料和医嘱核验，公开做法整理稿不会替代这些事实。

微信 r7 已通过官方 CLI 以版本 `2026.11.06.7` 上传并生成预览码，upload、preview 均 exit 0；收据为 `agent/.tmp/git-final-verification-20261106/wechat-r7-update-receipt.json`。审核发布与 r7 真机全链路仍未验证，原料标签及个人适用性缺口保持不变。
