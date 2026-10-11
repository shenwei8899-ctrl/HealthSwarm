# OCR任务与草稿分页

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_vision_service.py

## 问题

后台OCR任务与复核草稿各只读取最近50条，并在前端筛选报告或饮食；某一种类的新记录会挤掉另一种类的历史。用户需要继续查看旧任务、打开旧草稿，同时保留正在编辑的内容。既有成员vision接口返回结构需要兼容。

## 决策

### 实现方案

新增认证GET `/api/health/v1/members/{member_id}/vision/page`。kind必填report或meal，jobs_limit和drafts_limit默认20、范围1至50，jobs_offset和drafts_offset默认0、范围0至2147483647。响应含jobs、drafts、jobs_next_offset和drafts_next_offset。路由及DTO拥有协议；repository在分页前筛选成员与kind，按created_at降序、id升序各取limit+1；service每次校验report_view或diet_edit授权并检查源图片有效性，返回现有任务摘要和草稿投影。next_offset按原始入库窗口推进，来源被过滤后的空页仍可继续。任务状态来自TaskRecord，复核状态来自VisionDraft，普通读取不触发任务或写入。成功响应禁止缓存。旧vision接口仍保持最近50条的两个数组。

后台保留两个独立页码；单侧翻页只改变该侧位置。成员或用途变化、显式刷新、新建任务或草稿成功回到首页；轮询和编辑后的列表刷新保留当前位置，不重读已选详情。已授权OCR分区在页面可见且不忙时每3秒读取当前两页；背景读取保留现有列表且不锁复核输入。最新请求、成员、用途、操作者和卸载状态共同保护响应；403/404清理私有列表、已选详情及两用途正式记录缓存。任务完成仍由用户显式打开草稿。

## 替代方案

修改原vision返回结构会破坏旧消费者；增大固定上限仍无法访问任意历史。增加数据库快照游标和总数查询超出浏览历史的当前需求；增加活动任务摘要会扩大协议，当前可见OCR分区轮询已能更新当前页。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 独立有界分页与旧协议兼容 | HTTP/SQL | route/repository/service | 定向unit56项；真实TCP/PG11项，跨50条、同时间排序、单侧翻页 | 去掉kind、offset、ID排序或lookahead；非法参数 | Passed |
| 每页授权与源有效性 | 私有数据 | repository/service | 110次GET前后所有ORM表行/xmin及摘要一致，11个随机schema清理回读；授权撤回、图片删除、空中间页 | 11种缺陷恢复负控均由对应guard检出；无权空页 | Passed |
| 页码、轮询与编辑隔离 | 浏览器 | HealthVisionView.vue | 前端定向47项、lint/build；隔离页面61报告与41饮食历史、独立页码、空成员、未保存输入、撤权与恢复 | 迟到响应、用途/成员/操作者变化、两用途缓存、失败重试、轮询重置页码或草稿 | Passed |

后端完整unit为4421 passed、59 skipped；前端完整867项通过。trust guard与其63项unit通过。真实页面的任务、草稿行及xmin未变化；合成用户、成员、任务、草稿和凭据清理回读确认。浅色和深色页面已目检；671px实际窄屏为单列且无横向溢出，窄屏截图能力未成功，未把DOM检查描述成窄屏像素验收。可复现命令见[测试规范](../../testing-guidelines.md#ocr任务与草稿分页验证)。本轮不验证OCR供应商、Worker处理、模型、MinIO真实对象删除或专业营养质量。

## 后果

offset分页不是跨请求一致快照，并发新增可能改变页边界；刷新回首页。不提供总页数。当前分区每3秒读当前两页增加有界读取频率，不调用模型。草稿仍包含已确认等原有状态，不把查询投影当作新增营养或专业复核验收。正式小程序接入与整体协议冻结仍待各自负责人。
