# 商城线上源码回存与H5更新边界

2026-10-22，GitHub main 的商城缺少生产 `user-ingredient-20261022-193645` 已运行的12项代码/迁移变化。本次按逐文件核对的白名单回存，不复制生产环境、插件安装状态、用户数据或旧版商城小程序源码。

回存包括：标准食材目录的只读查询与SKU候选过滤；经过后端验证的业务账号接入商城；账号关联、最近接入渠道和微信验证时间记录；管理端用户列表、详情与检索；`20261022_miniapp_user_access.sql` 及迁移器登记。业务账号可接入商城，不代表持有微信支付身份，支付继续要求真实微信认证及完整AppID/OpenID。

迁移为历史记录保留空账号标识、未知登录渠道和零时间，不从既有绑定、支付OpenID或历史数据推断微信登录。生产已执行该迁移且SQL SHA256与迁移记录一致，本次回存和H5更新不重复运行生产迁移，不重启PHP/API/Worker。

独立PostgreSQL验证覆盖：旧Schema升级、重复迁移及校验和拒绝；历史渠道保持未知；业务/微信/支付身份区分、账号复用和冲突拒绝；原密码不变、不记录Bearer；别名和字面搜索、分页游标绑定；待审核/失效映射、库存和未发布商品不能作为采购候选。执行 `PostgresqlDeploymentMigrationTest.php`、`IngredientCatalogServiceTest.php`、`MiniappUserAccessTest.php`、`RuntimePatchTest.php`、`VersionedRouteTest.php`、`MiniappRouteTest.php`，以及9项PHP语法检查和两份后台JS语法检查。基础安装SQL的固定ID样例需要在隔离库推进用户序列；测试已显式准备该夹具。首次相关失败及Windows行尾导致的补丁哈希失败日志保留，规范测试源码为Git的LF文本后复跑通过。未以这些合成协议测试冒称真实微信支付验收。

当前生产云处理政策、专业规则/菜谱和食材SKU映射审核等条件仍需独立完成。本次H5继续使用指定站点测试账号入口、真实同源API及 `/family-app/` 资源前缀，不能使用关闭测试入口且资源前缀为 `/` 的历史构建包直接覆盖。
