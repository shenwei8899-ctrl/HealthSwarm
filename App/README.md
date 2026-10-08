# 家庭 AI 营养师微信小程序

本目录是 Uni-app + Vue 3 小程序工程，包含 30 个页面、公共组件、业务逻辑、样式、图片资源、构建配置和现有测试。小程序页面源码位于 `src/pages/`。

## 安装与构建

需要 Node.js 和 pnpm。当前验证环境为 Node.js 24、pnpm 10.33.0。

在仓库的 `App/` 目录运行：

```bash
pnpm install --frozen-lockfile
pnpm test
pnpm build:mp-weixin
```

微信开发者工具导入 `App/dist/build/mp-weixin/`。实际小程序 AppID 写入 `src/manifest.json` 的 `mp-weixin.appid` 后重新构建；当前该项留空。

## 源码结构

- `src/pages/`：登录、建档、AI 对话、家庭档案、菜单、食材包、烹饪、记餐、反馈、订单等页面。
- `src/components/`：公共 Vue 组件。
- `src/utils/`：业务逻辑、状态和本地存储。
- `src/services/mock.js`：模拟服务。
- `src/styles/`、`src/uni.scss`、`src/static/`：样式和图片资源。
- `src/App.vue`、`src/main.js`：应用入口。
- `src/pages.json`、`src/manifest.json`：页面与平台配置。
- `tests/`：现有业务及前端回归测试。

修改源文件后重新构建，不直接修改 `dist/` 中的生成文件。

根目录 `index.html` 只是加载 `src/main.js` 的 H5 构建入口，不包含小程序页面实现。同一份 Uni-app 源码可通过 `pnpm dev:h5` 或 `pnpm build:h5` 在浏览器预览。

## 当前集成状态

当前为可构建的前端实现。微信登录、真实 AI、语音转写、图片识别、Supabase、库存、支付和订阅消息等服务尚未接入；相关流程采用模拟服务和本地测试数据。源码构建和测试通过不代表微信开发者工具、真机或真实业务服务已验收。

本目录不包含 HTML 原型演示页、离线体验版、离线打包脚本、网页演示部署目录、依赖目录或编译产物。
