# 今日餐单与聊天恢复（2026-11-06）

状态：implemented；API/Worker 镜像 `363b0da894de` 与 H5 r7 `c0e7a1f75863` 已部署且健康，微信开发版 `2026.11.06.7` 已上传，尚未审核发布。最终版本在保留四项限制时，真实 Worker 的早餐与三餐做法候选、客户端实际响应解码均通过；候选没有形成已安排餐次或采购。个人适用性与真机全链路仍未确认。

本次沿用已经拉取的主分支与现有日常参考餐单链路。用户截图中的消息失败、餐单读取失败和持续骨架需要分别核对；不能把失败改成假成功，也不以未审核资料替代正式营养方案。

App 侧已定位：任务提交后迅速返回 `needs_input`，而今日餐单读模型尚未出现 pending 时，现有轮询会把真实追问丢成普通错误；任务状态的错误或配置原因也被统一提示覆盖。读模型和任务的短暂延迟应由有限读取解决，不能重复提交生成。

已修改：保留任务的真实问题、成员、线程和请求，展示继续回答入口；已接受任务的确定失败立即结束骨架。临时轮询失败沿用有限重试，继续使用原任务。成功只消费服务端保存且来源可核对的日餐单，不在客户端拼造菜品或营养值。

另定位并修复：只保存早餐也会返回 `ready`，原实现将其误认为三餐齐全。现按已保存餐次计算缺失餐次，只补午晚餐并保留早餐；需要更新的原就餐成员不变，不同成员组依次安排。下一组必须等上一组在日餐单中实际保存且版本推进，任务完成信号本身不能触发同组重复 POST。只读刷新只读取，不生成。

验收：实际组件逻辑与状态机覆盖三餐成功读取、提交后追问、临时失败恢复、超时后原任务刷新、切换账号及隐藏页面迟到结果；相关测试、正式 H5/微信构建和生产基础 Worker 链路已有通过证据。微信上传及 preview 编译成功；审核发布、真机全链路及录音交互尚未验证，新增限制组合早餐场景仍被资料及规则边界阻断。

本地结果：新增边界先复现 5 项失败，修复后相关 173 项全部通过，包括直接执行 `TodayMealPlanSheet.vue` 脚本与真实餐单状态机，读取三餐、打开午餐详情、追问继续和超时刷新。H5、mp-weixin 构建均通过，输出分别位于 `App/output/meal-chat-recovery-20261106/h5` 和 `mp-weixin`，未覆盖现有 dist 或开发者工具包。

全量 `npm test` 首次实跑 1373 项，1281 通过、92 失败。随后用 `git archive HEAD`（`78a79ec151c252f58198cadec910c0422023532b`）隔离原版 App，复现 1362 项中同样的 92 个失败，按文件和测试名逐项相同，餐单补丁没有引入新的全量失败。

已修复测试夹具：两个组件脚本夹具补 `defineOptions` 宏；成员资料测试读取实际 `sendBlocked` 计算式并增加提交中/图片错误等断言；商城路由校验包含真实子包且核对物理页面存在。四文件 174 项通过。

主任务从生产恢复真实后端 `recipe_covers.json` 后，确认其 5 条记录与客户端深相等；生成检查的剩余失败仅为 Windows CRLF 与生成器 LF。经授权修复 `sync-recipe-covers.mjs` 的检查换行规范，继续严格核对完整生成内容，保留业务对象深相等断言。该轮全量 1373 项通过；加入慢任务等待边界后，最终 `npm test` **1379/1379 通过**，无跳过、无取消。

前期日志保留在 `App/output/meal-chat-recovery-20261106/`；独立基线、逐项比较在 `agent/.tmp/meal-chat-baseline-20261106/`（`final-comparison.json`：92 项基线失败全部消除，新增失败 0）。最终 App 测试日志及构建记录位于 `App/output/three-meals-formal-20261106-r2/npm-test.log` 和 `build-record.json`。

生产真实三餐任务耗时超过原 90 秒轮询预算，因此前台默认改为 150 次、间隔 2 秒；45 次后使用现有 label 显示“三餐仍在生成，请稍候”。到上限结束骨架并保留原任务刷新入口；同一请求的明确失败或追问立即结束等待，其他设备已接受的新任务不受旧任务终态影响。新增默认预算、失败/追问、跨设备及关闭后迟到结果负控，目标测试 64/64 通过，全程不重复生成 POST。

正式 H5、mp-weixin r2 构建均成功，正式 API/商城域名、微信 AppID 与 H5 `/family-app/` 路径已核验。API/Worker 镜像 `94220a0ad8ee` 与 H5 r2 `a42f03401889` 已部署且健康；H5 网关逐文件核对 181 项并验证公开入口及资源。

生产基础 Worker 验收：文字咨询完成，正文来源和输出指针绑定同一 Run，未使用来源核验 fallback；三餐生成、保存并回读 `ready` v1；随后仅更换晚餐得到 v2，早餐和午餐原样保留。该基础样例的最终回读收据为 `agent/.tmp/miniapp-three-meals-20261106/live-status-latest.json`，不能以提交时仍在运行的单项 `live-*-latest.json` 代替最终结果，也不覆盖随后新增的限制组合。

后端当前 5609 个单元 case 经分轮修复及逐项收据合并全部通过，运行源码一致；这不是一次完整运行全部通过。真实 HTTP 当前 63 个 case 由同一运行源码的 60 项通过结果及修复后 3 项通过结果合并覆盖。对应证据为同目录的 `units-current-combined-receipt.json`、`http-current-combined-receipt.json`、`rollout-executor-receipt.json` 与 `h5-deploy-receipt.json`。

微信交付：已登录的官方本地 CLI 以 AppID `wx53a82377416871bc`、版本 `2026.11.06.2` 上传 r2，upload exit 0，`wechat-upload-info.json` 已生成；preview 编译 exit 0，预览二维码为同收据目录的 `wechat-r2-preview.jpg`。尚未正式审核发布，CUA 访问微信公众平台被站点安全策略拒绝，未绕过。模拟器 runtime 查询出现 Timeout/空白，不能作为通过证据。

新增受限场景：真机截图证明可以发送“明天早餐”问题，但该请求被限制规则挡住。确认保留的限制项为“麸质谷物”“大豆不耐受”“牛羊肉”“少吃重油重盐”；真实 Run 核对仅支持牛羊肉，其余三项为 unsupported。真实蛋、米、薯 SKU 的 `ingredients`、`allergen_codes` 为空，`data_completeness=partial` 且标记 `allergen_information_missing`。缺少真实配料、交叉接触信息以及受控分类和医嘱解释，该组合场景尚未跑通；不能自动编造标签或审核状态，已请求补充真实原料资料。证据为 `live-restriction-diagnosis.json` 与 `live-restriction-materials.json`。

受限做法候选：Task 读取严格消费 `result_type`、`validation`、`data` 包装，历史消息消费 canonical 业务内容；保留成员、日期、餐次、限制和来源，禁止将候选解释为已保存日餐单或可采购结果。其他设备或先前请求的候选终态也结束骨架，保留原请求入口和已有餐次，不重复提交或进入下一成员组。完整做法默认可读，技术来源说明由用户主动展开。

候选协议修复前，r3 的扁平 fixture 掩盖真实 Task 包装错配；真实协议复现 28 项失败，外部候选终态负控也复现失败，均已保留记录。最终 r6 全量 1429/1429 通过，独立 Reviewer 确认无阻断，正式双端构建冻结源码一致。真实受限账号完成早餐与三餐候选，客户端真实函数对两份服务器 HTTP 响应及历史内容解码通过，没有额外 POST、计划或采购声称。API/Worker 启动负载门槛触发后以只读检查确认资源回落和服务健康，没有重复更新。H5 r6 全部 181 个网关文件与 5 个公开资源校验通过；微信 upload、preview 均成功。验证账号已软删除、凭据已撤销。证据位于 `agent/.tmp/restricted-cooking-candidates-20261106/`，最终构建记录与全量测试日志位于 `App/output/three-meals-formal-20261106-r6/`。

未完成范围：个人适用餐单与采购仍缺实际原料标签、配料及交叉接触核验；微信审核发布和 r6 真机交互尚未验证。客户端函数验证使用合成传输承接真实响应，不能冒充真机执行。ASR 当前暂用文字输入。

提交前独立复核补齐四条边界：咨询用途同意撤回后，提交、运行、模型调用、历史与目录均拒绝访问；代建报告及其旧 grant 不授予家人 AI 处理权；聊天“我”只对应当前账号唯一且已获授权的“本人”；候选恢复核对当前家庭与日期，旧日候选终态不阻止新日请求。报告来源转交要求本人或有效监护身份及明确用途同意，转交时撤回当前主体之外的全部旧 grant；原有报告读取继续受家庭报告权限控制。

修复后的 Linux 定向集分 17 个文件运行，638/638 通过，无跳过、无 OOM；App r7 全量 1436/1436 通过。旧运行源码上的反事实验证中，9 项新增同意定向用例有 8 项按预期失败、1 项正控通过；真实 PostgreSQL 报告归属 4 项中有 3 项按预期失败、1 项正控通过；第一人称记餐 7 项中有 6 项按预期失败、1 项正控通过。收据为 `agent/.tmp/miniapp-three-meals-20261106/` 下的 `targeted-gitFinalU1-result.json`、`targeted-gitGuardBASE-result.json`、`http-gitOwnerBASE-result.json` 与 `targeted-gitSubjectBASE-result.json`。

最终后端非 slow 全量按 36 组实际执行 5677 项，5676 项通过，唯一失败为 Skill 版本 `2026.11.06.1` 的旧测试预期；显式更新至当前版本 `2026.11.06.2` 后，整个文件 13/13 通过。逐项合并覆盖当前 5677 项，原失败保留，不宣称单次全量全绿。全量、补跑及当前 516 个运行文件哈希一致，629 个测试文件仅该版本断言一行不同。真实 HTTP 76 项与独立 PostgreSQL 批次 35 项共 111 项通过，均无跳过、无 OOM；收据为 `units-git-full-current-combined-receipt.json`、`http-gitFinalH2-result.json` 与 `http-gitFinalPG3-result.json`，分别保存在 `agent/.tmp/git-final-verification-20261106/` 和前述验证目录。

r7 正式 H5、mp-weixin 构建完成，微信官方 CLI 以版本 `2026.11.06.7` upload 和 preview 均成功。最终 API/Worker `363b0da894de` 已部署并通过健康检查，H5 r7 `c0e7a1f75863` 已部署，181 个网关文件及 5 个公开资源核验通过。收据为 `agent/.tmp/final-consent-owner-repair-20261106/rollout-executor-receipt.json`、`agent/.tmp/restricted-cooking-candidates-h5-r7-20261106/h5-deploy-receipt.json` 和 `agent/.tmp/git-final-verification-20261106/wechat-r7-update-receipt.json`。

最终部署的生产验收使用新建合成账号：早餐与三餐两次真实 Worker 均单 attempt 完成，无数据库错误。早餐返回一道水煮全熟蛋，三餐包含早、午、晚共四道完整来源整理稿；四项限制全部保留，canonical 内容与同一 Run 已完成的 `get_reference_plan_context` 一致。原料资料仍为 unresolved，采购 disabled、无预览；每日读模型为 absent、版本 0，`pending.status=reference_candidates` 绑定同一三餐终态请求，没有已安排餐次或采购。初次三餐提交发生在早餐活跃期间，被 423 计划锁拒绝；确认早餐终态后再提交成功，原拒绝日志保留。

两份真实公开 HTTP Task 响应均直接通过当前 App 的任务流、校验器与历史函数，无新 POST、未调度轮询，也未声称保存餐单或采购；传输为合成实现，`real_browser_or_device_execution=false`。最终 Worker、客户端和清理收据位于 `agent/.tmp/final-consent-owner-repair-20261106/` 的 `live-status-latest.json`、两个 `*-client-wire-verification.json` 与 `live-cleanup-latest.json`。验证账号已软删除、凭据已撤销、审计保留。最终源码绑定收据 `agent/.tmp/git-final-verification-20261106/final-source-deployment-binding.json` 确认当前 288 个 App 构建源文件与 r7 一致、五个后端增量文件的 LF 哈希与已部署 `363b` 冻结记录一致。微信审核发布、r7 真机全链路、实际原料标签及个人适用性仍未完成。
