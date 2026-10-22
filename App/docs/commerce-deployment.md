# 小程序商城配置与发布

App 是原 Vue 3 uni-app 项目。商城后端在仓库 shop，部署、迁移和支付说明见 [商城部署文档](../../shop/docs/deployment-commerce.md)。不使用 addons/shop/uniapp 的旧 Vue 2 构建覆盖 App。

## 配置

实际环境文件不进入 Git。正式小程序统一使用微信业务身份，在本机 .env.local 或构建平台环境设置：

```dotenv
VITE_SERVICE_MODE=api
VITE_COMMERCE_MODE=api
VITE_COMMERCE_API_BASE_URL=https://mall.example.com
VITE_WECHAT_APPID=
```

mall.example.com 必须替换为真实 HTTPS 商城域名。AppID 是公开标识；AppSecret、商户密钥和私钥只放后端，不使用任何 VITE 变量保存。未配置真实 AppID 时无法完成正式微信登录，不提供商城账号或业务密码作为替代入口。

VITE 参数会进入编译结果，修改后重新 pnpm build:mp-weixin 或 pnpm build:h5。微信开发者工具导入 dist/build/mp-weixin；127.0.0.1 只适用于本机调试，真机和服务器发布需使用可访问的 HTTPS 服务及合法域名。H5 开发环境可用 /commerce-api 代理；生产环境需要直接使用正式 origin 或自行部署对应反向代理。

## 实际数据

商品、规格、价格、可售库存、购物车、地址、核价、订单及售后读取商城接口。商品在后台 Excel 预览并确认导入后才入库；可见、已发布、有库存的 SKU 才显示。图片由 SHOP_MEDIA_BASE_URL 生成正式地址，迁移商品库时同时迁移上传图片。

餐单读取 Agent 保存的当前家庭安排。商品导入本身不会生成菜单或健康推荐。本人档案、确认版本和家庭选择以 Agent 云端为准；商城只承接实际商品和交易。前端、Agent 与商城来源校验必须成套发布，不能仅替换前端。

配送不可用时保留本次采购内容供核对；只有地址和配送状态经服务端确认后才核价。后台在报价后新增停配送规则或停用时段，旧报价不能继续提交。订单支付状态以服务端为准；关闭微信付款窗口不代表已取消订单或已释放库存。

采购时 POST /api/v1/commerce/session/exchange 携带微信业务 Bearer 和空对象；商城向 Agent 验证 wechat_authenticated，再按 client_id + uid:业务UID 复用或自动建立会员。已有可靠关联的会员、地址、购物车、订单继续保留；未关联旧数据不猜测合并，不恢复独立登录。具体接口和分阶段验收见[实施说明](统一微信主线实施说明-20261021.md)。

## 验证边界

运行 pnpm test、pnpm build:h5、pnpm build:mp-weixin。构建后在开发者工具及真机分别验收。后端支付回归使用网关替身；真实微信登录、扣款、退款和生产服务器运行需要真实配置及独立验收。
