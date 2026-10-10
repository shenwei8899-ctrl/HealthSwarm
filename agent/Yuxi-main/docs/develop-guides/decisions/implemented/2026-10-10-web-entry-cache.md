# SPA 入口不使用浏览器缓存校验

状态：implemented
类型：bug-fix
Owner：docker/nginx/default.conf

## 问题

本地 OCI 打包可以产生相同时间戳、相同长度而内容不同的入口 HTML。Nginx 默认生成的 ETag 与 Last-Modified 无法区分这些入口，条件请求返回 304 后浏览器继续引用已被替换的旧资源，页面导航失败。

## 决策

### 实现方案

[Web Nginx 配置](../../../../docker/nginx/default.conf)对 `/index.html` 设置 `Cache-Control: no-store`，关闭 ETag 和 If-Modified-Since 校验。首页的 index 解析和深层 SPA 路由的内部重定向均经过这个精确 location，返回当前构建入口。带哈希资源和 API 代理沿用既有配置。

这是可在同一变更验证的局部缓存修复，不涉及持久数据、鉴权或需要先裁决的架构方案，因此直接记录 implemented。

## 替代方案

仅调整打包时间戳依赖构建工具持续保证版本差异；仅清理一次浏览器缓存无法保护已有访问者。对全部资源禁用缓存会增加带哈希资源的重复下载。

## 后果

每次获取入口都会传输完整的小型 HTML；页面导航引用当前构建资源。已经打开的旧页面需要刷新以获取新入口；发布过程中跨版本的未完成请求不在此修复的保证范围内。

## 验证

[真实 HTTP 探针](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/scripts/verify_web_entry_cache.py)对首页、显式入口和家庭深层路由分别携带旧 If-Modified-Since、If-None-Match，要求六次响应均为 200、no-store、无 ETag 且 HTML 内容一致。修复前真实服务返回 304，探针失败；修复后的隔离 Nginx 和部署服务使用同一探针验证。部署还需要浏览器刷新、导航与资源加载检查。
