# 商城目录动态配餐与低延迟读取

状态：proposed
类型：feature
Owner：backend/package/yuxi/services/daily_commerce_service.py

## 问题

当前 Agent 在配餐时可能重复拉取商城全量目录，食材识别仍依赖有限的硬编码名称，菜谱排名没有统一排除近期结果；菜品图片若进入同步请求又会显著拖慢文字和卡片返回。因此商城已上架商品增加后，Agent 不能同时满足“尽快感知、匹配完整、响应快速、换菜不重复”。

## 提案

### 实现方案

商城继续拥有商品、规格、库存、真实配料和营养说明。商城增加只读目录版本摘要，并在现有目录商品的结构化食材映射中返回已维护别名。Agent 每隔短周期探测版本；版本未变复用本进程完整快照，版本变化由单个刷新协程重新分页读取，分类查询在快照内过滤。

配餐匹配以商城返回的结构化食材编码、名称和别名为准，旧硬编码仅用于兼容已经存在的历史数据，不从商品详情自由推断。菜谱排名接受来源 ID 排除集，同一用户、家庭、日期和餐次的换菜流程优先排除当前及近期菜谱。

菜品图片在餐单事实提交后交给既有持久任务生成并缓存。文字、营养说明与菜品卡片不等待图片提供商；图片失败可重试，但不能回滚或阻塞已保存餐单。

## 替代方案

每次请求全量读取商城能保证新鲜度，但商品增加后延迟和商城压力不可控。固定周期离线导入知识库响应快，但会形成第二份商品事实并延迟上下架。继续扩大硬编码食材表不能随商城导入动态更新。同步生成图片会把外部图片服务延迟和故障传递给用户请求。

## 后果

Agent 进程增加版本化快照和并发刷新控制；商城增加一个轻量只读端点和食材别名字段。商品发布或下架后，在版本探测周期内被 Agent 感知。匹配结果仍受真实结构化食材资料完整度约束；无明确映射的商品不会被猜测为某个食材。

## 风险

多 Agent 实例各自维护内存快照，会在短探测周期内存在秒级版本差异。图片任务依赖持久 Worker 与图片供应商配置。目录版本未在所有商品变更路径触发时会导致缓存未刷新，需用发布/下架回归测试覆盖触发点。

## 验收标准

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 目录版本不变时仅探测版本并复用快照 | Agent 反复全量分页读取商城 | `backend/package/yuxi/services/daily_commerce_service.py` | `python -m unittest backend.tests.unit.services.test_dynamic_commerce_catalog` | 连续请求但目录版本未变化 | Passed |
| 目录版本变化后刷新快照并感知上下架 | Agent 长期读取旧目录 | `backend/package/yuxi/services/daily_commerce_service.py` | `python -m unittest backend.tests.unit.services.test_dynamic_commerce_catalog` | 版本变化或商品下架 | Passed |
| 结构化名称和别名可匹配且歧义不自动选择 | 错配或遗漏非硬编码食材 | `backend/package/yuxi/services/daily_commerce_service.py` | `python -m unittest backend.tests.unit.services.test_dynamic_commerce_catalog` | 同一别名对应多个食材 | Passed |
| 换菜保留日期、就餐人和餐次并排除近期菜谱 | 换菜串餐次或重复推荐 | `backend/package/yuxi/services/reference_meal_service.py` | `python -m unittest backend.tests.unit.services.test_reference_meal_service` | 当前及近期菜谱进入候选集 | Passed |
| 餐单提交不等待图片，图片由持久任务生成并缓存 | 图片供应商延迟阻塞餐单 | `backend/package/yuxi/services/reference_meal_completion_service.py` | `python -m unittest backend.tests.unit.services.test_reference_meal_completion_service` | 图片生成失败或超时 | Passed |
| 不修改页面、审核状态、订单或模拟业务数据 | 验证过程污染真实业务数据 | 本提案约束 | 检查本提案范围与对应实现差异 | 写订单、改审核状态或写模拟数据 | Inspected |
