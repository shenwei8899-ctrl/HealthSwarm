# 配餐知识检索的非空工具参数

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/agents/toolkits/meal_planner.py

## 问题

本文面向维护配餐工具与执行图的开发者。参考食谱和初始配餐知识检索要求非空关键词，正式已发布菜谱检索允许空查询浏览目录。共用允许空串的 schema 会让缺失或空白参数进入知识服务，产生 `knowledge_query_invalid` 并中止当前执行图。日志中的同类错误计数尚未关联具体用户运行，不作为本问题的归因证据。

## 决策

### 实现方案

工具包装拥有模型输入约束，service 继续拥有授权、来源和真实检索。参考食谱工具使用必填、trim 后 1–80 字符的 schema；初始知识工具复用 `HealthKnowledgeInput` 的必填、trim 后 1–120 字符约束，与各自服务一致。正式目录工具保留默认空查询。schema 不替换、截断或推测模型关键词。

真实 `create_agent` 回放先提交缺失或空白参数，核对 LangChain 工具入参错误可以返回模型并允许下一次合法调用；合法调用继续执行原服务的授权和来源检查。服务异常不转成假 sources，授权撤回和来源失效仍中止原执行路径。

## 替代方案

- 所有 `RecipeSearch` 统一必填：破坏正式菜谱的空查询浏览契约。
- 捕获服务异常并返回空结果：混淆参数错误、授权失败和来源失效。
- 自动补默认关键词或截断：改变模型实际查询且掩盖错误。

## 后果

缺失、trim 后空串和超长关键词在工具参数边界形成 LangChain 可读错误，模型可以重新提交合法关键词。没有新增 service 异常捕获、假来源结果或默认关键词。授权与来源检查继续由原 service 执行；工具参数通过不等于有权读取资料，也不等于知识库存在适用食谱。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 必填知识工具拒绝缺失、trim 空串和超长参数 | 工具 schema | meal_planner.py、HealthKnowledgeInput | 定向 unit | 旧 schema 允许空串进入服务 | Passed |
| 参数错误经过真实工具节点后可纠正，不伪造来源 | Agent 工具执行图 | LangChain ToolNode、真实工具包装 | create_agent 合成模型回放 | 旧 schema 因 `knowledge_query_invalid` 中止 | Passed |
| 合法检索保留授权和来源失败，正式目录仍允许空查询 | 业务边界 | 原检索 service、RecipeSearch | 合法工具调用与失败回放 | 撤权或来源失效继续抛出原异常 | Passed |

`Passed`：新增回归在旧 schema 下为 12 项失败、7 项通过，缺失和空白参数的真实工具节点回放均在原生产 service 的 `knowledge_query_invalid` 处中止。修复后新增 21 项 unit 通过，覆盖 missing、blank、各服务 max、trim、合法目录空查询、工具参数错误后的纠正，以及原授权和来源拒绝。

`Passed`：包含注册、普通建议、商品义务、最终正文、生命周期和协议 oracle 的相关九个模块共 186 项 unit 通过。本地 namespace runner 避免应用入口加载环境文件；真实工具包装、ToolRuntime 注入、create_agent 和所涉及生产检索函数原样执行，PG 会话、知识命中及授权存储为合成依赖。坏参数产生 error 工具消息，纠正后只调用一次 service，原授权前后核对继续执行；授权撤回或来源失效仍抛出原异常。

`Not run`：真实模型自纠程度、PostgreSQL/知识库/Worker 完整链路，以及日志错误与具体用户失败运行的关联。工具节点回放证明参数恢复协议，不证明真实模型一定选择纠正关键词。本决定不调整服务错误处理、权限、来源回执或正式餐单保存。
