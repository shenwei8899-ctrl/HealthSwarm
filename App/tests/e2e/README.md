# 正式 App 家庭共享验收

这些脚本只用于开发环境的合成家庭，不使用生产账号或真实健康资料。先运行 `npm test`，以 `VITE_SERVICE_MODE=api`、空 `VITE_API_BASE_URL` 构建 H5；或启动同配置的 H5 开发服务并将 `VITE_HEALTH_API_PROXY` 指向 `http://127.0.0.1:15486`。浏览器目标为 `http://127.0.0.1:15187`，需要同源 `/api` 转发到 15486。

在 `agent/Yuxi-main` 的开发 Compose 中启动独立 API：

```text
docker compose run -d --no-deps --name healthswarm-formal-client-test -p 127.0.0.1:15486:5050 -v <仓库绝对路径>/App/tests/e2e/family-sharing-fixture.py:/app/formal_client_fixture.py:ro -v <仓库绝对路径>/agent/.tmp/<本次证据目录>:/app/formal-client-evidence api uv run --frozen --no-sync uvicorn formal_client_fixture:app --host 0.0.0.0 --port 5050
```

fixture 创建唯一 `formal_client_<uuid>` schema，所有业务和认证数据库依赖使用该 schema，写出合成账号信息到 `fixture.json`。只使用 `/fixture-ready` 判断本测试容器初始化；它不启动 Worker，因此 `/api/system/ready` 不代表此 CRUD 验收就绪。测试不执行模型、知识检索或订单操作。

设置 `FORMAL_CLIENT_EVIDENCE` 为本次证据绝对路径，使用提供 Playwright 的 Node 运行时（必要时设置 `NODE_PATH`）：

```text
node App/tests/e2e/family-sharing.browser.mjs
node App/tests/e2e/family-sharing-final.browser.mjs
docker cp App/tests/e2e/family-sharing-verify-pg.py healthswarm-formal-client-test:/app/verify_formal_client.py
docker exec healthswarm-formal-client-test uv run --frozen --no-sync python /app/verify_formal_client.py
```

第一项必须使用新 fixture，验证档案/姓名/结构化字段、五类实测、更正/作废、409、跨家庭拒绝、停用清理及换号；第二项使用第一项完成后的 fixture，验证登录错误可见及非法日期不发送写请求。最后直接回读数据库，断言版本、审计操作者、旧值、未确认和独立资料权限仍为空。

验收结束后 `docker stop --timeout 60 healthswarm-formal-client-test`，核对 `fixture-cleanup.json` 中 schema 与本次 `fixture.json` 一致且 `removed=true`，再移除该测试容器。不得删除或停用其他容器/卷。脚本故障时保留证据，不能把未通过批次计为通过。H5 浏览器、微信编译与微信真机/生产验收分别记录。
