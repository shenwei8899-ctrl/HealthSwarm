# 成员面板与现有记餐事实统一

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/meal_roster_service.py

## 问题
空白对话失焦会卸载成员面板；独立 consumed_at 与现有逐人记餐确认可能冲突。

## 决策
### 实现方案
对话页持有成员面板与打开前的会话展示位置，稳定挂载到页面覆盖层。普通空白输入失焦仍沿用原交互，成员编辑后的页面保持原会话。
既有 DietLog、VisionConfirmation 与 VisionDraft 拥有实际摄入及撤回事实。repository 按家庭关联、原餐单成员、上海自然日和餐次读取有效确认，仅向餐单返回保护位。任一成员已有有效记录时保守保留该餐安排，界面称“已有记录”，不声明全家完成用餐。更正按当前 DietLog 快照重算日期和餐次；来源草稿撤回或版本失效后不再保护。专业营养资料当前可分析性不抹掉实际摄入事实。
修改名单、默认名单调度、worker、每日发布与专属计划发布重验相同投影；与既有记餐共用 FamilyArchive 行锁。原名单接口 consumed=true 明确拒绝，引导回既有记餐流程。不新增整餐完成按钮或持久完成状态。
旧 consumed_at 不再参与运行时判断；定向修复仅针对已核对、没有有效日记支撑的特定旧标记，备份并使用版本条件，不重置其他历史。

## 替代方案
只隐藏已用餐标签仍会留下后端锁。把一条逐人记录视为全家已用餐会失真。新增全家完成状态扩大了既有链路，均不采用。

## 验证
| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 空白对话操作后保留会话 | 浏览器失焦 | CloudNutritionChat | 编译后浏览器 | 无草稿且无消息 | Passed |
| 旧标记不生成用餐事实 | HTTP/PG | meal_roster_service | integration | 只有 consumed_at | Passed |
| 有效记餐保留原安排 | HTTP/PG | MealExecutionRepository | integration | 撤回、错日、错餐、其他成员 | Passed |
| 既有记餐与发布排序 | PostgreSQL | 家庭行锁 | integration | 写入未提交 | Passed |

## 后果
部分家庭成员已记录时整餐安排保守冻结，不自动改写剩余成员菜谱；不向其他家庭成员公开个人摄入明细。正式发布需独立 Review、真实 PG/HTTP 与候选镜像验证。

验证结果：前端全量 2069 通过、3 跳过；相关 125 通过。编译后 H5 在 320/390/430 宽度验证空白对话打开、取消、保存、问候语保留及普通再次失焦；320×480 验证失败仅一条提示和草稿保留。微信编译产物验证真实 tap 绑定、外部入口与稳定覆盖层。
后端同一组 28 项真实 TCP/独立 PostgreSQL 回归在 API、worker、worker-consultation 三个精确候选镜像各自通过，含逐人记录、撤回、当前快照、草稿版本、跨家庭/餐次/原名单、提交等待、生成期间新记餐、worker 收敛及旧结果拒绝。静态检查通过；独立 Reviewer 审查源码、逐角色发布差异及门控修复脚本未发现阻断问题。
验证文件位于 candidate/agent/.tmp/roster-flow-fix-20261124/verification.json；候选日志位于同级 diner-sync-20261124/release/roster-flow-fix-v2-20261124/deploy。未用单元测试替代真实数据库验证。微信官方预览和手机真机未验证。
