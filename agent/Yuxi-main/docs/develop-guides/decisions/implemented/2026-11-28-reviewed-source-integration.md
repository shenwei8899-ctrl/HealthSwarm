# 已验证本地修复与后续主线的整合

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/daily_dish_swap_service.py

## 问题

本地交付的历史回看、页面加载与展示修复需要进入源码主线；功能分支与后续主线分别改变了换菜、资料补齐和餐单读取。整文件覆盖会丢失权限或锁定保护，也会回退候选按目标计算和图片延迟读取。

## 决策

### 实现方案

在主线基础上整合已有功能提交，再按实际语义 Owner 提取本地修复。换菜保持当前日、版本、原位置、幂等和成员资料重验，保留已执行、正在更新及归档回退餐次的拒绝条件。只为指定餐次和菜位计算候选，候选文本不等待图片存储探测；旧餐单归档入口继续显式选择归档视图。

历史回看使用独立读取授权；普通执行、引用与采购沿用严格授权。回复底部操作栏移除引用按钮，长按选择引用和引用来源撤回校验保留。资料正常改版允许回看，真实撤权、来源停用和记忆撤回仍拒绝相应内容与动作。

“我的”页面仅复用同账号和家庭的展示摘要，读取失败与权限拒绝分别处理，页面设置20秒读取期限；服务端业务入口不接受摘要作为授权。流式平滑显示只消费既有公开文本事件，最终结果替换临时预览。采购展示沿用 SKU 规格与服务端数量，核价、库存和配送约束由服务端拥有。

## 替代方案

整文件覆盖活动目录会遗漏主线后续修复，单独采用主线会丢失本地交付能力。按共同祖先进行语义整合，并在同一检出验证源码与测试，保留双方实际消费的能力和保护。

## 后果

源码通过新分支和草稿 PR 供审查。构建目录、发布回执、运行数据和凭据留在本地；生产数据库和正式小程序版本不变。包体、完整后端回归、界面与真机证据的限制需要在合并或正式发布前处理。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 页面缓存、历史只读、流式与引用交互保持契约 | Node / Vue 逻辑 | `CloudNutritionChat.vue`、`my-profile-loader.js`、`AiAnswer.vue` | App `npm test` | 跨账号摘要清除、授权刷新前禁用、撤回应答隐藏、只读业务卡片 | Passed：2205 passed、4 skipped |
| 历史读取区分改版与撤权 | HTTP / PostgreSQL | `HealthConsultationRepository.authorize_history` | `pytest test/integration/services/test_health_history_view_http.py` | 跨账号、来源停用、记忆撤回、旧上下文继续执行与引用 | Passed：8项通过 |
| 换菜、份量和名单执行边界保留 | HTTP / PostgreSQL | `daily_dish_swap_service.py`、名单与份量服务 | `test_daily_dish_swap_http.py`、`test_reference_serving_nutrition_pg.py`、`test_meal_roster_http.py` | 旧版本、锁定餐次、已记餐与采购复核 | Passed：21项通过 |
| 引用保存和撤回保持有效 | HTTP / PostgreSQL | 引用与聊天意图服务 | `test_health_reply_quote_http.py` | 伪造引用、来源失效、重放 | Passed：单独重跑1项通过；同批首次在创建成员时10秒超时，未到引用断言 |
| 按目标计算且拒绝锁定餐次 | Python unit | `daily_dish_swap_service.py` | `test_planning_profile_readiness.py`、`test_dish_swap_archive_guard.py` | 指定锁定午餐、晚餐仍可用时不得查候选 | Passed：14项通过 |
| 配送数量和储存约束保留 | PHP unit | `ExclusivePurchaseDeliveryService` | `php shop/tests/unit/ExclusivePurchaseDeliveryTest.php` | 缺包装、待审批规则、未知SKU、取整守恒 | Passed；13个变更PHP文件语法检查通过 |
| 工程规范与后端静态检查 | 工程契约 / Python | 检查脚本与54个变更后端源文件 | 工程检查、检查器unittest、Ruff check/format | 检查器63项负向测试 | Passed：工程契约、检查器63项、Ruff check/format均通过 |
| API小程序源码可编译 | 本地编译 / 包体 | App构建脚本 | 正式微信API构建、包体检查 | 正式API配置、测试登录禁用、分包预算 | 编译Passed；包体gate未通过：主包1,796,884字节，超1.7MiB预算14,305字节 |

后端全量 unit 正在完整复跑。首次中断结果为2478 passed、4 failed；同一四个失败在主线源码上复现（46 passed、4 failed），涉及旧测试替身和共享投影预期，不能据此声明全量通过。

H5本地正式API模式构建为Passed。界面视觉、浏览器业务链路、真机与正式上传包体为Not run。文档站点构建为Not run，检出未安装文档依赖。草稿 PR 的源码审查结论不代表可合并或正式发布。
