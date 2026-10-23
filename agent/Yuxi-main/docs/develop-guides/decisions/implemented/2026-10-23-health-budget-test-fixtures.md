# 健康预算合成测试准备

状态：implemented
类型：testing
Owner：backend/test/support/health_budget_e2e.py

## 问题

预算加入外呼边界后，既有合成E2E模型缺少价格及期初准备，临时插件无法让提交后的标准命令复现。部分协议替身也未跟进外呼前授权回调。

## 决策

### 实现方案

共享测试support仅在专用数据库、同槽位API及当前内部合成模型端点验证后，通过真实管理员接口登记合成价格和一次性零期初。各真实模型fixture显式调用，不改变生产预算或绕过账本。报告fixture另登记内部固定页价。协议替身执行传入的授权回调；单独图协议测试复用既有合成预算stub，预算事实仍由PG和真实Worker验收。

报告重处理夹具创建完整依赖表和真实合成模型配置，明确断言缺失用量为未知；历史Schema用例排除尚不存在菜谱表的传递外键依赖。咨询HTTP夹具保留未同意403、已同意但云关闭503、缺权限及无副作用断言；历史消息关联同一Run和请求，公开错误及进度脱敏，撤权后停止下一条SSE。指标技能版本断言与当前三个内置技能的2026.10.21.1版本一致。

## 替代方案

保留未提交插件无法重跑。自动拦截所有HTTP或禁用预算会隐藏真实边界，故不采用。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| 标准E2E无需临时插件 | 新库无期初和价格 | test fixtures | 新隔离库咨询、交接与指标E2E | 非隔离库/外部端点拒绝 | 咨询1、交接4、指标6通过 |
| 既有授权测试仍到达原断言 | 模型替身签名不匹配 | integration tests | vision executor/report reprocess/vision HTTP | 撤权与过期lease | executor37、reprocess14、vision HTTP24通过 |
| 合成价格不会写向其他环境 | 专用库或端点不符 | health_budget_e2e | test_health_budget_e2e_guard.py | flag/API/数据库/provider不符均零写入 | 4 passed |

在专用内部网络Compose中执行 `python -m pytest test/e2e/test_health_consultation_e2e.py test/e2e/test_health_handoff_e2e.py test/e2e/test_health_indicator_agents_e2e.py -q -p no:cacheprovider --tb=short`，咨询和交接5项通过；指标旧版本断言修复后，单独执行指标文件6项通过。标准夹具自行登记合成预算，无需未提交插件。

定向integration文件为 `test/integration/services/test_health_vision_executor.py`（37通过）、`test_health_report_reprocess.py`（14通过）、`test_health_vision_http.py`（23通过后，私有历史夹具修复并定向回跑1通过）。工作台及质量HTTP23项通过。预算unit/PG31项通过；完整非slow后端unit4924通过、59跳过，新增隔离guard另4项通过。各命令使用 `python -m pytest <文件> -q -p no:cacheprovider --tb=short`；完整unit使用 `python -m pytest test/unit -m 'not slow' -q -p no:cacheprovider --tb=short`，测试容器启用Langfuse测试配置并以root运行以满足沙盒投影目录权限。原始尝试失败和修复后日志均保存在本地 `agent/.tmp/github-push-20261023/`，不将早期失败报告为整套通过。

## 后果

合成价格不表示真实供应商费用上界。测试辅助不自动配置生产用途；专业与App验收范围不变。

合成回放只验证工程语义。其余已接入共享准备器的E2E文件未逐一整套运行，报告TLS/OCR端到端及生产迁移、真实供应商、App页面仍未验收。连接池和Milvus API弃用警告保留，不影响本轮断言。
