# 家庭成员卡片跟手翻动

## 行为

家庭成员卡片的翻转由单指横向位移控制。拖动时没有时间驱动的缓动，停住保持当前进度，拖回沿原路径恢复；松手后从当前位置完成切换或回弹。横向方向识别容差为8px，完整翻卡距离为卡片实测宽度的65%；进度达到35%可完成切换，最近100ms速度超过0.5px/ms且进度超过10%也可完成。收尾约160–320ms，有完成回调和超时兜底。

左右运动互为镜像；越过起点可预览另一侧邻居，首尾不循环。顶部选择和正式成员事件只在完成后更新，取消不提交成员选择；底部摘要随同一进度淡入淡出。点击成员标签和切换按钮沿用同一收尾流程，连续点击保留最后一个待切换目标。

## 实现边界

- `src/components/FamilyMemberDeck.vue`：测量卡片宽度、接收手势、绑定位移/透明度、屏蔽拖后误点击；卡片按成员ID保持稳定节点，避免触点目标中途被替换。
- `src/utils/family-card-transition.js`：区分预览和收尾；成员快照只在新预览时复制。方向、进度和近期速度用于判断释放结果，家庭/页面变化清理手势和计时器。
- `src/components/CloudFamilyOverview.vue` 与 `src/pages/profile/index.vue`：转发拖动状态，由页面首个 `page-meta` 仅在横向拖动期间锁定页面滚动，松手、取消、卸载和隐藏解除；纵向手势留给页面。
- 无后端、鉴权、档案写入或线上服务变更。

## 验证

- `node --test tests/family-card-transition.test.mjs tests/family-sharing.test.mjs tests/family-invitations-flow.test.mjs tests/navigation-shell.test.mjs`：67项通过，其中卡片相关28项（新增10项）。
- H5与微信小程序独立输出构建成功。生成物位于工作区 `output/family-card-drag-20261124/`，随后已增量合入现用交付目录及同名ZIP（版本 `2026.11.24-family-card-drag`）。
- Edge无头浏览器通过CDP发送真实触摸事件，320/390/430宽度验证：连续慢拖、停住、继续拖、反向回拖、完成切换、取消、原卡片DOM节点稳定、纵向滚动和释放滚动锁。使用合成演示成员，不访问真实健康数据。
- 全量 `pnpm test` 本轮结果为2027项：1755通过、269失败、3跳过。其中268项是其他聊天测试夹具的 `ReferenceError: useReplySelection is not defined`，集中于chat-workflow、consultation-send、daily-meal-plan-unification、chat-products、chat-recovery；这些模块本轮未修改。另1项图片代理因沙箱本机TCP权限失败，沙箱外单独复核通过。全量测试未全绿。
- 备份、相对本次开始时的补丁、日志、截图及浏览器结果在工作区 `output/family-card-drag-20261124/`。

## 尚未验证

微信真机上的手指跟随延迟、原生滚动锁与触摸中断仍需设备验证。编译通过和浏览器触摸模拟不替代真机体验。未上传微信，未部署服务器。现用目录及ZIP已增量同步，更新12文件、保留699文件，711文件目录/ZIP与构建记录逐项一致；备份和安装回执位于 `output/family-card-drag-20261124/merge/`。保留现用公共运行库原始字节，只追加 `onResize` 导出；正式配置和登录声明修复均保持不变。
