<script setup>
import AppIcon from '../../components/AppIcon.vue'
import AppNavBar from '../../components/AppNavBar.vue'
import { computed, nextTick, ref, watch } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import FlowRibbon from '../../components/FlowRibbon.vue'
import MealBundleRecommendations from '../../components/MealBundleRecommendations.vue'
import { getProfile, getRecords, updateRecord } from '../../utils/profile.js'
import { createPlan } from '../../utils/demo.js'
import { createMealBundles } from '../../utils/meal-bundles.js'
import { createDiabetesCasePlan, DIABETES_CASE_ID, DIABETES_CASE_QUESTION, getActiveHealthCaseId } from '../../utils/health-cases.js'
import { applyMealCustomization, getMealSwap } from '../../utils/meal-customization.js'
import { DAILY_MEALS, mealToRoute } from '../../utils/meal-flow.js'

import DinerPicker from '../../components/DinerPicker.vue'
import { todayPlan,setMealMembers,activePlanOrder,changeResult,localDate,saveTomorrowProposal } from '../../utils/meal-state.js'
import { remember,forget } from '../../utils/memory.js'
const dinerMeal=ref('晚餐'),dinersOpen=ref(false),planRevision=ref(0),communityOpen=ref(false),updateNote=ref('')
const profile = ref(getProfile())
const records = ref(getRecords())
const input = ref('')
const thinking = ref(false)
const messages = ref(uni.getStorageSync('chat-'+localDate())||[])
watch(messages,value=>uni.setStorageSync('chat-'+localDate(),JSON.parse(JSON.stringify(value))),{deep:true})
const scrollTarget = ref('')
const caseId = ref(getActiveHealthCaseId())
const caseFeedback = ref(false)
const inlineTodayOpen = ref(false)
async function scrollToLatestReply() {
  await nextTick()
  scrollTarget.value = 'message-' + (messages.value.length - 1)
}
const nameList = computed(() => profile.value.members.map(m => m.name).join('、'))
const lastRecord = computed(() => records.value[records.value.length - 1])
const isDiabetesCase = computed(() => caseId.value === DIABETES_CASE_ID)
const caseRecordFeedback = computed(() => isDiabetesCase.value && lastRecord.value?.memberName === '爸爸')
const today = new Date()
const dailyPlans=computed(()=>{planRevision.value;return DAILY_MEALS.map(item=>{const plan=todayPlan(profile.value,item.name);return {...item,plan,summary:plan.blocked.length?'请补充家庭档案':plan.dishes.slice(0,2).map(d=>d.name).join(' · ')}})})
const selectedDinerPlan=computed(()=>{planRevision.value;return todayPlan(profile.value,dinerMeal.value)})
const hasActivePaidPlan=computed(()=>{planRevision.value;return Boolean(activePlanOrder())})
const prompts = computed(() => ['今晚全家吃什么？', '给我安排明天早餐', '看看我的饮食记录', '糖尿病家庭怎么吃？'])
onLoad(options => {
  caseFeedback.value = options.caseFeedback === 'diabetes'
  if (options.recordId) setTimeout(() => { messages.value.push({ role:'assistant', recordId:options.recordId, text:'这餐吃下来怎么样？有什么想告诉我的吗？你可以用文字或语音补充。' }); scrollToLatestReply() }, 280)
  if (options.startCase === 'diabetes') setTimeout(() => ask(DIABETES_CASE_QUESTION), 380)
})
onShow(() => {
  const nextProfile = getProfile()
  planRevision.value++
  profile.value = nextProfile
  records.value = getRecords()
  caseId.value = getActiveHealthCaseId()
  if (!isDiabetesCase.value) {
    messages.value.forEach(message => {
      if (message.action !== 'plan') return
      const refreshed = todayPlan(profile.value, message.meal)
      message.bundles = createMealBundles(refreshed)
    })
  }
})
function ask(text) {
  const content = typeof text === 'string' ? text : input.value.trim()
  if (!content || thinking.value) return
  messages.value.push({ role: 'user', text: content })
  scrollToLatestReply()
  input.value = ''
  thinking.value = true
  setTimeout(() => {
    if (/头晕|出汗|手抖|疑似低血糖|低血糖怎么办/.test(content)) {
      messages.value.push({ role: 'assistant', safety: true, text: '这可能是低血糖等需要及时处理的情况。请立即停止当前菜单和购买操作；如果能够安全测量，请尽快测血糖，并按医生事先给出的处理方案处理。若意识不清、无法吞咽、症状严重或持续不缓解，请立即联系急救或就近就医。不要给意识不清的人喂食或喂水。' })
      thinking.value = false
      scrollToLatestReply()
      return
    }
    if (/糖尿病家庭怎么吃|糖尿病.*饮食建议|糖尿病.*怎么吃/.test(content)) {
      messages.value.push({
        role: 'assistant', healthAdvice: true,
        text: '糖尿病家庭饮食建议 · 演示\n\n1. 先确认健康信息\n如果成员有自报2型糖尿病，应先确认医生饮食要求、低血糖风险和肾脏相关情况；缺失信息不能默认正常。\n\n2. 全家可以同桌吃\n优先选择清淡烹饪，保证蔬菜和优质蛋白，把主食单独分份，不需要为一个人重新做整桌菜。\n\n3. 个人份量要分开\n糖尿病成员的主食先按较小份演示，具体数量仍以医生或营养师要求为准；其他成员使用常规份量。\n\n4. 继续观察与记录\n按时进餐，不因一次热量估算随意跳餐。照片只能辅助记录菜品和食量，不能判断血糖变化。\n\n这是一段固定案例建议，不会自动生成菜单、食材包或购买推荐。',
      })
      thinking.value = false
      scrollToLatestReply()
      return
    }
    if (isDiabetesCase.value && /爸爸.*糖尿病|糖尿病.*今晚|三个人今晚/.test(content)) {
      messages.value.push({
        role: 'assistant', caseStep: 'clarify',
        text: '我读取到爸爸档案中记录了2型糖尿病。目前低血糖风险为“不确定”，肾脏相关情况仍“未填写”。请确认：爸爸是否有医生指定的饮食方案，或近期出现过低血糖？',
        quickReplies: ['没有特别医嘱', '有医嘱，稍后补充', '不确定，先看通用建议'],
      })
      thinking.value = false
      scrollToLatestReply()
      return
    }
    const meal = /早餐|早上/.test(content) ? '早餐' : /午餐|中午/.test(content) ? '午餐' : '晚餐'
    const plan = todayPlan(profile.value,meal)
    let response
    if (/以后|长期|一直|喜欢|偏好|患有|有糖尿病|有高血压|有高血脂|有肾脏疾病/.test(content)) {
      const result=remember(content)
      if(result.question) response={text:result.question}
      else {profile.value=getProfile();planRevision.value++;response={text:'已记住 '+result.entry.member+' 的这条长期信息。可随时查看、修改或撤回。',processed:'memory',memoryId:result.entry.id,resultText:'已写入长期记忆：'+content}}
    } else if (/有点咸|太咸|偏咸/.test(content)) {
      if(lastRecord.value){updateRecord(lastRecord.value.id,{feedback:content});records.value=getRecords();response={text:'收到，只关联这一餐，不写入长期忌口。',processed:'feedback',feedbackRecordId:lastRecord.value.id,resultText:'已关联当餐反馈：'+content}}else response={text:'目前没有可关联的饮食记录，请先记录这一餐。'}
    } else if (/记录|总结/.test(content)) {
      response = { text: records.value.length ? '本机已有 ' + records.value.length + ' 条演示饮食记录。最新一条为 ' + (lastRecord.value.memberNames?.join('、') || lastRecord.value.memberName) + ' 的 ' + lastRecord.value.meal + (lastRecord.value.kcal ? '，约 ' + lastRecord.value.kcal + ' kcal（示例估算）' : '，已逐人确认菜品和粗略份量') + '。单次记录不足以判断健康变化；下一餐继续记录实际食量。' : '还没有饮食记录。可以先从“拍照记一餐”体验记录流程。', action: 'scan' }
    } else if (plan.blocked.length) {
      response = { text: plan.blocked.join('；') + '。目前暂停自动配餐；如需补充资料，请从“我的 → 我的家”进入家庭健康档案。请补充档案后重新进行 AI 饮食安全检查。', action: 'profile' }
    } else if (/吃|餐|菜|早|晚/.test(content)) {
      response = { text: '已先读取本餐成员的基础病、饮食目标及已知限制，完成演示分析。'+(plan.general?'资料未填写完整，以下仅为通用建议。':'')+'这是为 ' + plan.count + ' 位成人展示的' + meal + '样例：' + plan.dishes.map(d => d.name).join('、') + '。已沿用目标“' + profile.value.goals.join('、') + '”和口味“' + (profile.value.tastes.join('、') || '家常') + '”。食材量随人数合并，分餐页保留每个人的饮食关注。尚未接入真实 AI 与营养计算。', action: 'plan', meal }
    } else {
      response = { text: '当前可演示家庭早餐、午餐、晚餐、下单配送和饮食记录流程。试试问“今晚全家吃什么？”；自由问答将在接入 AI 服务后开放。' }
    }
    if (response.action === 'plan') { response.bundles = createMealBundles(plan); if(/明天|明日/.test(content)){saveTomorrowProposal(profile.value,meal);response.text+=' 已保存为明日提议。'} }
    messages.value.push({ role: 'assistant', ...response })
    thinking.value = false
    scrollToLatestReply()
  }, 450)
}
function answerCaseChoice(choice, message) {
  if (message?.caseChoiceAnswered) return
  if (message) message.caseChoiceAnswered = true
  messages.value.push({ role: 'user', text: choice })
  if (choice === '有医嘱，稍后补充') {
    messages.value.push({ role: 'assistant', text: '好的。为了避免计划与已有医嘱冲突，我先不生成菜单。请从“我的 → 我的家”进入家庭健康档案，补充爸爸的医生或营养师饮食要求后再回来继续。', action: 'profile' })
    scrollToLatestReply()
    return
  }
  const plan = createDiabetesCasePlan(profile.value, '晚餐')
  const prefix = choice === '不确定，先看通用建议' ? '以下只展示通用搭配思路，不替代医生或营养师的个体建议。\n\n' : ''
  messages.value.push({
    role: 'assistant', meal: '晚餐', caseStep: 'menu', bundles: createMealBundles(plan),
    text: prefix + '1. 已使用的档案\n已参考：爸爸的2型糖尿病记录、全家清淡口味、3人共同就餐。\n\n2. 一桌共享菜单\n清蒸鲈鱼、香菇青菜、番茄豆腐汤、杂粮饭。\n\n3. 每个人怎么吃\n全家可以吃同一桌菜。爸爸的主食先按较小份演示，蔬菜和蛋白质正常搭配；其他成员使用标准份。实际主食量仍应以医生或营养师要求为准。\n\n4. 下一步操作',
    caseActions: [
      { label: '查看本餐菜单', type: 'portion' },
      { label: '换一道菜', type: 'swap' },
      { label: '购买食材包', type: 'buy' },
    ],
  })
  scrollToLatestReply()
}
function handleCaseAction(type) {
  if (type === 'portion') go('/pages/shop/index?meal=dinner&case=diabetes')
  else if (type === 'buy') go('/pages/shop/index?meal=dinner&case=diabetes')
  else {
    messages.value.push({ role: 'assistant', text: '已记录“换一道菜”的需求。完整版本会重新检查家庭档案与过敏原后给出替换菜；当前案例继续使用原菜单演示后续闭环。' })
    scrollToLatestReply()
  }
}
function voice() {
  uni.showModal({ title: '语音输入演示', content: '尚未接入录音与语音转写。是否使用示例句“今晚全家吃什么”？', confirmText: '使用示例', success: r => { if(r.confirm) ask('今晚全家吃什么？') } })
}
function go(url) { uni.navigateTo({ url }) }
function openDailyMeal(item) {
  go('/pages/shop/index?meal=' + item.route + (isDiabetesCase.value && item.name === '晚餐' ? '&case=diabetes' : ''))
}
function openShop(message, bundleId = '') {
  const meal = mealToRoute(message.meal)
  go((bundleId ? '/pages/shop/detail?meal=' : '/pages/shop/index?meal=') + meal + (isDiabetesCase.value && message.meal === '晚餐' ? '&case=diabetes' : '') + (bundleId ? '&bundle=' + encodeURIComponent(bundleId) : ''))
}
function openAction(message) {
  if (message.action === 'plan') go('/pages/shop/index?meal=' + mealToRoute(message.meal) + (isDiabetesCase.value && message.meal === '晚餐' ? '&case=diabetes' : ''))
  else if (message.action === 'profile') go('/pages/my/index')
  else go('/pages/scan/index')
}
function showHistory() { go('/pages/chat/history') }
function changeDiners(item){dinerMeal.value=item.name;dinersOpen.value=true}
function confirmDiners(ids){const before=selectedDinerPlan.value;setMealMembers(profile.value,dinerMeal.value,ids);planRevision.value++;updateNote.value=changeResult(before,selectedDinerPlan.value);dinersOpen.value=false}
function supplementPostMeal() {
  uni.showModal({ title: '补充餐后记录', content: '本原型不会从照片推断血糖。正式版可由用户主动填写餐后测量时间与数值，并注明单位和场景。', showCancel: false })
}
function openProcessed(message){ if(message.processed==='memory')go('/pages/memories/index'); else go('/pages/feedback/index') }
function undoProcessed(message){if(message.memoryId){forget(message.memoryId);profile.value=getProfile();planRevision.value++}if(message.feedbackRecordId){updateRecord(message.feedbackRecordId,{feedback:''});records.value=getRecords()} message.resultText='已撤回本次写入';message.processed='undone';uni.showToast({title:'已撤回',icon:'success'}) }
</script>

<template>
<view class="screen chat-screen">
  <AppNavBar><view class="nav-row chat-nav"><button class="history-button" aria-label="查询历史记录" @click="showHistory"><AppIcon name="history" :size="40"/></button><view class="assistant-title"><text>家庭营养师</text><text class="nav-subtitle">你的家庭饮食伙伴</text></view><button class="me-button" aria-label="进入我的页面" @click="go('/pages/my/index')"><AppIcon name="user" :size="40"/></button></view></AppNavBar>
  <scroll-view class="conversation" scroll-y :scroll-into-view="scrollTarget">
    <view class="today-card"><view class="today-top"><view><text class="eyebrow">{{today.getMonth()+1}}月{{today.getDate()}}日 · 今日安排</text><text class="section-title">好好吃饭，从今天开始</text></view><text class="test-badge">测试数据</text></view><view class="today-meals"><view v-for="item in dailyPlans" :key="item.route" class="daily-meal-row"><view class="meal-card-head"><text class="meal-name">{{item.name}}</text><button class="diner-capsule" @click="changeDiners(item)"><AppIcon name="family" :size="26"/> {{item.plan.count}}人用餐</button></view><text class="meal-summary">{{item.summary}}</text><view class="meal-foot"><text class="meal-source">{{item.plan.source}}</text><button class="meal-link" @click="openDailyMeal(item)">查看本餐安排 &gt;</button></view></view></view><button v-if="!hasActivePaidPlan" class="daily-buy" @click="go('/pages/shop/index?daily=1')">一键采购 <text>↗</text></button></view>
    <text v-if="updateNote" class="update-note">{{updateNote}}</text>
    <view v-if="lastRecord" class="feedback-card card"><text class="section-title">这一餐，已经记好了</text><text>{{lastRecord.memberNames?.join('、')||lastRecord.memberName}} · {{lastRecord.meal}}</text><button class="message-action" @click="go('/pages/feedback/index')">查看饮食反馈 →</button></view>
    <view class="message-list"><view v-if="!messages.length" class="welcome-message"><view class="welcome-symbol"><AppIcon name="chat" :size="54"/></view><text class="welcome-title">今天，想怎么吃？</text><text>你好，{{nameList}}。告诉我你想吃什么，
我们一起安排适合家人的三餐。</text></view>
      <view v-for="(message,index) in messages" :id="'message-'+index" :key="index" class="message-group"><view class="message-row" :class="message.role"><view v-if="message.role==='assistant'" class="ai-avatar"><AppIcon name="chat" :size="28"/></view><view class="bubble" :class="{'safety-bubble':message.safety}"><text class="bubble-copy">{{message.text}}</text><view v-if="message.quickReplies&&!message.caseChoiceAnswered" class="case-quick-replies"><button v-for="choice in message.quickReplies" :key="choice" @click="answerCaseChoice(choice,message)">{{choice}}</button></view><view v-if="message.caseActions" class="case-actions"><button v-for="action in message.caseActions" :key="action.type" @click="handleCaseAction(action.type)">{{action.label}}</button></view><button v-if="message.action" class="message-action" :class="{'menu-link':message.action==='plan'}" @click="openAction(message)">{{message.action==='plan'?'查看'+message.meal+'菜单':message.action==='profile'?'前往“我的”':'拍照记一餐'}} →</button></view></view><MealBundleRecommendations v-if="message.bundles" :bundles="message.bundles" :meal="message.meal" @open="openShop(message,$event)" @all="openShop(message)"/><view v-if="message.processed" class="processing-result card"><text class="eyebrow">本次处理结果</text><text>{{message.resultText}}</text><view v-if="message.processed!=='undone'"><button @click="openProcessed(message)">{{message.processed==='memory'?'查看记忆':'查看反馈'}}</button><button @click="undoProcessed(message)">撤回</button></view></view></view>
      <view v-if="thinking" class="message-row"><view class="ai-avatar"><AppIcon name="chat" :size="28"/></view><view class="bubble thinking">正在整理本餐建议…</view></view>
    </view><view class="quick-prompts"><button v-for="prompt in prompts" :key="prompt" @click="ask(prompt)">{{prompt}}</button></view>
    <view v-if="inlineTodayOpen" class="inline-today card"><view><text class="section-title">今日饮食计划</text><button @click="inlineTodayOpen=false">收起</button></view><button v-for="item in dailyPlans" :key="item.route" @click="openDailyMeal(item)"><text>{{item.name}}</text><text>{{item.summary}}</text><text>›</text></button></view><view class="conversation-spacer"></view>
  </scroll-view>
  <view class="composer-wrap"><scroll-view class="tool-strip" scroll-x :show-scrollbar="false"><view class="tool-row">
    <button class="tool-chip exclusive-plan-entry" @click="go('/pages/exclusive-plans/index')"><AppIcon name="calendar" :size="28"/><text>AI专属计划</text></button><view class="tool-divider"></view>
    <button class="tool-chip" @click="go('/pages/profile/index')"><AppIcon name="family" :size="28"/><text>家庭健康档案</text></button><view class="tool-divider"></view>
    <button class="tool-chip" @click="go('/pages/scan/index')"><AppIcon name="camera" :size="28"/><text>拍照看热量</text></button><view class="tool-divider"></view>
    <button class="tool-chip" @click="inlineTodayOpen=!inlineTodayOpen"><AppIcon name="record" :size="28"/><text>今日饮食计划</text></button><view class="tool-divider"></view>
    <button class="tool-chip" @click="communityOpen=true"><AppIcon name="chat" :size="28"/><text>加入社群</text></button>
  </view></scroll-view><view class="composer"><button class="camera-button" aria-label="拍照记一餐" @click="go('/pages/scan/index')"><AppIcon name="camera" :size="38"/></button><input v-model="input" placeholder="问问家庭营养师…" confirm-type="send" @confirm="ask()"/><button v-if="input.trim()" class="send-button" aria-label="发送" @click="ask()"><AppIcon name="arrow" :size="30"/></button><button v-else class="voice-button" aria-label="语音演示" @click="voice"><AppIcon name="mic" :size="36"/></button></view><text class="safe-note">AI 回复与营养数值为测试数据 · 膳食建议仅供参考</text></view>
  <DinerPicker :open="dinersOpen" :members="profile.members" :selected="selectedDinerPlan.members.map(m=>m.id)" :meal="dinerMeal" @close="dinersOpen=false" @confirm="confirmDiners"/>
  <view v-if="communityOpen" class="sheet-mask" @click.self="communityOpen=false"><view class="sheet community-sheet"><view class="community-head"><text class="section-title">加入社群</text><button @click="communityOpen=false">×</button></view><view class="qr-placeholder">二维码待运营配置</view><text class="safe-note">暂无可用社群二维码，请稍后再试</text></view></view>
</view>
</template>
<style scoped>
.chat-screen{height:100vh;display:flex;flex-direction:column;background:#fff;padding-bottom:calc(env(safe-area-inset-bottom) + 12rpx)}.chat-nav{flex-shrink:0}.history-button,.me-button{width:72rpx;height:80rpx;display:flex;align-items:center;justify-content:center}.assistant-title{text-align:center;display:flex;flex-direction:column;gap:4rpx;min-width:0}.assistant-title>text:first-child{font-size:32rpx;font-weight:600}.nav-subtitle{font-size:21rpx;color:#767680}.conversation{flex:1;min-height:0}.today-card{margin-top:20rpx;padding:28rpx;border-radius:30rpx;background:#f5f5f7}.today-top{display:flex;justify-content:space-between;align-items:flex-start;gap:12rpx}.today-top .section-title{font-size:34rpx}.test-badge{font-size:20rpx;color:#767680;white-space:nowrap}.today-meals{margin-top:16rpx}.daily-meal-row{padding:20rpx 0;border-top:1rpx solid #e5e5ea}.daily-meal-row:first-child{border:0}.meal-card-head{display:flex;justify-content:space-between;align-items:center}.meal-name{font-size:29rpx;font-weight:600}.diner-capsule{display:flex;gap:8rpx;align-items:center;justify-content:center;min-height:84rpx;padding:0 20rpx;border:1rpx solid #e0e0e5;background:#fff;border-radius:999rpx;font-size:24rpx;color:#246b50}.meal-summary{display:block;font-size:26rpx;margin-top:4rpx;line-height:1.5}.meal-foot{display:flex;justify-content:space-between;align-items:center;gap:12rpx}.meal-source{font-size:21rpx;color:#767680}.meal-link{font-size:24rpx;min-height:72rpx;color:#246b50}.daily-buy{display:flex;gap:16rpx;margin-left:auto!important;align-items:center;background:#1d1d1f;color:white;border-radius:18rpx;padding:16rpx 24rpx;min-height:80rpx;font-size:26rpx}.welcome-message{display:flex;flex-direction:column;align-items:center;text-align:center;padding:56rpx 16rpx 36rpx;gap:20rpx}.welcome-symbol{height:96rpx;width:96rpx;border-radius:30rpx;background:#eaf2ed;color:#246b50;display:flex;align-items:center;justify-content:center}.welcome-title{font-size:40rpx;font-weight:600}.welcome-message>text:last-child{font-size:27rpx;color:#63636b;line-height:1.7;white-space:pre-line}.message-list{padding-top:20rpx}.message-row{display:flex;align-items:flex-start;gap:14rpx;margin:24rpx 0}.message-row.user{justify-content:flex-end;padding-left:60rpx}.ai-avatar{width:52rpx;height:52rpx;display:flex;align-items:center;justify-content:center;border-radius:18rpx;background:#eaf2ed;color:#246b50;flex-shrink:0}.bubble{max-width:570rpx;padding:24rpx;border-radius:4rpx 24rpx 24rpx;background:#f5f5f7;font-size:28rpx;line-height:1.75}.bubble-copy{white-space:pre-line}.user .bubble{border-radius:24rpx 4rpx 24rpx 24rpx;background:#eaf2ed}.safety-bubble{background:#fff2ee;color:#a3392c}.message-action{display:block;padding:18rpx 0;font-size:27rpx;color:#246b50;min-height:80rpx;text-align:left}.processing-result{margin:0 0 22rpx 66rpx;padding:24rpx;font-size:26rpx;line-height:1.6}.processing-result>text{display:block}.processing-result>view{display:flex;gap:28rpx}.processing-result button{color:#246b50;min-height:80rpx}.processing-result button:last-child{color:#a3392c}.quick-prompts{display:flex;flex-direction:column;gap:14rpx;padding:16rpx 0 32rpx}.quick-prompts button{width:100%;box-sizing:border-box}.quick-prompts button,.case-quick-replies button,.case-actions button{min-height:80rpx;padding:16rpx 22rpx;border:1rpx solid #e5e5ea;border-radius:18rpx;font-size:26rpx;text-align:left;background:#fff}.inline-today{padding:24rpx}.inline-today>view,.inline-today>button{display:flex;justify-content:space-between;gap:20rpx;width:100%;font-size:26rpx}.inline-today>button{padding:24rpx 0;border-top:1rpx solid #e5e5ea}.inline-today>view{margin-bottom:20rpx}.conversation-spacer{height:32rpx}.composer-wrap{padding-top:14rpx;background:#fff;border-top:1rpx solid #f0f0f3}.tool-strip{width:calc(100% + 32rpx);white-space:nowrap;margin-bottom:16rpx}.tool-row{display:inline-flex;gap:12rpx;padding-right:32rpx;align-items:center}.tool-chip{display:inline-flex;align-items:center;gap:8rpx;min-height:76rpx;padding:12rpx 18rpx;border:1rpx solid #e5e5ea;border-radius:18rpx;background:#fff;color:#3c3c43;font-size:23rpx}.tool-divider{display:none}.tool-chip,.tool-divider { flex-shrink: 0; }.composer{display:flex;align-items:center;gap:12rpx;padding:12rpx;border:1rpx solid #dedee3;border-radius:24rpx;background:#fafafa}.composer input{flex:1;min-width:0;height:68rpx;font-size:29rpx}.camera-button,.voice-button,.send-button{width:68rpx;height:68rpx;display:flex;align-items:center;justify-content:center;color:#63636b;flex-shrink:0}.send-button{border-radius:50%;background:#1d1d1f;color:#fff}.composer-wrap .safe-note{font-size:20rpx;margin-top:12rpx}.feedback-card{padding:28rpx;margin:24rpx 0}.feedback-card>text{display:block;margin-top:12rpx;font-size:28rpx}.community-head{display:flex;justify-content:space-between}.community-head button{font-size:40rpx;min-height:80rpx}.qr-placeholder{width:320rpx;height:320rpx;background:#f5f5f7;margin:36rpx auto;display:flex;align-items:center;justify-content:center;color:#767680;font-size:26rpx;border-radius:24rpx}.update-note{display:block;padding:24rpx;background:#eaf2ed;margin:24rpx 0;border-radius:22rpx;font-size:26rpx;line-height:1.6}
</style>
