# 小程序本人营养咨询接入

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_consultation_service.py

## 问题

账号接入模块读取真实本人关联后，还需要提出营养问题、读取异步执行状态和恢复历史。客户端需维持账号、健康成员、咨询线程、Request 与 Run 的绑定，避免重复提交、读取相邻答案和展示失效来源。

## 决策

在 `agent/miniapp/` 增加本人普通营养咨询页，复用现有认证请求、本人关联、服务端处理政策和固定 `health-consultation` 入口。进入页面重新读取当前本人权限、真实映射和基础档案状态。用户核对当前处理方与政策并明确选择咨询用途同意后，进入今日咨询或幂等新建独立咨询。普通文字问题沿用已持久化的 Request 和 Worker 队列；客户端按当前 Request 的 `dispatched_run_id` 读取 Run 和权威结果，完成答案严格匹配同一线程、请求、运行和最终 Message ID。

新增健康成员只读咨询列表，由 consultation service 校验当前字段授权，repository 以实际 HealthConsultation 的 actor、成员与 active Conversation／Project 查询固定角色，按创建时间及稳定 ID 降序分页。列表只返回线程、成员、角色、业务日期和创建时间。打开历史仍重新校验当前来源与读取权限，逐个读取最近20次完成普通咨询的权威结果。原型标题、通用线程 metadata 和工具消息不用于推断成员或答案。

当前请求意图只在页面内存保留。未知响应重试使用相同正文、线程及请求键；轮询有时间预算，超时继续读取原请求。账号变化、页面隐藏、401、403、404、失效来源和协议不一致均废弃旧 ticket，并清除旧正文，禁止迟到结果回填。PostgreSQL Integer 类型的 Message ID 在协议边界规范化后精确比较。固定健康角色的现有后端拒绝审批恢复，本页面只消费普通 chat；中断后用户可明确新建咨询重新提问。

公开结果接口没有结构化引用，页面明确说明未提供来源，正式引用查询及展示保留后续范围。当前配置不可用时展示服务端原因，并保留受当前权限控制的历史入口。

## 替代方案

复制原型演示聊天无法证明真实成员及运行绑定；嵌入完整平台聊天页会引入当前小程序不需要的工具、模型配置和审批入口。新建独立咨询后端重复已有授权、队列和历史职责。现有接入模块以三页完成账号、本人关联和普通咨询，原根目录 App 保持原样。

## 后果

已交付范围是本人普通营养咨询接入工程。原App业务页面接入、正式引用、记忆与反馈完整页面、餐单页面、微信code身份、公开HTTPS、开发者工具和真机分别验收。基础档案可读取不代表完整专业档案及营养安全规则就绪。隔离的合成资料与确定性模型回放证明HTTP、Worker和持久化链路；真实供应商、医学与长期质量需独立验收。

## 验证

2026-10-10 提交前复核补充：创建咨询和提交问题在网络异常或5xx响应下保留原键与正文，仅通过显式恢复重发原包。创建前同意失败和创建成功后的历史读取失败按各自阶段处理；授权／来源错误继续清理私有正文。新增测试以递增请求键和独立幂等收据模拟提交后丢失响应，覆盖0、500、502、503、504，证明普通按钮不能另建请求、原问题不可替换、成功恢复只形成一次逻辑写入。控制器33项通过，小程序全量66项中65通过、既有账号HTTP条件测试1项跳过。实际浏览器网络故障注入未执行。

- Backend：新增列表与既有 consultation unit 共16项通过。真实隔离 HTTP/Worker/独立PG E2E 2项通过，核对用途同意、重复原请求、同Run最终Message、第二轮、真实取消与失败、171cm版本2变为172cm版本3后的旧来源拒读、重新咨询读取当前版本、撤权与撤回同意。只读列表核对分页、同创建时间稳定排序、另一账号／成员、其他角色、停用Conversation／Project及读取无新增事实。
- Miniapp：全量50项测试中49项通过，既有账号HTTP条件测试1项跳过。覆盖固定角色与字段白名单、整数消息ID、工具／相邻Run过滤、未知POST原包重试、90秒有界轮询、配置不可用、退出／换号／隐藏、授权拒读和来源失效后的并发迟到响应。独立Reviewer重放撤权竞态并确认修复后的私有正文为空。
- Build与页面：H5及微信目标构建通过，均装配login、members、consultation三页。H5浏览器以独立合成账号明确同意并提出自然问题，经真实Worker显示本人171cm版本2对应权威答案；刷新后通过成员列表恢复同一咨询，重新进入不推断已同意。退出回到空登录页，换账号后的成员、线程和回答不包含原账号内容。375像素视口无横向溢出。
- 隔离边界：验收使用既有 internal 网络与独立数据库，只操作本轮随机合成账号、来源和临时provider。当前夹具实际清理通过，metadata标记已清理、所属PG行归零、配置原值及provider全表基线指纹一致，secret删除且独占回放进程停止；读取报告时核对当前夹具，避免引用旧轮结果。主服务API重载后ready通过，健康配置指纹保持一致，未调用主服务云模型或修改真实用户授权。
- Not run：微信开发者工具、真机、公开HTTPS、真实供应商、正式引用及医学质量。网络故障和未知提交语义由单测回放覆盖；实际浏览器网络故障注入未执行。

以下两组命令分别从仓库根目录执行：

```bash
cd agent/miniapp
pnpm test
pnpm run build:h5
pnpm run build:mp-weixin
```

```bash
cd agent/Yuxi-main
docker compose exec api uv run --group test pytest test/unit/services/test_health_consultation.py test/unit/services/test_health_consultation_list.py -q
```

E2E使用已有 `health-diet-analysis-e2e` 隔离槽，数据库须为 `health_consultation_e2e`、容器已配置 `HEALTH_CONSULTATION_E2E_ISOLATED=true`，网络为internal、ready通过、健康配置为空基线且没有运行lease。`test.support.health_miniapp_consultation_fixture`负责启动独占回放进程、创建随机合成账号及精确恢复清理。按顺序执行：

```bash
docker exec health-diet-analysis-e2e-api-1 uv run --no-sync python -m test.support.health_miniapp_consultation_fixture start-replay
docker exec health-diet-analysis-e2e-api-1 uv run --no-sync python -m test.support.health_miniapp_consultation_fixture create
docker exec -e HEALTH_MINIAPP_CONSULTATION_E2E=true health-diet-analysis-e2e-api-1 uv run --no-sync pytest test/e2e/test_health_miniapp_consultation_e2e.py -m e2e -q -o cache_dir=/app/test/.tmp/miniapp-consultation-20261010/pytest-cache
docker exec health-diet-analysis-e2e-api-1 uv run --no-sync python -m test.support.health_miniapp_consultation_fixture cleanup
```

测试消费owner来源版本。成功或失败后均执行精确cleanup并读取当前夹具报告；不使用主库或真实账号。重复运行先完成上一轮清理，再启动回放和创建新夹具。浏览器验收需要在cleanup前通过接入模块登录独立browser账号，明确同意并提出夹具metadata提供的合成问题；verify-browser子命令只读取PG核对当前Run与最终Message，不能用旧清理报告证明本轮恢复。
