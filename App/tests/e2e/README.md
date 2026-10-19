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

## 开发计划第 2、4、6 项客户端验收（2026-10-16）

客户端按现有后端契约接入；本次没有改动 `HealthSwarm` 后端、模型配置或生产环境。正式入口在 API 模式的账号页：实际饮食记录、三指标回顾、报告上传与恢复、饮食照片识别与恢复、餐单与正式采用。默认演示模式仍保留。

| 项目 | 客户端行为 |
| --- | --- |
| 2 记录更正 | 修改实际时间、餐别、项目、克数及个人比例，保留原图位置证据；传原版本和同一请求键。后端同步事务重算，回读原 ID 的新版本；空数值保持未知。冲突要求重新读取，已保存记录可进入版本绑定的反馈。 |
| 4 三指标回顾 | 选择北京时间范围或具体记录，展示服务端结构化分组、统计和待补充问题。明确统计仅覆盖返回记录；缺少本人来源关联时提示关联，并禁用咨询入口。选定记录与版本传入独立指标会话。 |
| 6 上传和确认 | 分成员、用途授权；支持照片、聊天文件、取消上传、任务恢复/取消/明确重试、候选分页、人工录入与核对。饮食先服务端计算，再明确确认。未知任务/确认结果保留原请求，候选 PATCH 结果未知时先回读。 |
| 6 聊天和权限 | 恢复问题队列与选定任务，有限 SSE 重连后用 Task 查询恢复；不展示事件流中的模型候选正文。保存原未知问题以原键重试，确认后清除。切换账号、页面隐藏、失权或来源失效后丢弃迟到响应。 |
| 6 餐单采用 | 区分草稿、当前专业批准、正式采用与实际摄入。采用前重新读取批准和档案版本，替代既有当日采用需明确选择；取消提供原因并保留历史。未知采用/取消沿原请求恢复。 |

### 复现环境

`health-client-fixture.py` 使用真实 FastAPI 路由、仓储和 PostgreSQL，但只允许名为 `client246`、端口为 15488 的专用临时数据库。它会建表并创建合成账号、菜谱、实测和专业批准；**不要指向日常开发库或生产库**。运行 API 时使用现有后端依赖环境，`PYTHONPATH` 包含后端根目录、后端 `package` 目录和 `tests/e2e`。

1. 启动独立 PostgreSQL 16 临时容器，绑定 `127.0.0.1:15488`；数据库、账号均为 `client246`，使用本次合成测试专用密码，数据目录用 tmpfs。
2. 为独立 API 同时设置 `HEALTH246_POSTGRES_URL` 和 `POSTGRES_URL`，指向该临时数据库；Docker 内使用 `host.docker.internal:15488/client246`。设置 `HEALTH246_EVIDENCE` 为可写的本次证据目录，并设置测试专用 JWT 配置。执行 `python -m uvicorn health-client-fixture:app --host 0.0.0.0 --port 5050`，将容器端口绑定到 `127.0.0.1:15487`。Windows 本机后端的 `os.O_DIRECTORY` 限制需通过容器运行解决，不修改后端业务代码绕过。
3. `/fixture-ready` 返回 `ready=true` 后，从证据目录读取 `fixture.json`。其中 token 仅用于本次合成账号，不写入源码或提交记录。
4. 以 `VITE_SERVICE_MODE=api`、空 `VITE_API_BASE_URL`、`UNI_OUTPUT_DIR=.codex/client-246-20261016/api-h5` 构建 H5，再执行 `node tests/e2e/health-client-preview.mjs`。可用 `HEALTH246_H5_DIR` 指定其他输出目录。预览仅绑定 `127.0.0.1:15189`，把 API 和 fixture 请求转发到 15487。
5. 在该专用浏览器来源设置 `fn-session-v2:api`，值为 `JSON.stringify({type:'object',data:{accountId:fixture.account_id,householdId:'synthetic-client246',token:fixture.token,clientRevision:'client246-test'}})`。`accountId` 必须用 `User.id` 的字符串，不能用 UID。

验收不启动 Worker 或真实模型；使用 `/fixture-ready`，不把全系统 readiness 当作 CRUD 测试前提。2026-10-16 的隔离测试镜像另外固定了 deepagents 0.7.9、langchain 1.3.17、langchain-core 1.6.0、langgraph 1.2.11、langgraph-checkpoint 4.2.0、langgraph-prebuilt 1.1.0；该临时依赖设置没有写回项目。

### 页面与数据库断言

- 打开实际饮食记录，将 fixture 原记录 150g 更正为 300g，保留个人比例 0.4，填写原因并接受缺失营养。断言 PATCH 200、ID 不变、v1→v2、120→240 kcal。`/fixture-facts` 独立读库应显示 `records=1`、`revisions=2`、`version=2`。
- 打开 `#/pages/indicators/index?memberId=<member_id>`，读取 2026-10-16。三条实测里空腹 5 和 7 分为一组，均值 6.00；餐后 9 单独分组。勾选单条再次回顾，断言请求仅有该 ID/版本，回执仅返回一条。最小/最大值可带小数，不依赖字符串格式固定为整数。
- 在 `#/pages/health/vision?kind=report&memberId=<member_id>` 创建人工候选，填写名称、原始结果、单位、参考范围与修改原因。断言候选 PATCH v1→v2，明确确认 200，确认条数增加，实际饮食记录数仍为 1。
- 打开 `#/pages/health/plans?memberId=<member_id>`，核对 `invalidated_plan_id` 的旧批准失效且无法采用。再以 `plan_member_id` 打开独立有效批准的 `plan_id`：采用返回 201，数据库为 active/v1；填写取消原因，取消返回 200，数据库保留 withdrawn/v2，饮食记录数不变。
- 隐藏/重开、响应丢失、原键重试、候选不盲重试、排队取消、授权撤回、跨成员归属校验、换号迟到响应、上传大小/鉴权/取消与拆分 UTF-8 事件流由 `health-client-workflows.test.mjs` 和 `health-task-flow.test.mjs` 验证。

### 本次结果和边界

全量 `npm test` **244/244 通过**；默认 H5、默认微信小程序及正式 API 模式 H5 构建通过。真实 HTTP/数据库验收完成更正、指标选择、人工报告确认、无效批准拦截、有效采用和取消。390px 视口截图检查完成，无页面脚本错误或横向内容溢出。

日志、独立数据库回读、浏览器验收步骤保存在 `.codex/client-246-20261016/`；截图见 `docs/assets/client-246-20261016/`。测试结束只停止本次独立 API、临时数据库和预览进程，保留证据。

尚未验收真实 OCR/多模态识别、真实模型反馈、微信原生文件/权限交互和微信真机断线恢复；未提交、推送或部署。本次通过的合成 HTTP/数据库用例不能替代这些验收。
