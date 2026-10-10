# 健康 Agent 跨 attempt 执行预算

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/run_worker.py

## 问题

健康 Agent 遇到外层 ARQ 超时后，执行协程收到基础设施取消，现有 Worker 释放 lease 并将Run恢复为pending。ARQ作业失败与PostgreSQL恢复投递不是同一重试计数，后续投递仍可再次执行；用户无法获得有总时限的健康任务终态。模型SDK的默认HTTP重试与超时也没有沿健康Run的剩余时间收紧。

目标是让五个固定健康角色的同一Run从首次执行开始拥有不因重试或恢复投递重置的总预算，准备、模型及工具均在其中，耗尽后由当前lease Owner提交failed并完成既有清理。首次执行前的FIFO等待不计入预算；首次执行后的重试等待计入预算。独立人机输入后的resume使用其新Run的起点。普通Agent、用户取消、失去lease、专业业务状态及交易状态保持独立。

## 决策

### 实现方案

Worker仅对五个既有固定健康slug启用执行预算。取得lease后重读`AgentRunRepository.mark_running`首次写入且重试保留的权威`started_at`；总deadline为该起点加服务端部署预算，不接受请求或模型覆盖，不修改原始`input_payload`。不增加表、Schema、状态机、队列或健康结果Owner。部署默认预算为300秒，必须是正整数并小于等于外层ARQ超时减30秒，为执行关闭和持久终态清理留出时间；不满足时在Worker启动明确拒绝配置。人为部署改变预算会影响在途Run，首次起点仍保持。

每attempt取得ownership后读取持久起点和部署预算，计算剩余时间。耗尽的attempt在准备或外部调用前抛出专属不可重试错误；未耗尽的attempt启动拥有明确Owner的`asyncio.timeout`，覆盖输入恢复、配置准备、构图、模型和工具执行。heartbeat覆盖第一个长await；只有将真实取消异常交给本作用域`asyncio.Timeout.__aexit__`后，标准取消计数确认仅来自该计时器，才能翻译为预算耗尽；外部先取消、随后慢drain跨deadline仍保留基础设施取消。provider超时和外部取消沿原分类。准备阶段不吞掉预算错误。内部deadline在终态或重试收尾前结束，执行链先沿现有`_consume_stream_with_cancel`完成drain/close，才能提交终态或释放ownership。

健康预算通过当前执行作用域的ContextVar传到现有模型加载边界。三个当前provider适配器均支持SDK`timeout`和`max_retries`；只对健康作用域中新创建的模型将SDK自动重试设为0，并把超时限制到加载时的剩余时间，不修改缓存或已存在模型。内部deadline继续限制后续模型和工具调用；不安装通用网络重试、模型内容修复或无限重试middleware。作用域退出后恢复原值，非健康模型加载不增加限制。

预算耗尽返回稳定`health_execution_timeout`错误，沿现有`_finish_run`提交同Run的failed、关闭attempt、清除lease、收敛执行树和runtime cleanup后发布终态事件，不发布未校验健康正文。超时结算跳过可能慢的checkpoint用量读取，记录`available:false`，不把未知量补成零或计为完成。若PostgreSQL已确认用户取消，沿原cancelled路径；若当前attempt已失去lease，沿原停机路径，旧Owner不提交timeout终态。transition未改变时不发布虚假的failed事件。若取消在预检后、终态事务前提交，事务返回cancel_requested后立即交还既有取消Owner收尾，预算路径不读checkpoint。若当前最后attempt已提交completed且其权威输出指针匹配同Run/Request/Conversation、assistant/text/complete，则慢drain跨deadline后补发真实completed end；其他Owner终态不补发。预算内的基础设施故障仍可使用现有有限attempt重试，重试和恢复投递不能改变首次起点。PG故障仍依赖既有lease/reconcile收敛，预算不能承诺任意系统故障下即时提交failed。

## 替代方案

- 只降低ARQ作业超时：超时取消会进入基础设施重试语义，PostgreSQL恢复仍可重投同Run，且影响普通Agent，拒绝。
- 每attempt重新开始倒计时：无法给用户提供同Run总执行上限，拒绝。
- 新增健康Task计时表或恢复队列：复制已有Run事实、lease和清理Owner，拒绝。
- 只给SDK一个timeout：不能覆盖准备、工具执行及多次调用，也不能约束跨attempt恢复，拒绝。
- 在Run输入JSON固化预算：修改不可变用户输入事实并增加覆写与幂等边界；本范围接受部署操作调整在途政策，保持原始输入。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 当前总时限缺口及首次起点可复用 | ARQ短期状态被当最终事实 | run_worker、AgentRunRepository、ARQ安装实现 | 只读process_agent_run取消/重试分支、mark_running与release_lease_for_retry | 外层取消释放pending且恢复投递不共享ARQ tries | Inspected |
| 五角色起点不重置，准备/模型/工具耗尽形成failed | 每attempt重置、首次FIFO等待计时、普通Agent受影响 | 当前Run started_at与Worker执行作用域 | `test/unit/services/test_run_worker.py`：85 passed；三秒外部Worker慢回放通过；真实YuxiWorker双attempt 1 passed | 已耗尽第二attempt不再外呼，同Run首次started_at不变，准备/模型/工具慢调用，非健康兼容 | Passed |
| SDK仅使用剩余预算且关闭隐藏重试 | 默认SDK重试突破授权与总时间 | 当前模型加载/适配器 | `test/integration/services/test_health_model_execution_budget_http.py`：6 passed；真实loopback HTTP覆盖OpenAI/Anthropic/Gemini | 500仅一次发送、慢HTTP受剩余timeout约束、原有模型实例不变、退出作用域恢复 | Passed |
| 用户取消和lease失效保持独立 | deadline覆盖取消或旧Owner越权终态 | 当前RunContext与Repository终态Owner | 最终外部Worker命令3 passed，撤同意定向1 passed；咨询失败正文边界由[独立发布决定](2026-10-10-health-consultation-partial-publication.md)修复 | durable cancel、撤独立模型同意、旧attempt lease丢失、基础设施先取消后慢drain跨deadline | Passed |
| 最终结果和清理来自同Run事实 | 只看日志或ARQ失败而PG仍pending | 原_finish_run/输出/cleanup Owner | 8个已验收Run、9个attempt实际读回；50健康表及运行事实零行；14次精确cleanup各24表零行；原配置与24个provider哈希、队列和ready恢复 | 已验收路径无正文、无lease/cleanup pending；已耗尽第二attempt无新增模型调用 | Passed |

实际证据保存在本地`agent/.tmp/agent-completion-20261010/health-run-budget-verification-final.json`及对应命令日志，不随Git提交。单元85 passed、SDK真实HTTP6 passed、真实同Run双attempt1 passed；最终外部Worker命令为3 passed / 1 failed（失败来自Task错误投影的错误预期），修正到现有固定错误DTO后撤同意定向1 passed。两次命令分别记录，不声称同一命令4 passed。此前实际暴露的撤同意正文发布缺陷及其失败日志保留，最终该场景验证failed、无公开正文、无输出指针；失败Task只返回经过身份核对的固定执行失败DTO。

### 可复现的隔离实验

在`agent/Yuxi-main/`执行以下PowerShell流程。`$budgetEnvFile`指向该独立项目的本地合成环境文件，不输出或提交文件内容；项目名称限定为专属隔离槽，启动前确认没有其他测试占用其审批配置、队列和8778端口。原隔离环境已完成数据库迁移，API、Worker均可就绪；测试fixture创建合成账号、配置和业务事实并在每个用例后回读清理。

```powershell
$budgetEnvFile = '<隔离项目的合成环境文件路径>'
$budgetCompose = @('compose', '--env-file', $budgetEnvFile, '-f', 'docker-compose.yml', '-f', 'backend/test/support/health_consultation_e2e.compose.yml', '-p', 'health-diet-analysis-e2e')
$budgetApi = 'health-diet-analysis-e2e-api-1'
$budgetWorker = 'health-diet-analysis-e2e-worker-1'
$budgetHelperPid = $null
try {
    docker @budgetCompose -f backend/test/support/health_run_budget_e2e.compose.yml up -d --no-deps --force-recreate api worker
    # 等待 /api/system/ready 返回200且worker检查为ok，再启动专属回放。
    $budgetHelper = docker exec $budgetApi uv run --no-sync --group test python -c "import socket,subprocess,sys,json; s=socket.socket(); assert s.connect_ex(('127.0.0.1',8778))!=0; s.close(); p=subprocess.Popen([sys.executable,'test/support/health_run_budget_replay_server.py'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True); print(json.dumps({'pid':p.pid}))"
    $budgetHelperPid = ($budgetHelper | ConvertFrom-Json).pid
    docker exec -e HEALTH_CONSULTATION_E2E_ISOLATED=true -e HEALTH_RUN_BUDGET_E2E=true -e TEST_BASE_URL=http://localhost:5050 $budgetApi uv run --no-sync --group test pytest test/e2e/test_health_run_execution_budget_e2e.py::test_external_worker_budget_cancel_consent_and_lease_keep_distinct_final_facts -q --tb=short
    # 同Run双attempt必须仅暂停原隔离Worker，避免它竞争本测试job；测试使用真实YuxiWorker与独立随机队列。
    docker pause $budgetWorker
    try {
        docker exec -e HEALTH_CONSULTATION_E2E_ISOLATED=true -e HEALTH_RUN_BUDGET_E2E=true -e HEALTH_BUDGET_CONTROLLED_WORKER=true -e TEST_BASE_URL=http://localhost:5050 $budgetApi uv run --no-sync --group test pytest test/e2e/test_health_run_execution_budget_e2e.py::test_real_arq_pending_retry_keeps_first_start_and_refuses_second_external_call -q --tb=short
    } finally {
        docker unpause $budgetWorker
    }
} finally {
    if ($budgetHelperPid) {
        # 只停止本次捕获且cmdline匹配的精确PID，不按端口、名称或进程集合批量终止。
        docker exec $budgetApi uv run --no-sync --group test python -c "import os,signal,sys; from pathlib import Path; pid=int(sys.argv[1]); assert b'test/support/health_run_budget_replay_server.py' in Path('/proc/'+str(pid)+'/cmdline').read_bytes().split(b'\x00'); os.kill(pid,signal.SIGTERM)" $budgetHelperPid
    }
    docker @budgetCompose up -d --no-deps --force-recreate api worker
}
```

命令退出码须逐项核对；测试命令失败仍执行finally。最终核对原服务预算300、API ready与worker健康、未暂停、8778关闭、原审批配置与provider集合/哈希、所属job/随机队列键和默认队列基线、PG Run/attempt终态与lease/runtime cleanup。fixture不允许flush Redis或清理其他作业。SDK单次发送专项独立运行`uv run --group test pytest test/integration/services/test_health_model_execution_budget_http.py -q --tb=short`，无需短预算覆盖层。完整咨询引用Worker复验使用原300秒环境与8766咨询回放，见[咨询失败发布决定](2026-10-10-health-consultation-partial-publication.md)。

## 后果

此变更进入通用Worker和模型装配边界，必须通过现有取消、重试、FIFO、执行关闭与lease测试，并在隔离环境运行慢回放后读取真实终态。外层取消与内部deadline须避免同点竞争；不得在执行仍未关闭时释放lease或shield活模型继续执行。部署预算修改影响在途Run，运维需将其视为执行政策变更。清理失败继续使用既有runtime cleanup恢复，不能通过超时绕过。

专属三秒实验使用可复现的`backend/test/support/health_run_budget_e2e.compose.yml`覆盖层，仅设置独立api/worker部署预算，不修改主服务环境。启动时在原`docker-compose.yml`、`backend/test/support/health_consultation_e2e.compose.yml`后追加该层；完成后去掉该层，以同一隔离env-file、项目名和原两文件重新创建api/worker，核对原审批配置与provider哈希、ready、精确测试job键和租约清理。双attempt测试仅暂停原隔离worker，真实YuxiWorker领取本测试从默认队列移到随机专属队列的精确job；finally只清本测试job及随机队列键，恢复原队列基线并由宿主取消暂停。固定图CI使用默认300秒，不能加载三秒实验层。

配置与慢回放helper由独占隔离槽位运行，其他运行项目不参与配置修改。外部商城、专业规则和小程序页面不属于预算修复范围。此次局部验收不替代提交前全后端与固定图CI门禁；这些统一门禁由完整装配的发布检查拥有。
