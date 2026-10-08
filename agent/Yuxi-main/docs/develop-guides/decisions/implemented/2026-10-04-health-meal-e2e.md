# 饮食识图独立 worker 闭环验收

状态：implemented
类型：testing
Owner：backend/test/e2e/test_health_meal_e2e.py

## 问题

饮食流程需要证明实际上传的私有处理图片经过独立 worker 调用视觉协议，再生成未确认草稿；用户纠错、版本变化、营养计算和确认应形成同一成员的可回读日记。现有局部计算和执行器测试不证明这条发布链路。本文面向接口开发者和 Reviewer，只验收确定性数据流，不声明真实模型识别质量或商业食品授权已经通过。

## 决策

饮食测试复用健康咨询的独立合成 Compose 槽位、专用数据库和禁止外联的网络。视觉协议重放只接受固定版本模型、指定纯色 PNG 合成图片和无工具请求，并拒绝快照不支持的 `response_format` 参数；提示词要求 JSON 输出，调用层严格解析和校验，版本取舍由[固定快照请求决定](./2026-10-05-health-meal-snapshot-json.md)说明。正式管理 API 配置本地模型和合成用途审批；测试经 shipping HTTP、Durable Task 与独立 ARQ worker 完成。外部响应不提供克数或营养，最终数据来自用户纠错和人工定义的食品及计算 oracle。合成服务与原开发槽位的配置、凭据和数据隔离。

## 替代方案

进程内 patch 视觉函数只能证明局部执行器行为。临时启用原开发槽位会改变未获批准的外发配置。真实供应商及称重照片用于另行批准的质量校准，不能替代无费用的 assembled-path 回归。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 多视角通过独立 worker 成为同餐未确认草稿 | 不执行视觉协议或重复计食 | vision service / task worker / private objects | 实际 HTTP、Task lease 终态、VisionJob / Draft、图片协议及结果对象回读 | 未同意时零任务和零协议调用；非合成图片或额外工具拒绝 | Passed |
| 营养由纠错后的版本化数据计算 | 模型补造份量或旧预览仍有效 | nutrition service / calculation snapshot | 人工食品常量和手算 oracle，改量后再次计算 | 未纠错不计算完整营养，旧 calculation 确认拒绝 | Passed |
| 确认一次生成当前成员日记 | 确认幂等失效或跨成员读取 | confirmation / diet repository | 并发同请求确认、正式日记及 PG 快照回读 | 陌生账号及管理员无健康授权不得读 | Passed |
| 验收不启用现有云环境 | 共用凭据、数据或外部网络 | isolated Compose / fixture | 实际数据库、空审批前置检查；原槽位相关回归 | 普通槽位在 fixture 前跳过 | Passed |
| 失败保留未收敛任务证据 | 活动 worker 数据被测试清理删除 | health HTTP fixture / meal fixture | 未收敛清理拒绝后 PG、私有预览回读；审批撤销 unit | running、残留 owner / lease 的真实 PG 负控及 pending unit | Passed |

2026-10-04 专用槽位联合执行两条 E2E、两套协议 unit、模型缓存和健康逻辑 unit、真实 HTTP integration：101 passed，59.42 秒。原槽位相关回归：96 passed、1 skipped，51.19 秒；skip 是合成 E2E 的隔离前置条件，不计为产品通过。命令由[测试规范](../../testing-guidelines.md#饮食识图与咨询联合合成-e2e)维护。食品 oracle 固定每 100 克能量 130 千卡、蛋白质 2.6 克、脂肪 0.3 克、碳水 28 克、钠 2 毫克；240 克乘个人比例 0.25 的期望为 78.00、1.56、0.18、16.80、1.20，独立定义并按业务两位小数精度核对。

## 后果

固定合成图片与响应不代表真实菜品召回、营养准确性、份量估测或医学适用性。食品数据、临床审核、供应商留存合同及费用预算仍需负责人批准；这些缺口不能用本地测试通过替代。失败时仅取消并等待本轮所属任务收敛，清理入口读取 PG Task 终态、owner 和 lease；未收敛则保留整轮诊断数据，合成审批仍关闭。专用槽位停止后保留卷。连续识图和咨询使用的审批视图刷新由[独立决策](./2026-10-04-health-provider-cache-refresh.md)说明。
