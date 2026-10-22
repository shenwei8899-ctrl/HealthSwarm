# 小程序与 HealthSwarm Agent 源码对齐修改说明

日期：2026-10-13。状态：实施中；第 17 节记录已落地范围。面向小程序开发、Agent 后端开发和商城对接人员。

目标是保留现有小程序页面与交互，将登录、档案、咨询、配餐、识图和记录接到团队真实服务，并明确商城、多日计划、语音及专业数据的交付缺口。已有接口可复用，但客户端数据结构、身份关联和异步状态不能直接照搬；不能仅切换 API 地址就宣告接通。

## 1 核对范围与源码基线

| 对象 | 本次核对位置 | 使用边界 |
| --- | --- | --- |
| 当前小程序 | 工作区根目录的 `src/`、`tests/`、`docs/` | 当前本地源码是修改依据；不以编译产物代替源码 |
| 团队 Agent | `HealthSwarm/agent/Yuxi-main/` | 已同步的 `main` 提交 `a6f3554742952a2806caed75cf446416c1fc011b`；业务 Schema 12、健康 Schema 24 |
| 团队联调小程序 | `HealthSwarm/agent/miniapp/` | 提供账号、本人关联、咨询、普通餐单的客户端参考，不替换正式小程序 |
| 微信登录及商城整合副本 | `.codex/healthswarm-merge-20261012/` | 之前只在本机 `integration/healthflow2-20261012` 分支创建的 Git 提交 `1350355c681e2aea2b123b9165ab84b165125bfd`；未推送该分支，也未合入 GitHub `main`，更未部署生产 |

本文中的 `App:` 指当前工作区根目录；`Agent:` 指 `HealthSwarm/agent/Yuxi-main/`；`Merge:` 指上述本地整合副本。这样可以避免把三个目录的同名文件当成同一份源码。

本地小程序没有可作为本次基线的提交记录，且本次核对时已有新增的 `meal-planning.js`、`exclusive-planning.js`、`meal-plan-store.js` 和 `meal-result.js`。这些文件仍可能在并行开发中变化；实施前应重新检查工作区和第 16.4 节列出的关键入口，判断方案是否需要更新。不能覆盖这些已存在的改动。

本节记录方案编写时的源码基线；已实施部分见第 17 节。接口存在表示源码已有入口，不表示部署、真实模型、数据库、微信或支付已验收。

联调前双方应记录实际部署提交、业务及健康 Schema 版本、API/Worker 镜像版本、公开 API 地址和运行时 OpenAPI。上述 Git 提交是源码基线，不是联调环境的部署证明。当前本地工作树另有未提交的微信登录与 business Schema 13 补丁；不能把它当成 GitHub `main` 或同事已可访问的代码。

### 1.1 产品规则优先级

实施同时遵循当前[产品需求规格](../../../docs/家庭AI营养师-小程序产品需求规格-v1.0.md)、[全人群配餐修改方案](../../../docs/家庭AI营养师-全人群配餐修改方案.md)和[菜品营养契约](../../../docs/菜品营养字段与后端存储契约.md)。发生旧描述冲突时，以 2026-10-13 已确认的产品补充为准。

必须保持以下行为：

1. 全体家庭成员可建档和使用，不因未成年、孕期或哺乳身份直接拒绝整餐；专业依据不足时明确说明可支持范围，并围绕当前建议追问。
2. 保留现有建档字段与流程，不新增孕期、产后、哺乳期等必填阶段项，不例行询问所有女性成员。
3. 不新增用户人工健康审核步骤。当前后端已有的专业规则和批准状态需要由业务负责人对齐产品流程，不能简单增加一个审批页面来消化差异，也不能把模型完成状态当成批准。
4. 已生成建议持久保存；打开页面优先读取同一份结果。成员或菜品变更只影响目标日期和餐次；多日变更先预览并明确确认。
5. 已支付订单的商品、价格、配方、配送和营养快照保持交易时事实。新的饮食建议不能直接改写已支付订单。
6. 保留明确的过敏、不耐受、忌口和医嘱冲突检查；未知、已明确无、真实零值必须分别处理。
7. “健康设备”保持现有敬请期待页面，本次不增加测量、绑定或模拟设备数据。

### 1.2 当前能力与实施判断

| 模块 | 当前源码事实 | 实施判断 |
| --- | --- | --- |
| 微信登录 | App 调用 `/api/auth/wechat/*`；GitHub `main` 未注册这些路由；本地工作树已有未提交候选补丁 | 复核并交付微信身份链路，完成迁移、真实 HTTP 和真机验收后开放 |
| 家庭档案 | `/api/family` 已有创建、成员、版本修改、邀请和授权 | 可接；完整表单需字段映射，部分字段语义待补 |
| 健康业务成员 | `/api/health/v1/members` 与本人档案关联接口已存在 | 与家庭档案成员是两种对象，必须正式关联 |
| 咨询与历史 | 固定健康角色、每日咨询、Request、Run、结果查询已存在 | 可接；需要异步执行、恢复和结果分类 |
| 指标记录助手 | 新增血糖、血脂、血压三类回顾 Task 和固定 Agent；固定健康 Agent 合计八个，均为 `partial` | 只回顾授权实测记录和审核科普；不等于控糖计划或诊断 |
| 当日及家庭餐单 | 预览、保存、换菜、参与者调整、专业状态和采用入口已存在 | 可接；餐单、专业状态和采购必须拆开处理 |
| 全人群适配 | App 有相关产品规则和生成适配入口 | 后端适用规则及正式专业数据仍需验收，不能宣称现有成人规则已覆盖全部人群 |
| 识图和报告 | 上传、异步任务、候选草稿、计算和确认入口已存在 | 可接；图片不能直接发给健康咨询角色 |
| 记录和反馈 | 单成员饮食记录、单餐及 1/7/30 天分析、反馈及记忆已有入口 | 可接；家庭桌菜批量保存、已确认记录更正及前端趋势语义需补齐 |
| 菜品营养 | 后端支持五个营养代码，计算值常用十进制字符串 | 六项卡片需适配每百克口径，并增加膳食纤维 |
| 商城 | Agent 采购输出可食需求，`purchase_available=false`、`order_available=false` | 商品、报价、支付和配送走独立商城对接 |
| 21 天及控糖 | `multi_day_plan`、`glucose_plan`、`automatic_family_coordination` 仍返回依赖未就绪 | 后端业务能力待补；血糖回顾助手不能冒充控糖计划 |
| 语音 | App 有录音与 `transcribeVoice` 适配入口 | 转写服务、上传协议及用途契约待提供 |

## 2 总体修改方式与文件分工

保留 Uni-app 与 Vue 3 页面，通过现有服务层连接后端。营养计算、权限、持久化版本和交易最终状态由所属后端负责。前端负责成员选择、输入校验、字段转换、任务状态和可理解的结果展示。

不复制团队联调 miniapp 覆盖现有 App，不把通用 Yuxi 管理端当成正式小程序，不在客户端重新建立一套权威营养数据库。

### 2.1 小程序现有文件修改清单

| 现有文件 | 修改内容 | 优先级 |
| --- | --- | --- |
| `src/services/request.js` | 可传请求头、精确会话校验、健康错误解析、结果未知处理 | P0 |
| `src/services/session.js`、`storage.js` | 保留账号家庭隔离，加入请求级会话修订校验和分域清理策略 | P0 |
| `src/services/wechat-auth-client.js`、`wechat-auth.js` | 核对合入后的微信登录响应；保留 AppID 对照、切换账号拒绝迟到响应 | P0 |
| `src/services/index.js`、`src/main.js` | 在明确初始化入口注册已实现的 API 适配器；避免循环依赖 | P0 |
| `src/services/navigation.js` | 每个页面完成真实数据链路后逐项开放，不一次放行所有页面 | P0 |
| `src/pages/account/index.vue`、`family-onboarding.js` | 继续使用家庭接口，补活动量和正式版本状态的展示与恢复 | P0 |
| `src/utils/profile.js`、`pages/onboarding/index.vue`、`pages/profile/index.vue`、`pages/profile/member.vue` | 用服务器读写取代正式模式本地档案；同步字段、成员归属、确认和邀请 | P1 |
| `src/pages/chat/index.vue`、`chat/history.vue` | 替换文字演示分支，读取按成员和日期绑定的历史与结果卡片 | P1 |
| `src/services/meal-planning.js`、`utils/meal-result.js`、`utils/meal-plan-store.js` | 复用生成入口，改为后端任务和业务快照；取消餐单对真实商品价格的前置依赖 | P1 |
| `src/utils/meal-state.js`、`meal-context.js`、`meal-customization.js` | 读取已保存来源，局部变更，服务端确认次日提议及换菜，不根据无关聊天重算 | P1 |
| `src/pages/shop/index.vue`、`pages/plan/index.vue`、`components/DinerPicker.vue`、`components/MealNotes.vue` | 对齐计划、参与者、逐人份量、采购状态和异常操作 | P1 |
| `src/services/chat-images.js`、`pages/chat/camera.vue`、`pages/scan/index.vue` | 接上传和识图状态，保留原相机体验及用户确认 | P1 |
| `src/pages/reports/index.vue`、`reports/detail.vue` | 接报告候选核对、确认与权限，不使用固定演示指标 | P1 |
| `src/pages/records/index.vue`、`records/detail.vue`、`feedback/index.vue`、`memories/index.vue` | 接记录分页、反馈和记忆版本；移除正式模式本地写入成功提示 | P1 |
| `src/utils/dish-nutrition.js`、`components/DishNutritionCard.vue`、`pages/recipe/index.vue`、`pages/cook/index.vue` | 统一数值与每百克口径，读取版本菜谱，保留订单快照 | P1 |
| `src/services/exclusive-planning.js`、`utils/exclusive-plans.js`、`pages/exclusive-plans/*` | 多日能力未提供时明确禁用真实生成，完成后接多日版本和预览确认 | P2 |
| `src/pages/address/*`、`pages/orders/*`、`utils/checkout-state.js`、`utils/orders.js` | 精选引入独立商城适配；真实状态由交易系统查询 | P2 |
| `src/services/chat-voice.js`、`components/VoiceInput.vue` | 转写协议到位后接真实上传，保留录音授权与失败重试 | P2 |

### 2.2 建议新增的小程序适配模块

下列名称是建议新增文件，不是已存在接口。允许按现有代码风格合并相邻职责，不为单次转发拆出无实际用途的模块。

| 建议文件 | 责任 |
| --- | --- |
| `src/services/health-client.js` | 封装已存在的成员、关联、就绪、用途同意、任务和记录接口 |
| `src/services/health-task.js` | 管理一次 Request/Run 的提交、等待、取消、恢复及权威结果读取 |
| `src/services/health-projection.js` | 将已确认 DTO 转为页面对象，校验成员、版本、日期、计量口径；不伪造专业状态 |
| `src/services/health-integration.js` | 注册完成的 API 适配器和对应页面；由 `main.js` 显式引入 |
| `src/services/health-media.js` | `uni.uploadFile` 与私有预览下载、上传 ID、识图任务的鉴权和会话校验 |

注册时至少列清楚 `generateMealPlan`、档案读写、咨询、记录读取、报告处理和图片路径。`generateExclusivePlan`、`transcribeVoice` 等没有真实契约时保持不可用，不注册一个返回演示对象的实现。

### 2.3 Agent 与商城修改责任

| 文件或模块 | 责任与修改边界 |
| --- | --- |
| `backend/server/routers/__init__.py` | 注册精选合入的微信路由；保持现有健康路由 |
| `wechat_auth_router.py`、`wechat_login_service.py`、`wechat_identity_repository.py` | 从 Merge 提取，复用业务账号和 JWT，不自动创建家庭或健康授权 |
| `storage/postgres/models_business.py`、`manager.py`、`storage_migrations/` | 按最新数据库版本合入微信身份模型和正式增量迁移，不直接覆盖管理器 |
| `family_schemas.py`、`family_service.py`、`family_repository.py` | 补齐已确认档案字段语义、权限和版本；迁移由存储 Owner 执行 |
| `health_family_profile_service.py` 与对应 repository | 保留本人明确关联边界；代成员路径需要独立设计，不能扩大现有本人接口 |
| `health_vision_types.py`、`health_nutrition_service.py`、`health_vision_service.py` | 增加纤维代码与来源字段；补菜谱公开展示所需字段；保持不可变已发布版本 |
| `health_task_types.py`、`health_task_service.py` | 优先复用现有分类；仅在实际新增业务 Owner 后扩展多日或新媒体类型 |
| `health_meal_plan_service.py`、家庭餐单与参与者服务 | 支持正式业务保存、局部调整与来源校验，不把采购和专业批准揉成一个状态 |
| `health_vision_service.py`、`health_vision_repository.py` | 若产品继续要求家庭桌菜原子保存、确认后更正，补所属业务事务及公开契约 |
| `Merge: shop/` 及商城客户端 | 商品、地址、报价、交易、支付和配送由商城负责；Agent 只输出可授权采购需求 |

## 3 微信登录与身份链路

### 3.1 当前阻塞与合入范围

App 的 `wechat-auth-client.js` 已调用以下协议，但 GitHub `main` 的 `auth_router.py` 只提供现有账号认证，路由注册中未包含微信路由。本地工作树已从整合副本精选加入微信路由及依赖，仍未提交、共享或部署：

| 方法与路径 | 输入 | App 已要求的输出 |
| --- | --- | --- |
| `GET /api/auth/wechat/config` | 无认证 | `available`、`appid` |
| `POST /api/auth/wechat/login` | 微信临时 `code`；显式绑定时同时带 `identifier`、`password` | `access_token`、秒级 `expires_at`、`account`、`families` |
| `GET /api/auth/wechat/session` | 业务 Bearer token | 当前 `account` 与可访问 `families` |

微信源码来源是 Merge 的 `backend/server/routers/wechat_auth_router.py`，而非直接改通用密码登录接口名称。应一起提取服务、repository、身份模型、路由注册、`v013_wechat_identity.py`、配置及相关测试。

团队 `a6f3554` 基线为 business Schema 12、health Schema 24；Merge 的微信身份增量为 business Schema 13，第 17 节记录的当前本地工作树已引入该增量。正式合入前仍须核对业务迁移版本是否被团队其他开发占用，并在现有数据库副本验证 12→13 的幂等迁移；如版本已占用，按正式迁移流程重新分配和审查。API 与 Worker 必须使用同一兼容版本，不能只提高常量而不迁移数据库。

服务端配置沿用源码实际名称：`WECHAT_LOGIN_ENABLED`、`WECHAT_APP_ID`、`WECHAT_APP_SECRET`、`WECHAT_AUTO_REGISTER`、`WECHAT_USER_DEPARTMENT_ID`。客户端只配置公开 `VITE_WECHAT_APPID` 与 HTTPS 服务地址。AppSecret、微信会话密钥及交易密钥不得进入客户端配置。

### 3.2 会话响应与成员选择

登录成功后，App 继续按 `projectLogin()` 校验 token、到期时间、正整数账号 ID 和家庭列表，再选择当前家庭。`families` 每项至少含字符串 `id`、`name`、布尔 `onboarding_required`；`is_owner` 用于现有展示。不要把 `/api/auth/token` 返回的 `uid/user_id/username` 原样交给 `projectLogin()`，两种成功形状不同。

一次微信登录不自动授予其他家庭成员健康访问权。新账号没有家庭时进入现有创建或加入家庭流程，不默认创建演示成员。

### 3.3 验收要求

AppID 不一致、缺配置、无效或过期 code、显式绑定冲突均有明确失败；重试不会把账号绑定到错误身份。切换账号后，旧登录和旧家庭请求的迟到结果不能覆盖新会话。正式验收必须覆盖微信开发者工具与真机，模拟微信 HTTP 响应只能验证工程路径。

## 4 请求封装与公共协议

### 4.1 request 的目标形状

在现有 `request()` 上增加可选请求头和精确会话修订检查，保留 HTTPS 校验和 `{ data, traceId }` 的成功返回方式。建议调用形状如下，这是客户端内部接口设计：

```js
request({
  path, method: 'POST', data,
  headers: { 'Idempotency-Key': data.client_request_id },
  timeout: 15000,
  authenticated: true,
})
```

认证头由请求层从当前会话设置，不能让业务传入的 `headers` 覆盖为其他账号 token。对于版本编辑按实际路由追加 `If-Match: "<version>"`。上传也应复用同等的账号与修订检查，而不是绕开请求层约束。

现有 `storageContext()` 只按模式、账号和家庭构造隔离键。同账号重新登录可能仍落在相同 scope，旧 token 的 401 不能直接清除新 token。因此发请求时同时记录 `sessionRevision()` 或 token 快照；收到 401 先确认原会话仍为当前会话，再清理。403、网络超时和 5xx 不按登录失效处理。

### 4.2 各路由的幂等与版本要求

| 写入类型 | 正文 | 请求头 |
| --- | --- | --- |
| `/family` 创建、加入、档案修改与确认 | 沿用各自 DTO；修改与确认使用 `expected_version` | 不凭空增加健康路由的统一要求 |
| 健康成员创建、授权、用途同意、本人的档案关联 | 沿用各自 DTO | 当前这些入口不要求统一幂等头或 If-Match；建健康成员每次会创建新对象 |
| 普通 `/consultations`、统一 `/task-entries`、餐单保存、识图任务与确认 | `client_request_id` 为合法 UUID | `Idempotency-Key` 等于正文 UUID |
| 固定 `/meal-planner`、`/diet-analyst`、反馈会话、安全改版会话 | 按实际 DTO 带 `client_request_id` | 当前这四类固定会话入口不额外要求上述两个头 |
| 餐单换菜、安全换菜、记忆和反馈修改 | UUID 创建键与当前 `version` | 幂等头和 `If-Match: "<version>"` |
| 识图草稿 PATCH | `version`、修改原因和对应载荷 | `If-Match: "<version>"` |
| `/api/agent/runs` | `agent_slug`、`thread_id`、`query`、`meta.request_id` | 运行去重以原始 Request ID 为准，不等同于业务创建键 |

新增 `client_request_id` 使用 UUID，不能把现有 `meal-时间戳-随机串`、`exclusive-时间戳-随机串`、`chat-...` 直接当成后端 UUID。可以保留这些字符串作为客户端展示关联键，另生成后端业务键，并在未知结果重试时复用原键与原正文。

### 4.3 错误解析

健康路由的 `HealthRoute` 返回顶层 `code`、`message`、`trace_id`、`retryable`，`detail` 通常是字符串；当前实现只对 429/503 设置 `retryable=true`。普通登录、家庭和通用 Agent 路由不保证同一错误 JSON 形状，客户端需分别兼容。第 17 节记录的 App 请求层已支持健康错误顶层字段，但真实服务的状态与页面投影仍需联调。

```json
{
  "detail": "If-Match 必须为当前草稿版本",
  "code": "version_conflict",
  "message": "If-Match 必须为当前草稿版本",
  "trace_id": "诊断标识",
  "retryable": false
}
```

示例仅说明顶层错误结构，具体业务 code 以所属路由为准。请求层按“健康顶层结构 → FastAPI detail 字符串或对象 → 验证错误数组 → HTTP 通用提示”解析，不把验证错误数组展示成 `[object Object]`。

| 情况 | 页面处理 |
| --- | --- |
| 401 | 当前请求对应会话失效时退出；迟到旧会话结果丢弃 |
| 403 | 清除当前无权展示的数据，说明授权不足；不伪装为空列表 |
| 404 | 区分业务对象不可访问与未实现路由，不继续使用旧对象 |
| 409 | 读取当前版本并要求用户重新核对；不自动用新版本重放旧修改 |
| 410 | 隐藏失效来源及其结果，明确重新选择或发起新任务 |
| 422 | 区分输入校验、业务缺项和不支持的载荷，展示可操作信息 |
| 429、503 | 根据实际就绪状态和允许动作显示等待、重试或人工填写 |
| 超时、断网、服务端未知写入结果 | 保留原键和原意图，先读取或按同键核对，不自动创建第二笔 |

只对幂等契约明确的操作提供原包恢复。家庭创建和健康成员建档等没有同样的幂等保证，超时后先回读列表，不盲目重复 POST。

## 5 家庭档案与健康成员关联

### 5.1 两种成员不能共用一个 ID

App 当前成员经常是数字或本地时间戳，家庭服务成员和健康业务成员则是独立服务器对象。应在页面数据中明确保留以下标识：

| 标识 | 含义与使用位置 |
| --- | --- |
| `accountId` | 当前登录账号；App 使用字符串形式，来源是已验证登录响应 |
| `familyId` 或现有 `householdId` | 当前授权家庭 UUID |
| `sourceMemberId` | `/api/family/{fid}` 返回的正式家庭成员 UUID |
| `healthMemberId` | `/api/health/v1/members` 返回的健康业务成员 UUID |
| `profileVersion` | 对应家庭档案确认版本；与专业安全投影版本分开 |
| `healthProfileVersion` | 被配餐、规则或专业投影实际引用的版本，不从家庭 version 推算 |

本人关联使用现有 `POST /api/health/v1/members/{healthMemberId}/family-profile-link`：

```json
{
  "family_id": "11111111-1111-4111-8111-111111111111",
  "source_member_id": "22222222-2222-4222-8222-222222222222",
  "confirmed_identity": true
}
```

以上 UUID 是合成示例。关联成功后用同路径 GET 回读，不靠昵称、关系、数组顺序或数字相等猜测。该入口服务于本人，不能拿本人 token 自动绑定父母或孩子的档案。

家庭创建不会自动创建健康业务成员。本人首次使用健康功能时，先回读健康成员；确需新建且具有相应依据时按 `MemberInput` 发送 `display_name`、`relationship_label`、`authorized:true`。`authorized:true` 不是客户端绕过授权的开关，页面操作和服务端必须有实际授权依据。

家庭成员代操作需要家庭档案字段授权、健康访问 scopes、模型用途同意及有效代理依据分别满足。团队角色说明仍将管理员代成员联调列为缺口，首个可验收链路应从本人开始；随后完成家庭代理链路，保留所有成员的产品入口，不以“暂未联调”永久删除成员或套用本人身份。

### 5.2 档案字段映射

`ProfileInput` 拒绝额外字段。不能将整个 `getProfile()` 或 `MemberFields` 对象原样发送；使用白名单投影。

| 当前 App 字段或语义 | 已有后端字段 | 修改说明 |
| --- | --- | --- |
| `gender` | `sex` | 女、男、暂不说明分别映射 `female`、`male`、`unspecified`；未填写用 null |
| `birthDate` | `birth_date` | 保留真实生日；年龄和月龄按建议对应日期派生 |
| `height` | `height_cm` | 合法有限数值；空输入不能转 0 |
| `weight` | 独立 measurements 的 `kind=weight` | 当前 ProfileInput 没有 weight 字段；必须带采集日期和来源，不自动把旧展示值当成当天实测 |
| 饮食目标、`goals` | `goal`、`health_goals` | 基础目标文本与带来源、日期、状态的目标记录分别处理 |
| `conditions`、`otherCondition` | `medical_history`、`condition_records` | 区分自述、已确诊与未知；保留来源，不因上传报告就设为确诊 |
| `clinicianGuidance` | `doctor_instructions`、`instruction_records` | 保留医嘱来源、核对时间及有效期 |
| `allergies` | `allergens`、`allergy_records` | 已明确无用空集合；未知用 null 或待确认状态，不能两者都映射空数组 |
| `avoidances` | `avoidances` | 既有忌口可映射，但要保留未知语义 |
| `intolerances`、`intoleranceStatus` | 当前无同名独立字段 | 需要后端确认独立存储、发布投影及校验契约，不能悄悄并成过敏或丢弃 |
| `flavors`、`cuisines`、`tastePreferences` | `preferences` | 当前后端主要是文本；若产品要保留各选项和状态，需扩展结构或定义可回读映射 |
| `healthStatus`、`allergyStatus`、`avoidanceStatus`、`doctorStatus` | 无完全一一对应的状态字段 | 明确“未知／无／有／未核对”的编码；无法无损保存时补后端 DTO 和迁移 |
| `usageMode`、`defaultDiners`、逐餐成员选择 | 家庭 settings 与餐单 participation 分属不同对象 | 个人或家庭使用方式及默认成员需确认持久字段；逐餐选择保存到餐单，不修改其他餐次 |
| 报告列表和共享状态 | 健康上传、候选、确认记录与访问 scopes | 不是 ProfileInput 中一个 reports 数组，按实际来源和权限读取 |

特别注意：基础档案的 `ready` 依赖性别、生日、身高、活动量、目标及当前确认版本，不代表完整营养安全档案已就绪。现有三步建档是否提供活动量，应由页面映射和后端基础规则共同核对；不能默填 moderate 来让 ready 变 true，也不能因为基础 ready 不完整而整体阻止普通科普咨询。

当前成员的 `/capabilities`、`/readiness` 和按用途的处理同意分别提供入口提示、依赖诊断与授权事实。客户端按成员和用途区分 `missing_scopes`、`consent_required`、`selection_required`、`configuration_unavailable`、`external_contract_required` 等情况；`capabilities=available` 也不替代提交、工具读取和最终发布时的服务端重验。第 17 节的本人关联页面已加入选定健康成员的只读诊断展示，并可进入独立健康助手页进行咨询或指标回顾；单日配餐仍未解锁，基础档案 `ready` 不能替代专业就绪。

### 5.3 现有家庭接口消费顺序

| 操作 | 已存在接口 |
| --- | --- |
| 创建、列出、读取家庭 | `POST/GET /api/family`、`GET /api/family/{fid}` |
| 创建成员关系 | `POST /api/family/{fid}/members`，只提交名字和关系 |
| 更新档案 | `PUT /api/family/{fid}/members/{mid}`，正文为 `expected_version` 和 `profile` |
| 本人确认 | `POST /api/family/{fid}/members/{mid}/confirm`，确认实际读取的当前版本 |
| 邀请和加入 | `POST /api/family/{fid}/members/{mid}/invite`、`POST /api/family/join` |
| 字段及用途授权 | `PUT /api/family/{fid}/members/{mid}/authorization` |
| 健康成员与访问范围 | `GET/POST /api/health/v1/members`、`PUT /members/{id}/grants` |
| 当前入口诊断 | `GET /api/health/v1/members/{id}/readiness`、`/capabilities` |
| 模型用途同意 | `POST /api/health/v1/members/{id}/processing-consents` |

每次更新后回读服务器档案与新版本，再更新页面。邀请必须使用真实短期邀请码或分享载荷；不将 `utils/invitations.js` 的本地认领状态当作服务端授权。

### 5.4 模型用途与数据范围

用途同意使用 `purpose`、`accepted`、`processor`、`policy_version`，政策来自当前配置。已有用途包括 `consultation`、`meal_plan`、`meal`、`report`、`diet_analysis`、`quality_review`、`purchase`；某用途同意不能替代全部用途同意。

正式 API 模式不把家庭所有健康字段直接塞进 `generateMealPlan(input)` 的 HTTP 正文。客户端传成员选择、日期、对象和版本，服务端读取已授权事实与当前必要的上下文。当前内部 input 可以继续服务 mock，但 API 适配器必须按后端 DTO 建白名单，不发送 `paidOrder.cookingGuides` 等无关敏感或交易数据。

## 6 AI 咨询与异步任务

### 6.1 统一入口与每日会话

普通独立咨询可使用统一任务入口：

```http
POST /api/health/v1/members/{member_id}/task-entries
Authorization: Bearer 当前业务会话
Idempotency-Key: 33333333-3333-4333-8333-333333333333
```

```json
{
  "task_type": "consultation",
  "client_request_id": "33333333-3333-4333-8333-333333333333"
}
```

`entry_status=ready` 只表示固定线程已建立；随后按返回的 `agent_slug`、`thread_id` 和 `request_submit_url` 显式提交 `/api/agent/runs`。`needs_input` 或 `dependency_not_ready` 不创建假 Request，也不默认为可运行：

```json
{
  "agent_slug": "health-consultation",
  "thread_id": "44444444-4444-4444-8444-444444444444",
  "query": "我想了解这餐记录应该如何看",
  "meta": { "request_id": "55555555-5555-4555-8555-555555555555" }
}
```

普通提交不带客户端模型、工具、健康规则或授权覆盖。Task 入口创建键与本次问题的 Request ID 是两个不同 UUID；提交成功后保存服务端返回的实际 `request_id`，不能把入口的 `client_request_id` 当作它。

产品按天历史可使用现有 `POST /members/{member_id}/daily-consultations`、`GET /members/{member_id}/daily-conversations` 和聊天线程 history。业务日期由服务器北京时间确定。每日会话与独立咨询是两种明确入口，不能每次问问题都创建一个新的日线程，也不能将某成员的日历史当成全家共有健康正文。

### 6.2 请求执行与结果分类

提交后保存实际 `request_id`；初始响应可能带 `run_id`，排队 Request 后续查询使用实际 `dispatched_run_id`。不能默认两次响应字段相同，更不能拿相邻 Run 填补当前结果。

最小接入可以参考团队 `agent/miniapp` 的普通 HTTP 查询方式；具体轮询间隔、等待预算由联调确认。断线后先读取同一 Request 的任务投影 `GET /api/health/v1/tasks/{request_id}`，核对成员、线程与实际 Run；`request_status` 是排队事实，`execution_status` 是 Run 事实，`result.result_type` 才是可展示类别。后续需要流式体验时只订阅该 Task 返回的 `request_events_url` 或 `run_events_url`，补齐微信分块响应与游标恢复；流结束仍回读同一 Task 的当前授权结果。

| 所属状态 | 实际枚举或分类 | 页面含义 |
| --- | --- | --- |
| 入口 | `ready` | 可以提交，不表示 AI 已回答 |
| 入口 | `needs_input` | 展示具体选择或问题，不创建假结果 |
| 入口 | `dependency_not_ready` | 展示当前缺项和允许操作，不默降级为 demo |
| Request | `queued`、`dispatched`、`cancelled`、`rejected`、`failed` | 排队、已派发或请求级结局 |
| Run | `pending`、`running`、`cancel_requested` | 执行中；取消请求还不是已取消 |
| Run | `completed`、`failed`、`cancelled`、`interrupted` | 真实执行结局；中断与追问不同 |
| 业务结果 | `general_education_answer` | 显示咨询正文及同一答复的有效引用，不贴个体化安全通过标签 |
| 业务结果 | `needs_input` | 展示已完成运行的追问 |
| 业务结果 | `meal_plan_preview` | 显示预览，后续保存、专业状态、正式采用分别处理 |
| 业务结果 | `diet_analysis`、`meal_feedback`、`quality_check`、`ingredient_requirements` | 按各业务快照显示，不统一压成一段 text |
| 业务结果 | `error` | 显示固定错误结局，不展示失败 Run 的片段正文 |

等待超时只表示客户端停止等待，不把服务器状态改成 failed。用户继续读取时恢复原 Request。只有服务器明确失败且用户发起新的意图，才使用新的创建键。

### 6.3 三项指标记录助手

`a6f3554` 新增 `blood_glucose_review`、`blood_lipids_review`、`blood_pressure_review` 三类可创建固定线程的任务，统一入口可创建线程的类型合计十一类。这三个任务不带 `selection`；血糖最小请求如下，血脂和血压仅替换 `task_type` 并使用各自新的 UUID：

```http
POST /api/health/v1/members/{health_member_id}/task-entries
Authorization: Bearer <业务账号 JWT>
Idempotency-Key: 0f33c524-2cd6-4e5a-89f5-815427604cff
Content-Type: application/json

{"task_type":"blood_glucose_review","client_request_id":"0f33c524-2cd6-4e5a-89f5-815427604cff"}
```

正文 UUID 与幂等头完全一致；新操作使用新 UUID，同一未知创建结果按原键回读或重放。只有返回 `entry_status=ready` 才使用实际 `agent_slug`、`thread_id` 提交文字问题；不从“血糖助手”等显示名构造 slug。后续保存 `/api/agent/runs` 返回的真实 `request_id`，按第 6.2 节恢复。三项助手只回顾当前授权的本人实测指标、追问缺失条件并解释当前有效的审核知识；无数据不能推断诊断或目标值，血糖记录回顾不等于 `glucose_plan` 已就绪。

普通咨询及三项指标助手的 Request/Run 流只公开固定进度，不提供可展示的模型候选正文。`needs_input` 是已完成运行的追问，`interrupted` 是运行中断；Run 失败、取消或旧来源失效时不能从流、缓存或相邻 Run 补出旧正文。来源重验、引用范围和断线游标按[任务恢复说明](../Yuxi-main/docs/advanced/health-task-recovery.md)实现。

### 6.4 页面修改内容

`pages/chat/index.vue` 的正式文字路径移除 `mockDelay('chat')`、固定咨询回复、关键词直接修改记忆和本地反馈写入，接真实成员、用途及会话。mock 模式仍保留演示路径。

保留现有相机、语音切换、按天布局、餐次卡与成员选择交互。消息对象补 Request、Run、业务结果和来源绑定；上下文按服务器授权来源组织，不上传本地全量聊天历史替代服务器会话。

页面隐藏、退出、账号切换或家庭切换时停止本页监听，拒绝旧响应。重新进入根据服务器会话与任务恢复，不把未确认的旧本地正文当成有效完成结果。数据保留策略区分健康正文和恢复所需 ID，不默认将全量健康内容长期缓存。

`pages/chat/history.vue` 接真实 daily-conversations 和 history；来源失效或撤权清除不再可读的正文。引用使用 Task 公开 citations 或现有 `/consultation-runs/{run_id}/citations`，不把模型正文 URL、工具日志或内部审计字段冒充已审核引用。

### 6.5 图片咨询的明确边界

`agent_request_service.py` 对固定健康后端拒绝非文字或附件消息，返回“专属咨询只支持文字，报告与照片请在健康识图复核”。虽然通用 `/api/agent/runs` 有 `image_content` 字段，也不能给 `health-consultation` 直接塞 base64 绕过边界。

现有 `uploadChatImage` 加 `chatWithImage` 不是一对已交付的健康聊天接口。食物照片应导向餐次识别、核对和确认；报告应导向报告识别。任意图片自由问答需要另外确认媒体用途、模型和公开结果协议，在此之前保留图片并说明当前可处理类型，不用通用 chatbot 悄悄替代健康角色。

## 7 当日餐单与家庭配餐

### 7.1 已有本地模块继续复用

`meal-planning.js` 已有按作用域及请求键的并发去重、同日期餐次最新任务校验和生成入口；`meal-plan-store.js` 按日期、餐次及上下文键保存本地结果，`meal-result.js` 检查逐人成员归属与份量。这些机制应继续使用，但 API 适配需要改造当前契约。本地缓存及“最新任务”检查仅约束当前客户端，不能代替服务器幂等和版本控制。

目前 `generateMealPlan` 内部 input 带本地成员健康对象和字符串请求键；返回结果要求 `passed/needs_info/conflict`、`generationId`、中文餐次、菜谱步骤、商品价格及逐人需求。团队后端返回 Task 分类和计划快照，没有同一形状。直接把后端 JSON 返回给 `normalizeMealResult()` 会被拒绝，或把专业未就绪错误地转成 passed。

### 7.2 将配餐与采购拆开

现有 `normalizeMealResult()` 要求 `products`、`memberDemands`、`memberNotes`，食材需求又必须引用带价格的 product。即使已有真实营养餐单，商城未接通也无法完成该校验。应调整为以下两个独立结果：

| 结果 | 必须字段或事实 | 不作为前置要求的内容 |
| --- | --- | --- |
| 餐单展示对象 | 服务器计划或预览 ID、日期、餐次、菜谱版本、明确参与者、逐人份量、当前业务及专业状态、来源版本 | SKU、包装价格、库存和运费 |
| 采购展示对象 | 有效采用来源、食材版本及状态、逐人或汇总可食需求、已确认库存扣减、映射状态 | 不凭空补价格；未映射时允许不可购买 |

优先让餐单正常查看，再显示“采购尚未就绪”的独立状态。不用假 SKU、0 元报价、固定 perPerson 或成人系数填满适配对象。

内部对象建议保留现有 date、meal、dishes、memberNotes，但增加 sourceId、sourceVersion、previewId/planId、professionalState、adoptionState、procurementState。这些是客户端投影字段，不要求团队立即增加同名 HTTP 字段。`generationId` 可由明确的来源 ID 和版本构成稳定标识，不能每次读取随机生成。

展示状态建议按“待补信息／预览可查看／待业务处理／当前有效／来源失效”组织。后端普通餐单草稿 `personalized=false`、`adoption_available=false` 时仍可显示草稿范围，但不能映射为“全部人群个体化检查通过”。实际专业状态与现有无新用户审核步骤的产品要求，需由业务 Owner 在服务端完成流程对齐。

### 7.3 现有餐单入口选择

| 用途 | 已有接口或类型 | 适配要求 |
| --- | --- | --- |
| 普通单日三餐草稿 | `/meal-plan-previews`、`MealPlanSpec` | 已发布 `recipe_version_id` 与份量；不接受客户端营养值 |
| 家庭普通草稿 | `/family-meal-plan-previews`、`FamilyMealPlanSpec` | `kind=family`；每餐 `participant_ids` 与逐菜 `member_portions` 对应 |
| 已批准来源的首次配餐 | `/initial-meal-plan-previews` 或 `initial_meal_preview` Task | 明确 rule code/version、专业 profile_versions、日期与三餐参与者 |
| 已保存单成员安全改版 | `/safe-meal-plan-conversations`、`safe_meal_revision` Task | 选择实际计划和批准来源，不只发一句“换一道菜” |
| 已保存家庭改版 | `/family-meal-planner` 或 `family_meal_revision` Task | 绑定真实家庭餐单，逐成员用途同意 |
| 持久保存草稿 | `POST /members/{id}/meal-plans`、`/initial-meal-plans` | 选择服务器 preview_id，带原 UUID 幂等键 |
| 正式采用与今日读取 | `/meal-plans/{id}/adopt`、`/members/{id}/adopted-plan?plan_date=...` | 按实际 review_id、版本及 profile_versions；不能把生成完成等同采用 |

首次完整计划采用三餐结构不等于每次修改都要生成三餐。初始完整生成后，单餐换菜走对应 meal_type 和 dish_index；家庭参与者接口即使要求完整三餐 allocation，也从当前服务器版本保留未修改餐次，预览并核对差异，不能重新推算其他餐次。

### 7.4 保存与读取规则

1. 当前有效计划由服务器 preview、plan 或 adoption 的持久事实拥有，客户端缓存只加快展示。
2. 页面打开先回读选定来源与当前状态；缺少结果时显示未生成，不能在正式模式创建 demo 菜谱。
3. 用户发起生成、明确修改或相关来源失效才进入分析。首页首次自动生成需要产品允许的触发契约、去重和来源选择，不能用每次 onShow 并发生成三餐代替。
4. 用户生成动作与草稿持久保存的关系需要固定下来；无论采用何种交互，都不能把一次普通查看解释成自动保存、批准或采用。
5. 持久记录来源只包含实际采用的档案、规则和上下文版本；新的无关聊天不让全部缓存失效。
6. `mealPlanKey()`、`ensureMealPlan()` 与 `todayPlan()` 使用一致的上下文指纹。目前 `ensureMealPlan()` 可将 `messages` 放入写入键，随后却调用不带这些 `messages` 的 `todayPlan()` 回读；`todayPlan()` 自身也用默认上下文算键。相关聊天改变时，即使写入成功，页面仍可能读到“尚未生成”。实施时改按服务器返回的相关来源 ID 与版本回读，并让无关聊天不影响既有餐单。
7. 历史列表恢复使用服务器分页和版本，不按旧本地菜单名称猜测来源。

### 7.5 换菜与参与者变更

普通单菜换菜使用 `/meal-plans/{id}/swap`；需要安全候选时用 `/swap-candidates` 与 `/safe-swap`，家庭对应 `/family-swap-candidates` 与 `/family-safe-swap`。按当前计划版本发送合法 UUID 和 If-Match。选错 meal_type、版本冲突或成员来源变化时重新核对，不按旧菜名寻找替换位置。

家庭参与者变化使用 `/family-participation-preview` 和 `/family-participation`。保留当餐成员调整入口；预览展示变更餐次、逐人份量与受影响状态。档案本身和其他餐次不因一个人退出本餐而删除。

### 7.6 次日提议与已购订单

当前 `saveTomorrowProposal()` 是本地存储，不等同于后端待确认提议。普通配餐 Run 可通过 `/members/{id}/meal-planner-runs/{run_id}/next-day-proposals` 登记同 Run 的权威预览；一般业务提议使用既有 next-day-proposals DTO。只有用户明确选择才登记，不能从“明天”关键词就将所有未来餐次正式采用。

当前 daily service 不自动生成正式次日餐单，家庭、初始及安全模式的次日联动仍需契约。保留缺口，不能在前端伪造日终服务。

已购餐单只更新当前饮食建议和安全提醒。`todayPlan()` 的订单快照优先级继续保留；真实已购指南缺失时展示暂不可用，不能调用 `createPlan()` 生成另一套菜谱冒充订单做法。需要真实改单时走商城正式变更流程。

## 8 拍照记餐与报告识别

### 8.1 餐照的真实流程

当前 `pages/scan/index.vue` 的 `analyze()` 只等待 `mockDelay('photo')`，预置“杂粮饭、西兰花、香煎鸡腿”等结果；保存记录写在本地。接入时沿用既有拍照、相册、逐人份量弹层，替换结果来源和保存动作。

一张或多张餐照的建议实现顺序：

1. 明确目标 `healthMemberId`、餐次、就餐时间及 `meal` 用途，读取 `/members/{id}/readiness`。无模型依赖时继续允许手动填写。
2. 用 `uni.uploadFile` 逐张提交 `POST /api/health/v1/uploads` 的 multipart `member_id`、`purpose=meal`、`file`；保存服务器 `upload_id`。本机临时路径或 Data URL 仅供本机预览，不发给模型任务 DTO。
3. `POST /api/health/v1/meal-photo-tasks` 提交同一餐的 `upload_ids`、`member_id`、`client_request_id`，以及明确 `meal_type`、`eaten_at`；Idempotency-Key 必须匹配 UUID。后端返回 202 是接收任务，不是识别完成。
4. 读取 `/vision-tasks/{task_id}` 或成员 vision 列表，区分排队、失败、候选待确认、来源失效。任务异常提供受控重试和人工记录，不将失败展示成空识别结果。
5. 读取 `/meal-drafts/{draft_id}`，显示候选菜、来源照片、不确定项。用户修改时 PATCH 携带版本、原因和 If-Match；重新计算 `/meal-drafts/{draft_id}/calculate`。
6. 用户核对餐次、菜品和逐人份量后，以 `/meal-drafts/{draft_id}/confirm` 幂等写入正式记录；回读 `diet-logs/page` 的同一记录 ID 与版本。仅此时进入正式饮食记录和后续反馈。

上传返回 ID 之后、任务未知结果之前，应保留上传 ID、原 UUID 和本次操作状态；网络失败不得重新上传同一照片并重复记餐。账号切换清掉本地健康照片引用和未授权预览。后端原图、候选和私有预览继续按当前账号授权读取。

### 8.2 报告核对与授权

报告使用相同 `/uploads`，但 `purpose=report`；随后 `/report-tasks`、`/report-extractions/{draft_id}`、PATCH、`/confirm`。候选结果只有人工核对后才能成为正式测量事实，不能把 OCR 候选直接写成疾病诊断或个人规则。

`pages/reports/index.vue`、`reports/detail.vue` 目前依赖本地 `addReport/confirmReport` 和 `getProfile()`。API 模式中应显示任务状态、可编辑候选、版本冲突、明确分享权限。报告跨成员读取和分享必须由服务端访问范围控制；仅前端开关不能构成健康授权。

### 8.3 家庭共享桌菜的缺口

当前 App 一条记录可包含 `memberIntake[]`，每个人可确认吃过菜品、粗略份量或未吃。当前健康识图 `DraftInput`、`MealPayload` 和确认路径按单个 `member_id` 保存。不能把全家桌菜绑定到第一个成员，也不能把本地整条 `memberIntake[]` 原样塞进单成员 DTO。

后端需要决定是提供同一餐次组 ID 下的多成员原子确认接口，还是为每人保存一条关联同组餐次的正式记录。两种方案都必须解决部分成功恢复、成员授权、共享照片读取、未吃成员不产生摄入、反馈按成员及餐次回读。接口定稿前，正式模式只对已核对的单成员记录开放保存；家庭桌菜页面说明保存条件，而不是生成虚假的全家成功提示。

## 9 饮食记录、反馈、记忆与趋势

### 9.1 记录来源与更正

`utils/profile.js` 目前把 `getRecords()`、`saveRecord()`、`updateRecord()` 存在本地；`pages/records/detail.vue` 可直接修改旧记录。真实模式的列表先接 `GET /api/health/v1/members/{member_id}/diet-logs/page?limit=...&offset=...`，并保留服务器 record ID、source_version 和状态。分页的 `next_offset` 按入库游标推进；过滤失效来源后，空的中间页未必是结束。

当前后端已有未确认草稿 PATCH 与确认，但这不等于已确认记录的任意字段更正接口。对于“保存后更正实际菜品和份量”的产品流程，服务端需明确版本化更正或撤销重录契约，以及旧营养估算、分析和反馈如何失效。该合同未落实前，正式模式不可只改本地数组并提示已保存。

“仅保存”和“保存并聊聊这一餐”必须复用同一个服务器记录 ID。后者可基于该记录及版本创建分析或反馈会话，不重复调用确认创建第二条记录。

### 9.2 反馈与分析

| 页面动作 | 已有服务能力 | 对齐点 |
| --- | --- | --- |
| 读取/修改当餐反馈 | `/diet-logs/{record_id}/feedback` GET/PUT | PUT 使用版本、UUID、Idempotency-Key 和 If-Match；按当前成员授权 |
| 撤回反馈 | `/diet-logs/{record_id}/feedback/revoke` | 原版本失效，不把撤回解释为“从未有过” |
| 单餐饮食分析 | `/members/{id}/diet-analysis` | 明确 record_id、source_version，不能读计划量冒充实际摄入 |
| 近 1/7/30 天分析 | `/members/{id}/diet-period-analysis` | 使用服务器确认记录；未记录日留空，未知营养不计零 |
| 选餐反馈会话 | `/diet-logs/{record_id}/feedback-conversation` | 绑定已确认记录版本，新的正文作为单餐反馈来源 |

`utils/feedback.js` 当前通过本地菜名正则统计蔬菜趋势，只能用于演示。真实趋势若要显示“是否达标”或历史目标差额，需后端提供批准规则、完整记录覆盖率和适用时间区间；现有分析师的已确认事实不自动给出这些结论。

### 9.3 长期记忆

当前 `utils/memory.js` 及聊天关键词可本地写入长期内容。团队后端提供 `/members/{id}/memory` 列表、`/memory/{id}` 历史、PATCH 和撤回。正式模式中仅当前被授权成员的长期自述在服务器保存，修改带原文来源、版本与 UUID；本餐“有点咸”属于单餐反馈，不能自动升级为永久忌口。

代成员提及和暂时状态由后端校验主体和时间语义。页面 `pages/memories/index.vue` 回读服务器版本，失效、撤权或改成员时清除旧显示。不能仅通过一个客户端撤回按钮隐藏文本而继续让 Agent 使用旧记忆。

## 10 菜谱详情与六项营养卡片

### 10.1 数值口径

当前 App `DishNutritionCard` 和 `normalizeDishNutrition()` 只接受每 100 克熟制后可食部分的结构、数值类型与来源；六项为能量、蛋白质、脂肪、碳水化合物、膳食纤维、钠。未知用 `null`，真实 0 可显示。

Agent `health_vision_types.py` 的 `NUTRIENTS` 目前仅五项：`energy_kcal`、`protein_g`、`fat_g`、`carbohydrate_g`、`sodium_mg`。`FoodInput` 不接受其他代码，`recipe_nutrients()` 也只按上述集合计算。`health_meal_plan_service.py` 放进 `dish.nutrition` 的是计划份量营养量，不是每 100 克。不能把它直接映射到菜品详情卡。

| 数据对象 | 建议来源与口径 | App 显示 |
| --- | --- | --- |
| 已发布菜谱营养 | 后端按原料与净成品重计算的每 100 克值；还须确认 `cooking_state` 与熟制可食口径，带版本与来源 | 只有口径成立时进入单道菜详情及收货后烹饪页的六项卡 |
| 计划份量营养 | 当前计划菜品的 `planned_grams` 与计算快照 | 本餐或逐人计划量，另标口径；不覆盖菜谱卡 |
| 实际摄入营养 | 用户确认的实际食品与份量的计算结果 | 饮食记录与反馈；不从计划量复制 |
| 交易时营养快照 | 支付或下单时所选版本与口径 | 已支付订单及烹饪页沿原快照 |

后端新增 `fiber_g` 时需同步 FoodInput 白名单、已发布食品版本数据、营养计算、快照 DTO、数据库存储或迁移、计算版本和测试。旧版本缺纤维返回 `null`，不补零。客户端将 Decimal 字符串做有限、非负的受控数值转换，同时保留 `source` 与 `sourceReference`；不能把格式错误的字符串或计划量换算后冒充批准每百克值。

### 10.2 做法与媒体字段

当前 `GET /api/health/v1/recipes` 返回已发布配方版本与原料数据，需核对其公开序列化结果是否足以满足 `pages/recipe/index.vue` 和 `pages/cook/index.vue` 的步骤、预计时间、图片和视频。缺字段时由菜谱发布与读取接口补充有审核来源的内容，不从 Agent 文本生成未审核的图文做法。

订单已支付后，烹饪页优先读取交易快照与对应菜谱版本。当前代码找不到指南时会调用 `createPlan()` 造演示指南；真实模式必须改为缺失状态和恢复路径，不能显示另一套菜谱。购买前详情与收货后烹饪应复用同一营养展示组件，但来源分别是当前菜谱版本与已购快照。

## 11 21 天计划与控糖

`src/services/exclusive-planning.js` 已定义 `generateExclusivePlan` 适配入口，并要求 21 天、每天三餐、同一生成 ID 及成本。Agent 的 `multi_day_plan`、`glucose_plan` 当前从 Task 入口返回 `dependency_not_ready` 和 `external_contract_required`；循环 21 次普通单日生成不能保证统一目标、版本、局部修改范围或原子保存。

后端正式多日业务契约至少应明确：计划 ID 与版本、起始日和每天参与者、逐日目标与档案/规则来源、受影响日期、部分重算、整体撤回、幂等保存、正式采用和订单独立快照。App 再把 `ensureExclusivePlan()` 映射到该权威结果。打开 21 天页应读取已保存计划；用户只改一餐时仅改该日期餐次，多日变更先预览影响并确认。

控糖另需专业确认适用与排除人群、测量条件、目标范围和异常处置。现有血糖实测读取不等于控糖方案已就绪；UI 不能仅根据自报糖尿病或一张报告显示安全控糖计划。

团队 Agent 当前八个固定健康 Agent 均属 `partial`：咨询、配餐、饮食分析、质量审核、采购，以及血糖、血脂、血压记录回顾。`health-profile` 是业务能力，不能算作第九个固定 Agent。已有工程任务闭环不等于正式专业数据和全人群安全规则完成。客户端可显示明确的能力范围和缺项，不把“未就绪”静默退化为成人演示菜单；血糖回顾也不能称为控糖计划。

## 12 商城、地址、支付与配送

### 12.1 三个服务各自拥有的事实

| 事实 | Owner | 客户端处理 |
| --- | --- | --- |
| 当前成员、可食需求、营养安全、已采用计划 | Agent 健康业务服务 | 读取实际被授权的来源和版本 |
| SKU、包装、库存、报价、运费、地址可达性 | 商城服务 | 使用商城当前目录和有效报价；不用营养食材名猜商品 |
| 订单、支付、退款、配送、收货 | 商城交易服务 | 以交易查询及确认快照为准 |

Agent 当前采购服务返回可食克数，`sku_candidates=[]`，`purchase_available=false`、`order_available=false`。这些事实不能填成空价格或“已可购买”。商城适配要建立食品/菜谱版本与 SKU/包装版本的显式映射，跨生熟状态的采购毛重换算必须有批准依据。供应商只收采购履约必要字段，不发送家庭健康档案。

Merge 中已有 App 的 `commerce-client.js`、`commerce-integration.js` 与 `shop` 的本地交易增量，可用作受控提取来源。它先以 Agent 业务 JWT 调用 `/api/v1/commerce/session/exchange`，将 Agent 外部账号关联到商城账号；不能按昵称或数字 ID 猜测同一会员。该本地增量尚非团队 main 的已部署能力，实施前需对当前 `HealthSwarm/shop` 及 Agent 微信登录分支进行基线、迁移和接口重审，避免把旧源码覆盖新工作。

### 12.2 小程序修改方式

真实商城模式在入口集中注册地址、商品、报价、订单、支付状态和售后适配；逐页打开 `navigation.js` 白名单。现有 `service.selectedAddress()` 为同步读取，但真实商城地址是异步服务器数据；页面 `onShow`、报价指纹和结算弹层需改为明确 loading/error 和已加载快照，不能把 Promise 当地址对象。

生成餐单、生成食材需求、挑选商品、确认有效报价、创建订单是不同动作。报价受成员、菜谱、SKU、数量、地址和配送时段变化影响；变化后重新核对。写入时保留原交易幂等键和未知结果查询，避免重复下单或重复支付。付款成功以已验证网关回调和订单当前事实为准；微信支付界面返回成功只触发查询，不单方面把本地订单置为 paid。

21 天计划仍有退款规则待定。Merge 的正式计划报价和下单返回关闭状态 `purchase_enabled=false`、`refund_rules_status=pending`，对应实现拒绝新购买。App 可展示和保存计划草稿，不能把演示价、旧商城“不退款”规则或客户端按钮状态当成正式支付资格。

已购批次地址、暂停、取消、退款和售后按交易服务已有正式动作接入。对当前只在本地模拟的能力逐项确认服务端是否已交付；没有服务器动作时页面明确不可操作，不写本地成功状态。

## 13 语音输入与音频协议

现有 `chat-voice.js` 在微信侧申请 `scope.record`，采集 16 kHz、单声道、PCM，保存录音，并调用 `transcribeVoice` 适配器。团队健康路由当前未提供转写接口，也未有处理方、授权目的、时长/大小、费用、内容保留及失败分类的完整公开契约。

上线转写前，后端需确定上传路径、音频格式和时长限制、用户及成员授权、处理方和政策版本、转写结果的幂等键、删除/保留规则。客户端用真实文件上传，成功返回文字后仍由用户确认或发送普通文字咨询；录音不能直接作为健康角色附件绕过文字边界。

微信允许/拒绝、授权读取失败、运行环境失败和语音服务失败分别提示。录音取消不提交，识别失败保留可重试的当前录音；账号切换或用途撤回清掉未授权本地音频引用。仅 H5 编译或录音动画正常不构成真机转写验收。

## 14 实施顺序与可交付切片

每个切片只在对应后端接口、数据来源和验证材料同时具备时开放正式页面。建议以本人链路验证为起点，同时继续为家庭全成员功能落实授权与适配，避免先实现一套只支持成人本人的最终产品。

| 阶段 | 源码修改 | 完成条件 |
| --- | --- | --- |
| A 登录与协议 | 合入微信身份路由/迁移；扩展 App `request.js`、会话修订与错误解析 | 真实微信身份可获得业务 JWT；同账号重登、跨账号、401/403、超时重试正确 |
| B 家庭档案 | App 正式档案适配；本人家庭/健康成员关联；授权与用途同意 | 后端回读同一个家庭、本人档案和关联 ID；未授权成员不能被读出 |
| C 咨询 | App 聊天与按天历史；统一任务、Request/Run 查询、引用 | 输入、排队、追问、完成、失败、断线恢复和撤权均可验证 |
| D 单日餐单 | App 餐单投影与持久化；Agent 菜谱来源、参与者、版本和专业状态 | 打开不重新生成；一餐修改只影响该餐；未知/冲突不展示安全通过 |
| E 识图与记录 | 上传、任务、草稿修订、人工确认、记录分页、反馈 | 图片候选不能跳过确认；记录只保存一次；失败可手动记录 |
| F 菜品详情 | 后端纤维和已发布菜谱展示数据；App 每百克转换与烹饪快照 | 六项数值和来源可核；缺值为 null；已购快照不变化 |
| G 商城 | 精选接入 Merge 的当前有效交易模块，完成商品映射和支付联调 | SKU/报价/订单/支付回执为权威；21 天购买继续按政策关闭 |
| H 多日、控糖、语音 | 后端合同、规则与服务完成后接 App | 对应业务真实可用，独立联调和真机验收通过 |

阶段 B 与 C 可以在独立测试环境协同推进，但发布入口必须满足 A。阶段 D 可先展示普通草稿，但不能声称完成全人群专业适配。阶段 G 不阻塞单日计划查看，也不能反过来让商品价格成为餐单必填字段。

阶段 A 的本地微信路由补丁仅证明已准备源码，须在共享分支上复核、完成 business 12→13 迁移、实际 HTTP/PG 及微信真机验证，并记录部署版本后才算完成。B/C 可用合成账号、成员和隔离服务并行准备；指标回顾入口属于 C 的独立任务类型，不改变 H 中控糖方案仍未就绪的判断。D 的普通餐单草稿展示与专业正式采用分开验收。G/H 的交易和多日依赖不阻塞已有普通记录或单日草稿读取。

### 14.1 服务端剩余交付

| 优先级 | 责任模块 | 当前缺口与完成证据 |
| --- | --- | --- |
| P0 | 微信认证与存储 | GitHub `main` 尚无微信路由；本地候选补丁需共享、迁移审查、真实 code/绑定冲突/重放/跨账号负例和真机验收。AppID、服务端密钥和合法域名由实际运行环境提供 |
| P0 | API 部署与联调 | 固定部署提交、Schema、API/Worker 镜像、公开地址和 OpenAPI；提供合成账号、成员样例及错误/幂等/版本头实测，不把静态源码等同运行服务 |
| P1 | 家庭档案与授权 | 本人关联已存在；代成员代理依据、字段/用途/期限、模型同意以及不耐受/状态/默认设置的无损映射仍需合同和跨成员 HTTP/PG 负例 |
| P1 | 专业规则与全人群 | 审核的适用和排除来源、过敏及医嘱冲突策略、版本和专业状态；普通草稿可以明确显示范围，不能称为个体化安全通过，也不增用户人工审核页 |
| P1 | 饮食记录 | 家庭桌菜多人确认、同餐关联、部分成功恢复以及已确认记录的版本化更正/撤销；旧计算和反馈失效须由业务服务持久处理 |
| P1 | 菜谱与营养数据 | 有授权来源的纤维、熟制每百克净成品口径、图文做法与发布版本；旧版缺值为 `null`，计划量、实际摄入和订单快照各自保留 |
| P2 | 多日、商城和语音 | 多日/控糖规则、商城 SKU/报价/支付沙箱、转写处理方与授权合同分别就绪后分功能开发；未就绪时显示真实不可用状态 |

实施团队应对每个切片提交精确文件清单，说明接口 DTO、版本/幂等、回读证据和未就绪项。当前根目录有未提交和未纳入 Git 的工作；禁止整体覆盖、全量暂存或将 `.codex` 中的集成副本直接替换团队 main。

## 15 验收矩阵

### 15.1 契约与单元测试

| 场景 | 应验证的业务结果 |
| --- | --- |
| 错误形状 | 顶层 `code`、FastAPI `detail` 字符串/数组、401/403/409/410/422/429/503 均转为正确页面状态 |
| 请求幂等 | 相同 UUID 和正文重试只得到同一结果；相同键不同正文被拒绝；无幂等支持的创建先回读 |
| 版本编辑 | 旧 `If-Match` 得到 409，客户端不自动覆盖新版本；正确版本只更新目标记录 |
| 身份隔离 | 登录、退出、同账号换 token、跨账号、跨家庭迟到响应不能污染页面或清除新会话 |
| 成员映射 | 本地数字 ID、家庭 source_member_id、健康 member_id 明确分离；不能按昵称建立映射 |
| 未知值 | 空字符串、null、零值、没有数据和已确认无不互相混淆 |
| 餐单来源 | 读页面不触发生成；仅相关来源变更需复核；错误配方版本/参与者被拒绝 |
| 异步状态 | `ready`、`queued`、`running`、`needs_input`、`completed`、`cancelled`、`interrupted` 各有独立 UI |
| 指标助手 | 三种 `task_type` 均无 `selection`，入口键与实际 Request ID 分离；同 Run 回读授权指标和有效引用，无数据追问，不产生控糖计划 |
| 部署版本 | 源码提交、运行环境镜像、business/health Schema 与 OpenAPI 一致；部署不一致时不能把联调结果归到当前源码 |
| 计量口径 | 每百克菜谱、计划份量、实际摄入、订单快照不混用；缺纤维返回 null |
| 产品范围 | 儿童和孕产相关自述按现有信息处理；未知不猜测；没有新增阶段建档或用户审核页 |

App 的 `pnpm test` 应补 `request`、健康 DTO 投影、任务恢复、成员关联、餐单持久化和媒体状态的针对性测试。现有 mock 测试继续覆盖交互，但不能用 mock 通过证明真实服务可用。按改动阶段分别运行 `pnpm build:h5` 与 `pnpm build:mp-weixin`，检查构建出的请求域名、AppID、页面注册及相关 `mp-weixin` 产物。

Agent 按受影响模块运行对应 unit、真实 HTTP integration 和需要的 Worker/PG E2E；数据库迁移需在现有数据副本上验证幂等与旧版本升级。HTTP 200 不等于持久成功，需回读所属 PostgreSQL 记录、Request、Run、最终 Message、图片候选和业务快照。商城对订单、支付回调、退款、售后及库存使用独立交易库和网关沙箱验证。

### 15.2 端到端使用场景

1. 新用户微信登录，选择或创建家庭，建档后刷新 App，仍读取同一服务器成员及确认版本。
2. 本人授权健康用途并关联正式档案，咨询得到当前 Request/Run 和有效引用；中途断网重新进入仍可查询原任务。
3. 家庭中儿童、成年人和资料缺失成员调整同一餐；无年龄身份整餐拦截，缺专业依据时说明范围和需要的信息，已知过敏或医嘱冲突仍阻断不安全结果。
4. 单餐换菜后只改变目标日期餐次；打开餐单多次不触发重复生成；已购订单菜品、价格和配送快照不变。
5. 上传餐照、纠错、计算、确认，得到一条正式记录；“保存并聊聊这一餐”引用同一记录；报告识别保留核对状态。
6. 跨账号或跨家庭打开旧健康记录、图片、咨询与订单均拒绝；请求失败显示真实错误，不展示其他账号缓存。
7. 菜品卡显示六项每百克营养，缺来源和缺纤维显示暂无数据；烹饪页随当前菜品切换，收货后读取交易快照。
8. 无 SKU 或 21 天退款政策未定时，可查看允许查看的计划和食材需求，但不可生成虚假报价或真实支付。
9. 微信开发者工具与 iOS、Android 真机核对 AppID、HTTPS 合法域名、真实微信 code、图片上传、录音授权和页面恢复；真实支付及生产模型另行验收。

### 15.3 本次文档的验证边界

本次完成的是静态源码和 DTO 对照。未启动 Agent、PostgreSQL、Redis、Worker、商城或微信开发者工具；未运行本次文档所描述的端到端流程。上述矩阵是实施后的验收要求，不是已通过结果。

## 16 源码定位与复核索引

### 16.1 小程序源码

| 主题 | 源码入口 |
| --- | --- |
| 真实模式与服务注册 | [config.js](../../../src/services/config.js)、[index.js](../../../src/services/index.js)、[navigation.js](../../../src/services/navigation.js) |
| 请求与微信会话 | [request.js](../../../src/services/request.js)、[wechat-auth-client.js](../../../src/services/wechat-auth-client.js)、[session.js](../../../src/services/session.js) |
| 家庭建档 | [account/index.vue](../../../src/pages/account/index.vue)、[family-onboarding.js](../../../src/services/family-onboarding.js)、[profile.js](../../../src/utils/profile.js) |
| AI 聊天与媒体 | [chat/index.vue](../../../src/pages/chat/index.vue)、[chat-images.js](../../../src/services/chat-images.js)、[chat-voice.js](../../../src/services/chat-voice.js) |
| 配餐与计划 | [meal-planning.js](../../../src/services/meal-planning.js)、[meal-result.js](../../../src/utils/meal-result.js)、[meal-plan-store.js](../../../src/utils/meal-plan-store.js)、[meal-state.js](../../../src/utils/meal-state.js) |
| 识图、记录、反馈 | [scan/index.vue](../../../src/pages/scan/index.vue)、[feedback.js](../../../src/utils/feedback.js)、[records/detail.vue](../../../src/pages/records/detail.vue) |
| 六项营养 | [dish-nutrition.js](../../../src/utils/dish-nutrition.js)、[菜品营养字段与后端存储契约](../../../docs/菜品营养字段与后端存储契约.md) |
| 多日与订单 | [exclusive-planning.js](../../../src/services/exclusive-planning.js)、[shop/index.vue](../../../src/pages/shop/index.vue)、[orders.js](../../../src/utils/orders.js) |

### 16.2 团队 Agent 源码

| 主题 | 源码入口 |
| --- | --- |
| 路由注册、认证、家庭 | [routers/__init__.py](../Yuxi-main/backend/server/routers/__init__.py)、[auth_router.py](../Yuxi-main/backend/server/routers/auth_router.py)、[family_router.py](../Yuxi-main/backend/server/routers/family_router.py) |
| 家庭字段与成员关联 | [family_schemas.py](../Yuxi-main/backend/package/yuxi/services/family_schemas.py)、[health_family_profile_service.py](../Yuxi-main/backend/package/yuxi/services/health_family_profile_service.py) |
| 健康业务路由 | [health_vision_router.py](../Yuxi-main/backend/server/routers/health_vision_router.py)、[health_vision_types.py](../Yuxi-main/backend/package/yuxi/services/health_vision_types.py) |
| 任务和状态 | [health_task_types.py](../Yuxi-main/backend/package/yuxi/services/health_task_types.py)、[health_task_service.py](../Yuxi-main/backend/package/yuxi/services/health_task_service.py)、[agent_router.py](../Yuxi-main/backend/server/routers/agent_router.py)、[任务恢复说明](../Yuxi-main/docs/advanced/health-task-recovery.md) |
| 配餐与营养 | [health_meal_plan_types.py](../Yuxi-main/backend/package/yuxi/services/health_meal_plan_types.py)、[health_family_meal_plan_types.py](../Yuxi-main/backend/package/yuxi/services/health_family_meal_plan_types.py)、[health_nutrition_service.py](../Yuxi-main/backend/package/yuxi/services/health_nutrition_service.py)、[health_meal_plan_service.py](../Yuxi-main/backend/package/yuxi/services/health_meal_plan_service.py) |
| 采购、角色和未就绪能力 | [health_purchase_service.py](../Yuxi-main/backend/package/yuxi/services/health_purchase_service.py)、[health_agent_roles.py](../Yuxi-main/backend/package/yuxi/services/health_agent_roles.py) |
| 小程序对接参考 | [Agent 交付与待对接](家庭营养师-Agent交付与待对接.md)、[miniapp 营养客户端](../miniapp/src/services/nutrition-client.js) |

### 16.3 本地整合副本与联调前核对

Merge 中已有[整合记录](../../../.codex/healthswarm-merge-20261012/MERGE-20261012.md)、微信路由 `agent/Yuxi-main/backend/server/routers/wechat_auth_router.py`、微信身份迁移 `v013_wechat_identity.py`、App `commerce-client.js` 和商城 `shop/`。这些文件只作为本地候选来源。合入前按团队 main 当前提交重新比较、执行精确文件清单和迁移冲突检查；不得把本地整合副本的测试通过或客户端编译通过当作当前团队主线及生产已验收。

### 16.4 实施前的动态源码复核

团队 Agent 的固定 Git 基线见第 1 节。小程序工作区没有本次可用的提交基线，且本次写作期间 `meal-planning.js`、`meal-state.js` 已发生更新，因此不将一次性文件摘要视为实施依据。开始编码前先重新读取第 16.1 节的服务入口，重点核对 `ensureMealPlan()`、`mealPlanKey()`、`todayPlan()` 的读写键、在途任务校验与已购快照分支，以及请求层的会话和错误处理。逐项与本文的源码事实比较，若有变化先更新受影响的修改清单与验收点；保留并行开发的现有修改。

## 17 当前实施记录

本节记录实际源码变更与验证结果；前文尚未实施的设计和验收要求仍按原意使用。

| 切片 | 已修改 | 尚待验证或交付 |
| --- | --- | --- |
| A 请求协议 | App 请求层增加受控请求头、会话修订检查、健康业务错误字段解析；同账号重登旧请求不清新会话 | 真实服务 401/403/409、网络未知写入与真机网络行为 |
| A 微信登录 | 从本地整合副本精选合入 Agent 微信路由、服务、身份 repository、业务迁移、模型、配置及测试；主线其他文件保持原结构 | 数据库迁移和真实 HTTP 集成、微信 AppID/AppSecret 配置、开发者工具及真机登录 |
| B 本人关联与诊断 | App 账号页支持显式读取和选择健康成员、创建本人健康成员、确认两个 ID 后建立关联并回读；未知创建结果阻止直接重复提交。选定成员后可读取 `/capabilities` 和 `/readiness`，校验返回成员 ID，并按服务端状态展示咨询、单日配餐、三项指标回顾、控糖与多日入口；区分授权、处理同意、选择、运行依赖、专业资料与外部契约缺口 | 真实家庭/健康成员数据及授权隔离、代成员关联合同、用途同意和正式页面解锁；该展示不代表可提交或已获专业批准 |
| C 咨询与指标回顾 | App 账号页可进入独立真实健康助手页。该页核对当前本人成员与就绪状态，处理咨询用途的明确同意，以独立 UUID 创建 `task-entries` 和提交 `/api/agent/runs`；只从同一 `/api/health/v1/tasks/{request_id}` 回读咨询或指标结果。仅保存成员、线程和请求等不含正文的恢复指针；隐藏页面清除正文；未知提交用同一请求键核对，轮询有界，账号/成员错配及拒读清除投影 | 尚未接入 SSE 过程流、按天历史列表、图片及餐单业务结果卡片；需要同一部署版本的真实 HTTP/PG、断网恢复、撤权、微信真机和模型/资料引用验收。当前独立页不宣称替代原演示聊天页 |

App 本轮已运行 `pnpm test`（168 项通过）、`pnpm build:mp-weixin` 和 `pnpm build:h5`（均通过）。这些结果只证明本地模拟和编译。Agent 已通过 Python 语法编译、相关文件 Ruff lint/format、微信登录 10 项 unit、工程契约主校验和 `git diff --check`。工程契约校验器的 63 项自测有 1 项因 Windows 缺少创建 symlink 权限而报错；迁移流程单测在 Windows 收集时依赖 POSIX `fcntl` 而无法运行。本地 Compose 缺少必填运行配置，真实 HTTP 和 PostgreSQL 迁移仍需在隔离 Linux 环境验证。未运行的微信真机与支付验收均不标记为通过。
