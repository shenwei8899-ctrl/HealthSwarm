# 小程序本人餐单草稿接入

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_meal_plan_service.py

## 问题

小程序已提供现有账号登录、本人关联及普通营养咨询。后台拥有已发布菜谱查询、三餐计算预览、餐单保存、换菜和历史修订接口，小程序尚未提供餐单页面。咨询回答不能代替业务餐单，普通草稿也不能显示为个体化建议或正式采用。

## 决策

### 实现方案

在既有 `agent/miniapp` 接入本人普通餐单页面，从成员页进入，重新读取当前账号的本人健康对象、真实家庭关联和饮食权限。先读取餐单列表、详情和历史，再允许选择已发布菜谱及明确计划份量，按现有业务接口预览、明确保存和换菜。页面展示服务端菜名、原料、克数、三餐和全天营养，缺失值保留为空。份量由用户填写，客户端不计算营养或推导个人目标。

业务状态及服务端授权沿用上述 Owner，本轮未修改生产后端；小程序生命周期由 `agent/miniapp/src/ui/meal-plan-controller.js` 拥有。本人、三个入口权限与家庭关联在进入或手动重新核对时读取；各业务请求正式校验沿用服务端 `diet_edit` 和账号、成员、餐单绑定。真实撤权验收针对 `diet_edit`，没有增加其他入口权限或家庭源变化的持续撤销通知。

请求层复用现有会话与迟到响应隔离；保存仅提交预览ID及幂等键，换菜携带原版本、`If-Match`及幂等键。网络与5xx未知写入保留原包，显式恢复原请求后读取权威业务结果。确认拒权、失效来源及身份切换清除私有内容；409版本冲突要求刷新核对。列表、详情、目录和预览读取各自拒绝过期选择的迟到响应。

普通草稿无需调用模型。该小程序模块作为接口联调和交接参考，正式小程序页面由客户端负责人交付，Agent 开发继续服务端能力与接口契约。个体化安全配餐、专业审核操作、正式采用、家庭多人流程、原App业务页面迁移、微信身份、公开HTTPS及真机验收属于后续范围。读取已有单成员个体化餐单可显示服务端快照，普通换菜仅开放普通草稿，避免改变其专业适用性语义。家庭餐单保留明确的后台查看提示。

## 替代方案

直接复用咨询聊天文本缺少版本、份量与保存事实；复制完整后台面板会引入本轮无需的专业管理、模型和多人控制。新建后端餐单系统重复现有事务、授权及计算职责。

公共份量参考按菜谱版本与页面 epoch 缓存，不依附请求发起菜位。早餐与午餐共用同一菜谱时，午餐改选不会使早餐丢失已发布参考；消费参考仍精确校验其菜谱版本。预览返回同时绑定当前成员、日期、三餐菜谱版本和菜数。服务端 Decimal 科学记数在模板中按字符串展开，不通过浮点数重算或改动营养精度。

成员页退出由会话订阅统一清理并跳转；退出按钮仅失效会话，避免额外并发导航。客户端会话版本和页面 epoch 同步失效，旧请求不能回填。

## 后果

已交付范围是本人普通三餐草稿的接入工程，补充[咨询接入](./2026-10-10-miniapp-nutrition-consultation.md)的后续餐单范围。原API列表有查询上限，页面明确显示截断；发布目录为空则提示后台准备。普通草稿不评价个人适用性，不代表专业审核、正式采用、采购或实际摄入。未保存的选择及未知提交意图只保留在本页内存，离开即清除；H5刷新沿用既有账号入口回到成员页，重新进入读取已保存餐单。完整小程序错误、事件流协议与其他业务页面继续按各自范围推进。

## 验证

- Miniapp：`pnpm test` 共116项，115通过，既有账号HTTP条件测试1项因未配置其独立夹具而跳过；本轮真实餐单HTTP由下面的专属夹具验证。餐单请求、控制器、投影及真实Vue模板共50项通过。覆盖0、500、502、503、504提交后丢失响应的原包原UUID恢复，普通按钮不重复写入，POST确认后只GET恢复，409废弃旧意图，拒读与页面 epoch 清理；缺失值和零分别显示，历史与个体化餐单只读、家庭不读取详情。
- 独立语义 Review：发现并复核修复同菜谱跨菜位参考竞态。纯内存恢复旧选择位门禁后，新增并发用例因丢失早餐参考准确失败；修复版本通过。Reviewer独立执行餐单逻辑46项、实际模板4项及14个科学记数精度边界；无未解决阻断问题。测试替身不作为PG或真实页面证据。
- HTTP与PG：专属 `test/e2e/test_health_miniapp_meal_plan_e2e.py` 1项通过，防误库unit 2项通过；使用 `health_consultation_e2e` 独立数据库、internal网络、随机合成账号与已发布合成菜谱。核对预览没有business plan，明确save仅v1、swap仅v2及修订1/2，重复键无多写、旧版409、另一账号和撤销diet_edit拒绝、未发布菜谱及错误参考422。独立数据库读取核对最终spec与snapshot，不以HTTP200替代持久化。
- H5：实际表单选择早餐50g、午餐100g、晚餐150g，显示具体菜名、原料与700kcal；独立PG核对只有预览。明确保存后更换午餐为第四已发布菜谱100g，当前v2和900kcal，历史v1保留原午餐及700kcal且没有换菜按钮。浏览器PG校验精确匹配v1、v2及current spec，只1份餐单、2条修订，钠为null、脂肪为0。页面刷新经本人入口恢复v2，未保存选择为空。375 CSS像素视口无横向溢出。输出在 `agent/.tmp/miniapp-meal-plan-20261010/` 及 `backend/test/.tmp/miniapp-meal-plan-20261010/`。
- 构建：最终H5和微信目标均通过；Ruff、Python编译与 `git diff --check` 通过。普通业务没有调用模型、Worker、采用或记餐，也没有新增用途同意；独立PG核对无对应额外事实，配置/provider全表基线指纹一致。
- 退出与切号：原账号退出到空登录页，另一账号仅显示自己的成员与餐单，不含原账号成员ID、身份或换菜原因。发现并消除了旧退出按钮与会话订阅的重复跳转；最终独立浏览器tab重新读取v2后退出，私有内容为空且console error为0。Reviewer增量审阅会话清理与迟到隔离路径，并独立执行13项会话测试通过。
- 清理：独立PG连接核对11组本轮资源列及全表反向外键残留均为0，配置/provider全表基线不变，宿主与容器的私有凭据文件均删除。两个任务浏览器tab已关闭、视口已恢复，操作内存凭据已清空；仅关闭本轮临时H5端口5176，未停止主服务。归零证据见 `backend/test/.tmp/miniapp-meal-plan-20261010/closure-verification.json`。
- Not run：微信开发者工具、真机、微信身份、公开HTTPS、生产专业审核/正式采用及真实云模型验收。验收阶段未改生产后端或部署；实际浏览器网络故障注入未执行，原包恢复由独立收据回放和真实HTTP幂等验证。profile_view/profile_edit或家庭来源变化后的持续撤销通知未新增，也未作为本轮验收主张。

小程序命令在 `agent/miniapp` 执行：

```bash
pnpm test
pnpm build:h5
pnpm build:mp-weixin
```

隔离夹具按顺序使用，不能改用主库。容器必须配置 `HEALTH_CONSULTATION_E2E_ISOLATED=true`，实际库名、Schema、ready与配置基线通过后才允许创建；浏览器验收在cleanup前进行。

```bash
docker exec health-diet-analysis-e2e-api-1 uv run --no-sync python -m test.support.health_miniapp_meal_plan_fixture create
docker exec -e HEALTH_MINIAPP_MEAL_PLAN_E2E=true health-diet-analysis-e2e-api-1 uv run --no-sync pytest test/e2e/test_health_miniapp_meal_plan_e2e.py -q -o cache_dir=/app/test/.tmp/miniapp-meal-plan-20261010/pytest-cache
docker exec health-diet-analysis-e2e-api-1 uv run --no-sync python -m test.support.health_miniapp_meal_plan_fixture verify-browser
docker exec health-diet-analysis-e2e-api-1 uv run --no-sync python -m test.support.health_miniapp_meal_plan_fixture cleanup
```

夹具凭据只写入忽略目录的secret文件，不打印、不入Git；最终清理只针对本轮所有权ID。verify-browser要求实际界面按metadata中的明确spec保存并换菜，不能以创建夹具或旧报告代替本轮页面结果。
