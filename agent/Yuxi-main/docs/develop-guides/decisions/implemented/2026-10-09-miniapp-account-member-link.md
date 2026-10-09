# 小程序账号登录与本人成员关联

状态：implemented
类型：feature
Owner：backend/package/yuxi/repositories/health_family_profile_repository.py

## 问题

小程序原型以本机演示会话和数字成员 ID 展示家庭，无法读取现有 Yuxi 账号的家庭关系及健康权限。家庭档案成员与健康成员分别拥有 UUID；按姓名或原型 ID 推断关联会错误绑定身份。用户确认先使用现有账号密码完成接入。

## 决策

### 实现方案

`agent/miniapp/` 提供账号登录和本人成员接入页面，复用 Yuxi 现有认证、家庭及健康业务接口。服务端本人关联的语义 Owner 是现有 `HealthFamilyProfileRepository`；客户端请求、会话和页面状态由 miniapp services 与页面持有。登录取得 `/api/auth/token` 表单返回的 Bearer，持久会话恢复经 `/api/auth/me` 验证。家庭和健康 API 每次执行当前用户及部门、字段权限校验。

页面读取真实家庭及可授权健康成员，仅显示服务端认定的本人关系，以及当前账号拥有并具备 `profile_view`、`profile_edit` 的本人健康对象作为候选。用户选择双方并明确确认后调用既有 `family-profile-link`，再回读唯一映射和基础档案状态／确认版本。唯一性、不可改绑及本人权限仍由原业务服务与 PostgreSQL 校验。登录和普通读取不创建健康对象、授权或模型处理同意。

客户端只持久化 token、uid 和显示名，家庭、档案、映射和选择保留在页面内存。15秒请求预算、401清会话、退出和账号切换失效旧请求；登录／恢复在网络响应后及 await 续体重验会话版本，避免已退出凭据恢复。页面用会话订阅与独立请求版本清除旧账号及旧选择结果。错误显示原业务状态，没有示例成员降级。

源码、配置、依赖、测试及输出均位于 `agent/` 内。H5只读复用原型组件的物理路径；微信编译用工程内虚拟 SFC ID、只读加载同一组件，满足 uni-app 分块路径要求。原 `App/` 页面保持原型实现。H5同源 `/api` 代理默认开发主服务；微信端读取构建指定的 HTTPS API 地址，未配置明确失败。AppID仅注入本工程生成的微信项目配置，原型及源 manifest 不写入实际配置。

## 替代方案

直接修改根 `App/` 与开发目录边界冲突，整体复制原型引入重复维护；接入模块只复用现有组件及样式。H5统一采用虚拟 SFC 会使 Vite 依赖预扫描读取不存在的文件，两个编译目标各用所需读取方式。微信 code 登录需要新的可信身份交换与服务端凭据配置，保留为后续范围；商城凭据和客户端提交的 openid 不作为 Yuxi 登录证明。

## 后果

本入口覆盖已有账号的身份和本人关联工程，账号需要所属部门及既有本人健康对象。无家庭／对象／字段权限时页面显示真实准备条件，管理员身份不扩大健康授权。完整专业档案、其他成员授权、微信身份、原型业务页面接入、咨询和餐单小程序页面、公开 HTTPS 与真机验收继续。Supabase、Yuxi 与商城的数据归属维持现有边界。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 真实会话及服务端成员，不以原型身份代替 | token复活、账号串读、错误隐藏 | miniapp nutrition-client、Yuxi auth/family/health | 13客户端和5投影 unit；12真实HTTP场景及独立PG核对 | 错误密码、401、无部门、退出／切账号后的晚到回调与微任务续体 | Passed |
| 明确本人关联保持唯一的双方UUID | 姓名猜测、自动建档、改绑或越权 | health_family_profile_repository.py | 真实客户端HTTP；PG逐条核对link、actor、来源、grants和consents | 他人source/health、未确认、重复、冲突、撤权；授权与同意保持基线 | Passed |
| 页面消费真实接口与持久会话恢复 | 孤立SDK或UI缓存旧账号资料 | miniapp两页及uni.request | 隔离H5实际登录、明确关联、基础v2回读、刷新恢复、退出及第二账号；375px视口无横向溢出 | 旧账号家庭和健康对象在切账号后不可见 | Passed |
| 两编译目标消费同一只读组件 | H5扫描失败或微信相对分块越界 | miniapp vite.config.js | H5/微信构建，H5实际组件HTTP200；独立合成AppID输出验证，源码manifest不变 | 虚拟SFC在H5的失败原因为depscan路径，按目标读取后重建通过 | Passed |
| 验收writer在失败时拒绝通过证据 | Node失败子测仍写passed:true | account-http.test.mjs | 真实HTTP部门断言负控exit1、证据passed=false；最终正确夹具重跑和精确cleanup | running先写false，各子测成功才计入；不能以parent signal证明通过 | Passed |
| 页面在注入延迟和恢复故障时仍正确 | epoch guard失效或保存响应丢失 | miniapp页面 | 源码审阅；客户端边界已有unit，页面未注入故障 | 页面延迟／丢响应专项注入 | Inspected；故障注入Not run |
| 微信端正式身份及部署可用 | 把编译产物当真机验收 | 后续微信身份与部署Owner | AppID／域名真实配置、微信开发者工具及设备未提供 | code登录、真实HTTPS请求及真机 | Not run |

HTTP和浏览器使用内部网络隔离数据库及合成账号，未调用云模型或部署主服务；PG模型配置摘要保持不变且AgentRun为0。只清理夹具自己的账号、关系、映射、授权及审计，最终回读无所属残留。页面独立审阅、相关工程契约与补丁检查按交付证据收敛；测试命令由 miniapp package 与账号HTTP夹具持有。
