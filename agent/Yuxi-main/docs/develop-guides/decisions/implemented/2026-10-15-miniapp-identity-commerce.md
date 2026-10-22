# 小程序身份与商城会员关联

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/wechat_login_service.py

2026-10-21更新：前台登录及首次会员选择由[统一微信主线](2026-10-21-miniapp-single-mainline.md)取代。当前正式客户端仅微信登录，采购时空对象自动复用或建立会员；本文其余身份稳定性与历史发布证据保留。

## 问题
小程序需要可验证的普通业务账号和当前家庭上下文。商城会员与 Agent 用户属于独立账号域，账号编号相同不能证明同一身份。缺失微信路由使登录配置查询返回 404。

## 决策
### 实现方案
微信路由复用业务 JWT、普通用户权限与家庭 repository；只从固定微信 HTTPS 服务交换临时 code。身份摘要通过 PostgreSQL 唯一约束和事务锁关联用户。business 迁移从 12 升到 13，仅新增微信关联表；API 与 Worker 使用同一版本，由 storage-migrator 执行迁移。

商城服务器向固定会话地址验证业务 Bearer token，以稳定部署来源和已验证 UID 建立会员映射。首次进入需要验证原商城会员或明确选择创建新会员；已关联后显式提交凭据也必须认证并匹配原绑定。小程序采用会话切换和迟到响应保护，返回的 Agent 账号必须匹配当前账号。原商城密码及历史数据不因关联而改变。

## 替代方案
客户端直接声明商城会员编号不能证明所有权。按名称自动合并会误关联账号。默认创建新会员会令已有会员误以为购物车与订单丢失，因此首次关联采用显式选择。

## 后果

健康域 24、25 升级到 26 与本身份模块的兼容由[健康流程升级与身份整合的迁移兼容](./2026-10-16-health-schema-identity-sync.md)维护。
生产默认禁用微信登录。启用需要 WECHAT_LOGIN_ENABLED=true、WECHAT_APP_ID、WECHAT_APP_SECRET；注册新 Agent 普通用户另需 WECHAT_AUTO_REGISTER=true 和有效的 WECHAT_USER_DEPARTMENT_ID。密钥仅由部署环境注入，不进入前端或 Git。登录与密码接口共用限流。

商城配置 SHOP_AGENT_SESSION_URL 指向受信 Agent 的 /api/auth/wechat/session，使用 HTTPS，或仅同机回环 HTTP；SHOP_AGENT_CLIENT_ID 是固定来源标识，部署后不要随意更换。App 使用 API 模式，在原业务会话上调用商城 exchange；mock 模式保持原商城会员登录供本地联调。正式小程序需要 HTTPS 合法域名及对应 AppID。

身份关联不自动创建家庭、不授予健康数据访问权，也不代表真实支付完成。生产迁移前备份数据库和 compose；如果微信尚未启用且新关联表为空，可在停止新 API/worker 后保留新增表、将 business 版本恢复为原值并恢复旧镜像。存在新绑定数据时先审查再回滚，禁止直接丢弃关联表或覆盖业务库。

## 验证
- Agent：隔离 PostgreSQL/Redis，运行 `python -m pytest test/unit/services/test_wechat_login.py test/unit/services/test_storage_migration.py test/integration/api/test_wechat_login_http.py -q`，56 项通过。覆盖真实 HTTP/JWT、迁移、锁定/管理员拒绝、配置禁用和限流；微信外部服务使用合成响应。
- 跨服务：独立商城 PostgreSQL、真实 Agent HTTP/JWT、4 个 PHP worker，运行 `php tests/integration/MiniappRouteTest.php` 和 `python3 tests/integration/AgentCommerceHttpTest.py`，通过。数据库回读证明密码、购物车、地址和订单指纹不变；错误凭据、已关联账号冲突被拒绝；4 个并发创建仅得到 1 个会员。
- App：`node --test tests/*.test.mjs`，206 项通过；API 模式 H5 和 mp-weixin 构建通过。构建使用保留的示例域名，属于隔离验收产物，不可直接发布给用户。
- 独立 Reviewer 已复查完整改动及已映射身份的显式凭据修复，无剩余阻塞问题。
- 真实微信配置缺失，微信供应商实连、开发者工具及真机登录验收尚未完成。生产 readiness 只证明服务就绪，不替代真实微信与业务验收。
- 工程契约检查通过；检查器自测在 Linux 上 63 项通过（Windows 的符号链接权限用例受限）。docs build 未运行：本地未安装 VitePress 依赖。两个改动工作区的 `git diff --check` 通过。
- 生产增量已部署：API/Worker 同镜像，business 13，knowledge 2 和 health 24 不变；ready 200，微信 config 200 且 available=false，无会话 401，禁用登录 503，商城无效 Bearer 401，商品及后台页 200。迁移前后数据库指纹比对证明原账号及商城业务表不变；家庭共享源码摘要一致。公网直连检查通过。
