# 正式 App 家庭共享发布说明

家庭档案 H5 独立使用 `/family-app/`，现有商城 `/mall/` 保持其原业务模式。构建正式 `App/` 时设置 `VITE_SERVICE_MODE=api`、空 `VITE_API_BASE_URL`、空 `VITE_COMMERCE_MODE` 和 `UNI_H5_BASE=/family-app/`，运行 `uni build -p h5`。健康业务账号与商城身份分别登录；不会把商城本机健康体验自动迁为云端档案。

生产使用现有80端口网关：`/family-app/` 转发至18082静态服务，`/api` 保持现有路由到 Agent 业务 API。服务器当前后端含 `identity-20261015` 身份整合覆盖层；本次仅发布 H5，不用本地旧镜像覆盖该后端。共享服务源码摘要已与本地核对一致。微信服务端代码在服务器上已存在，实际微信登录和真机仍须独立验证，不能继续一概描述为“服务端未交付”。

部署脚本为 [deploy_family_app.py](../scripts/deploy_family_app.py)。发布目录限定 `/opt/healthswarm-commerce/releases/family-app-<提交前12位>/`，包含 `h5/` 和 `manifest.json`（完整revision及逐文件SHA-256）。先执行脚本 `check`，再执行 `deploy`；首次发布检查已有路由或链接即拒绝，后续升级应另准备保留前一链接的发布方案。

脚本备份两份 nginx 配置，保留文件 bind mount 的 inode，测试配置后热加载；异常时恢复原配置及本次链接。部署前后核对现有容器、环境文件摘要、后台首页和商城首页不变。回滚点保留在发布目录 `proxy-backup/`。静态发布无需暂停 API/Worker 或改模型与政策。

生产验收使用随机凭据的专用合成普通账号、独立合成家庭，通过 SSH 隧道访问实际网关和 API。验证编译后浏览器页面、资源、共享读改、五类实测、更正作废、冲突和权限清理，并直接回读生产 PostgreSQL 中这些合成对象的版本和审计。验收结束后禁用合成账号及其家庭关系，保留可追溯审计；凭据不进入 Git、报告正文或公网日志。

现有公网入口为 HTTP。公网匿名资源检查与隧道内认证业务验收分别记录，不宣称 HTTPS、微信真机或负责人业务签认已经完成。模型与政策保持用户要求的暂缓状态。
