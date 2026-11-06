# Agent 商品目录只读连接

本文用于商城数据库管理员和部署负责人配置咨询 Agent 的 SKU 条件搜索。Agent 先通过商城签名接口读取有货分类并验证本轮分类回执，再只查询所选分类内的商品与食材目录；商品详情仍调用商城既有签名接口，核价、下单和支付继续以商城业务服务为准。生产凭据和真实业务数据不进入 Git。

## 数据库权限

在商城 PostgreSQL 上以管理员身份执行 [只读角色脚本](../database/postgresql/operations/20261106_agent_catalog_reader.sql)。脚本创建 `healthswarm_catalog_reader`，初始为 `NOLOGIN`，只授予七张目录表的 SELECT，并拒绝已有高权成员关系、商品写权限和订单读取权限。重复执行不会重建或删除商品数据。

在真实库核对角色和授权后，进入管理员 `psql` 交互会话，先执行 `\password healthswarm_catalog_reader` 设置独立随机密码，再执行 `ALTER ROLE healthswarm_catalog_reader LOGIN;`。不要把密码写进 SQL、Compose 文件、命令历史或仓库。确认该角色不能写目录表，也不能读用户、订单或支付表；只读权限是数据库边界，不依赖 Agent 代码约定。

若商城与 Agent 在同一 Docker 主机上，先创建专用网络，再分别把 [Shop 叠加配置](../docker-compose.agent-catalog.yml) 和 Agent 的 `docker-compose.shop-catalog.yml` 叠加到现有 Compose 命令中。Shop 数据库在该网络中的别名为 `shop-catalog-db`；Agent API 与 Worker 同时加入网络。叠加配置不会发布数据库端口。不同主机部署需要现有私有网络或 VPN，并单独验证数据库传输加密；不要把 5432 暴露到公网。

```sh
docker network create healthswarm-commerce-catalog
docker compose --env-file .env.production -f docker-compose.production.yml -f docker-compose.agent-catalog.yml config --quiet
docker compose --env-file .env.production -f docker-compose.production.yml -f docker-compose.agent-catalog.yml up -d
docker compose --env-file .env.production -f docker-compose.production.yml exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < database/postgresql/operations/20261106_agent_catalog_reader.sql
```

以上命令在 Shop 目录执行。Agent 的叠加命令在 `agent/Yuxi-main/` 执行，并保持 API、Worker 原有网络：

```sh
docker compose -f docker-compose.yml -f docker-compose.shop-catalog.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.shop-catalog.yml up -d api worker
```

完成授权和网络验证后，通过 Agent 的部署密钥同时给 API 与 Worker 配置 `HEALTH_COMMERCE_SEARCH_DSN`，主机名使用 `shop-catalog-db`。未配置时 Agent 保持原按分类读取完整目录的路径；配置后数据库异常会使本次搜索显式失败。不要在未验证真实商城连接、只读权限和商品详情回源前启用。

## 索引与验收

先以真实数据和典型查询运行 `EXPLAIN (ANALYZE, BUFFERS)`，确认名称、分类和食材别名的模糊匹配成本，另测已确认过敏或忌口时的限制名称解析。需要时以管理员身份**单独**执行 [索引脚本](../database/postgresql/operations/20261106_agent_catalog_indexes.sql)；该脚本使用 `CREATE INDEX CONCURRENTLY`，不得放入单一事务。它会创建 `pg_trgm` 扩展、空白归一化的目录字段 GIN 索引及限制名称 B-tree 索引，但会增加写入和存储成本。部署窗口、空间和执行耗时由商城负责人评估。

用合成或脱敏数据验证名称、SKU、分类、已审核食材及别名、空查询、分页、下架、库存归零和映射失效。确认只读角色无写权限与无交易表读取权限；在商品变更后检查 Agent 的单 SKU 详情回源拒绝旧来源。最后比较旧全目录路径与数据库直读路径的查询计划、请求数、返回字节、工具耗时和最终答复 P50/P95，包含已确认过敏或忌口的档案。隔离 PostgreSQL 语法与权限验证已经通过；真实 Shop 数据库、网络及性能仍待联调。
