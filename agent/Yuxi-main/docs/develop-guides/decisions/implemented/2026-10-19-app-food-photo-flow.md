# 正式 App 照片记餐流程

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_vision_service.py

## 问题

正式 App 已有人工记餐和更正，照片入口尚未连接健康识图服务。用户要求接通上传、识别任务、候选核对和确认记餐，暂缓实际模型及政策。

## 决策

新增正式照片记餐页面，复用健康私有上传、meal-photo-tasks、vision 分页、meal-drafts 修改/计算/确认。服务端继续拥有授权、任务执行、营养计算和正式事务。客户端保存成员隔离的任务/草稿 ID 与幂等请求标识以恢复未知提交；不持久保存照片或候选正文。配置只读，未配置不外呼；处理同意由用户针对当前处理方和政策明确提交。候选变更使本地预览失效，保存当前版本后计算，显式确认后回读正式记录。

## 替代方案

直接让聊天图片回复写入日记缺少候选复核和版本约束；重新实现服务端识图/计算会复制已验证能力。采用专用页面接现有业务接口。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 未配置不提交模型任务 | 配置/同意 | App client、既有 service | App unit、H5禁用状态 | 未启用、缺授权、政策变化 | Passed |
| 未知提交可恢复 | 网络/重开页面 | App client、既有确认事务 | App unit | 丢响应后原包同键重试、旧版本、撤权、切号 | Passed |
| 候选复核后确认当前计算 | 交互/来源 | App page、meal draft | test/integration/services/test_app_meal_photo_browser.py 与H5操作 | 缺失营养须明确接受；未确认不形成记录 | Passed |

真实 H5 经 HTTP 上传至隔离 MinIO，在独立 PostgreSQL schema 中创建任务、核对候选、关联食品、保存 v2、计算并确认。独立会话读取一条正式 DietLog，150g × 0.4 × 200kcal/100g = 120kcal，钠保持 null，原始照片关联保留。队列出口与识别结果使用测试替身；未验证真实模型、ARQ Worker 或生产识别效果。App 全量测试、H5 与 mp-weixin 编译单独执行；独立审查修复恢复选择及跨成员/候选状态残留。

客户端实现位于顶层 App 的 services/meal-photo-client.js、services/health-upload.js 和 pages/meal-photo/index.vue；现有健康业务服务拥有协议、授权、计算与最终事务。原图在页面内通过鉴权下载展示，切成员或权限失效时清除。页面显示任务状态，用户手动刷新；模型未启用时上传仍可用，识别按钮禁用，已有候选可以继续核对。

## 后果

真实模型准确率、微信真机和生产发布另行验收。图片上传接口无幂等键，上传响应丢失可能留下未绑定私有对象；不能把它称为识别或记餐成功。
