# 微信聊天插槽样式

聊天输入栏由 `CloudNutritionChat` 提供，通过 `NutritionistLayout` 的 composer 插槽渲染。提供方使用 `shared`，接收方使用 `apply-shared`，使横向排列、圆角背景和说明文字字号能作用到插槽内容。

`NutritionistLayout.vue` 声明接收外部样式；`vite.config.js` 在微信构建中将两侧的隔离配置写入组件 JSON，避免后续构建依赖手工修改产物。

开发者工具中已观察到只调整接收方隔离设置即可恢复输入栏横向排列。最终生产构建成功，27 项相关测试通过，布局组件产物已选择性同步至当前小程序目录。前一次聊天任务恢复代码、接口配置和其他组件保持不变。备份和哈希证据在 `output/chat-layout-20261104/`。未上传或发布小程序，未进行真机验证。
