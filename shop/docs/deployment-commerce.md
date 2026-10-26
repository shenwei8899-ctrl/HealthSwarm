# 商城与 Vue 3 小程序部署

本轮源码包括商城会员登录、实际商品/SKU/图片、购物车、地址、全国配送及停用规则、服务端核价、普通订单、支付结果、后台发货、收货与售后。本餐页面读取会员已有的服务端菜单；Excel 商品导入不会生成营养建议、菜谱或个人份量。

## 源码和业务数据

仓库 App 为 Vue 3 小程序，shop 为 Healthflow2 后端。addons/shop/uniapp 是旧 Vue 2 项目，不用于本轮小程序发布。App 构建参数见 [小程序配置](../../App/docs/commerce-deployment.md)。

Git 不保存实际 .env、数据库备份/卷、用户上传图片、runtime 会话、商户私钥或本机夹具。Excel 导入的商品记录和 public/uploads 必须单独迁移，或在服务器重新导入。恢复数据前备份并核对会员、密码哈希、SKU、地址、订单和身份映射；不得用测试初始化脚本替代原会员数据。不要执行历史 reset/seed SQL 来升级生产库。

## 干净构建

生产 PHP 镜像使用 composer.lock 中的固定依赖，显式复制 vendor 和 thinkphp。Composer post-install/update 将版本化 PostgreSQL 驱动修补应用到已知上游文件，遇到未知版本会中止。升级框架时同时审查 patches/thinkphp，而不是手工修改被 Git 忽略的框架。

Nginx 镜像使用 package-lock.json 安装依赖，通过 Grunt 生成 public/assets/libs。已有压缩 JS/CSS 和动态加载模块的依赖、字体会一起进入镜像。Docker context 排除 outputs、.codex、运行数据和本机依赖。

将 .env.production.example 复制为 .env.production，设置数据库、管理账号、随机主密钥、HTTPS 域名、证书及后台允许网段后执行：

```sh
docker compose --env-file .env.production -f docker-compose.production.yml build
docker compose --env-file .env.production -f docker-compose.production.yml up -d
```

此命令必须在目标服务器环境执行，源码推送不代表已经部署。生产 entrypoint 执行幂等结构升级；新增 004_supplier_catalog_import_fields.sql 仅补导入字段，005_wechat_payment_lifecycle.sql 仅补支付映射/流水表。数据库卷和上传卷须保留。额外运行 prepare-miniapp.php 可在空地区字典时导入原行政区划；它不创建会员或商品。

PostgreSQL 商城插件安装与升级还会执行 `database/postgresql/migrations/20261019_001_agent_meal_source.sql` 和 `20261021_commerce_catalog_review.sql`，在同一事务记录版本及校验和；已执行文件不可改写。这两份迁移包含 Agent 采购来源证明字段和目录审核结构，不能仅复制 PHP 服务而遗漏 SQL 文件。新增对象使用幂等 DDL 保留业务记录，历史数据重置脚本不进入此自动升级链。

`SHOP_AGENT_SESSION_URL` 指向固定可信的 Agent `/api/auth/wechat/session` HTTPS 地址，`SHOP_AGENT_CLIENT_ID` 使用与 Agent 一致的稳定标识。正式 Compose 将它们注入 PHP 和调度进程；不要把 bearer、AppSecret 或 client secret 放进前端。缺少这些配置时，业务身份交换与带来源证明的采购不可用。先在独立环境验证身份交换、无效凭证拒绝及来源回查，再接入正式客户端。

## 商品导入与配送

小程序手机号绑定使用独立的 `SHOP_WECHAT_PHONE_ENABLED`、`SHOP_WECHAT_PHONE_APP_ID` 和 `SHOP_WECHAT_PHONE_APP_SECRET`。仅在后台配置完成且 AppID 与小程序一致后启用；AppSecret 保存在部署环境中。生产 Compose 将这三个配置传给 PHP 和调度进程。安装与升级通过 Migrator 执行 `20261023_wechat_phone.sql`，保留版本校验和；已部署数据库应先核对两张手机号表，再运行幂等升级。缺少配置时接口明确返回未配置状态，不接受客户端直接提交手机号作为微信验证结果。

后台“商品与食材库”导入并确认供应商 Excel。发布正常、可见且有可售库存的 SKU 才会进入小程序商品目录；图片需要在正式 SHOP_MEDIA_BASE_URL 对应域名可访问。导入与上传需要 GD、fileinfo、mbstring、zip 等运行扩展，生产镜像及 12 MiB 上传限制已配置。

地区字典可选择的地区和实际配送范围分别管理。检查后显式配置全国省级覆盖：

```sh
php scripts/configure-nationwide-delivery.php
php scripts/configure-nationwide-delivery.php --apply
```

重复运行保留已暂停规则；只有明确增加 --reenable 才重新启用同编号规则。区县规则优先于市、省；后台可以新增更具体的暂停规则。报价后发生停用、时段状态/归属/费用或地址变化，提交订单会重新检查并拒绝过期报价；不可配送仍能浏览商品。

原地区字典的港澳台缺少完整三级层级，仍需补齐或适配真实地区信息后验收，不能用省级覆盖记录声称已经支持完整地址录入。

## 微信支付

真实付款需要同一小程序的 AppID/AppSecret、商户号、API v2 密钥、HTTPS 支付回调和真实设备。配置放服务器环境。退款证书目录通过 SHOP_WECHAT_CERT_DIR 只读挂载到 /run/secrets/wechat；SHOP_WECHAT_CERT_PATH/KEY_PATH 是容器内文件路径。

长商城订单号保持不变，微信 out_trade_no 使用持久化的 32 位映射；成功回调和主动查单均核对 AppID、商户、订单、金额及流水。V5 回调不经过旧版会回退履约状态的支付处理器。重复及晚到的成功结果不会重复扣库存或回退已收货状态。

创建支付先持久化意图和映射，再在订单锁下调用网关；幂等重试会重新检查订单有效性，不重放已过期的支付参数。payment-status 与调度任务主动查单；取消/超时关闭先核实并关单，再释放库存和配送容量。USERPAYING、网关超时、身份或金额不符均保留待核实状态。创建后 120 秒内的 ORDERNOTEXIST 不作为取消依据，以保护仍在处理的请求；超过保护期的权威不存在结果可关闭该意图。

未配置微信时，普通订单可保存为待付款，不能声称实际扣款成功。本地无扣款支付仍只在专用测试库、显式开关及真实回环网络同时满足时启用，生产配置没有开启它。

## 验证

App：pnpm test、pnpm build:h5、pnpm build:mp-weixin。PHP：语法检查、RuntimePatchTest.php，以及专用测试库中的地区、路由、配送、MiniappCommerce 和 WechatPaymentLifecycleTest.php。支付测试使用网关替身，不能替代真实微信扣款/退款验收。

有写入的集成测试必须使用独立数据库；WechatPaymentLifecycleTest 还要求 HEALTHFLOW_RELEASE_TEST=1。不要在生产库或现用商城库运行夹具。部署后另验收登录、Excel 商品与图片、地址、核价下单、后台发货、收货与售后，并核对数据库事实；开发者工具构建通过不等于真机或服务器验收。
