<script setup>
import { computed, reactive, ref } from 'vue'
import { onLoad, onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import { createHealthPlanClient, healthPlanState } from '../../services/health-plan-client.js'
import { archiveCard, archiveDate, plannedGrams } from '../../services/meal-archive-presentation.js'
const selectedPlanId = ref(''), view = ref('list'), reviewExpanded = ref(false)
const state = reactive(healthPlanState()), memberId = ref(''), replace = ref(false), reason = ref('')
const client = createHealthPlanClient({ state })
const reviewNames = { approved: '已专业批准', not_reviewed: '尚未专业审核', submitted: '待审核', returned: '需补充资料', invalidated: '原批准已失效' }
const meals = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }
const cards = computed(() => state.plans.map(plan => archiveCard(plan)))
const selectedMember = computed(() => state.members.find(member => member.id === state.memberId))
const detailDate = computed(() => archiveDate(state.plan?.plan_date))
const reviewLabel = computed(() => state.adoption?.current ? '已正式采用' : state.approval?.available
  ? '可正式采用' : reviewNames[state.approval?.professional_review] || '尚未专业审核')
const locked = computed(() => state.busy || !!state.pending)
let visibility = 0
function resetActions() { replace.value = false; reason.value = ''; reviewExpanded.value = false }
async function load() {
  const current = ++visibility
  resetActions()
  await client.open(memberId.value)
  if (current !== visibility) return
  if (state.memberId) memberId.value = state.memberId
  if (selectedPlanId.value && !state.pending && state.memberId) await client.detail(selectedPlanId.value)
}
onLoad(options => {
  memberId.value = options.memberId || ''; selectedPlanId.value = options.planId || ''
  view.value = selectedPlanId.value ? 'detail' : 'list'
})
onShow(load)
function clear() { visibility++; client.discard(); resetActions() }
onHide(clear); onUnload(clear)
function top() { uni.pageScrollTo({ scrollTop: 0, duration: 0 }) }
function select(plan) {
  if (locked.value) return
  resetActions(); selectedPlanId.value = typeof plan === 'string' ? plan : plan.plan_id
  view.value = 'detail'; top(); return client.detail(selectedPlanId.value)
}
function back() {
  if (view.value === 'detail') { view.value = 'list'; selectedPlanId.value = ''; resetActions(); top() }
  else uni.navigateBack()
}
function changeMember(id) {
  if (locked.value) return
  memberId.value = id; selectedPlanId.value = ''; view.value = 'list'; return load()
}
async function retry() {
  const current = visibility
  await client.retry()
  if (current === visibility && state.plan) {
    selectedPlanId.value = state.plan.plan_id; view.value = 'detail'; reviewExpanded.value = true; top()
  }
}
function chat() { if (!locked.value) uni.navigateTo({ url: '/pages/chat/index' }) }
</script>
<template>
  <view class="screen meal-archive">
    <AppNavBar><view class="nav-row"><button class="mra-back" :aria-label="view==='detail'?'返回餐单列表':'返回'" @click="back">‹</button><text class="nav-title">{{view==='detail'?'餐单详情':'我的餐单'}}</text></view></AppNavBar>
    <view v-if="view==='list'" class="mra-heading">
      <text>好好吃饭，</text><text>每一餐都有迹可循。</text>
    </view>

    <view v-if="state.members.length>1" class="mra-members" aria-label="选择餐单成员">
      <button v-for="member in state.members" :key="member.id" :class="{chosen:state.memberId===member.id}" :aria-pressed="state.memberId===member.id" :disabled="locked" @click="changeMember(member.id)">{{member.display_name||'家庭成员'}}</button>
    </view>
    <view v-if="state.error" class="mra-alert" role="alert">
      <text>{{state.error}}</text><button :disabled="locked" @click="load">重新读取</button>
    </view>
    <text v-if="state.notice" class="mra-notice" role="status">{{state.notice}}</text>
    <view v-if="state.pending" class="mra-recovery">
      <text class="mra-section-title">上次操作还需核对</text>
      <text class="mra-caption">采用或取消的结果尚未确认，请先核对原操作。</text>
      <button class="mra-primary" :disabled="state.busy" @click="retry">核对并重试原操作<text>→</text></button>
    </view>

    <template v-if="view==='list'">
      <view class="mra-section-heading">
        <text class="mra-section-title">已保存餐单</text>
        <text class="mra-meta">{{state.members.length>1?selectedMember?.display_name:''}}{{state.plans.length?(state.members.length>1?' · ':'')+'本页'+state.plans.length+'份':''}}</text>
      </view>
      <text v-if="state.busy" class="mra-loading" role="status">正在读取餐单…</text>
      <view v-for="card in cards" :key="card.plan.plan_id" class="mra-card">
        <view class="mra-card-heading"><view><text class="mra-caption">{{card.date.caption}}</text><text class="mra-card-title">{{card.title}}</text></view><text class="mra-badge">已保存</text></view>
        <view v-for="meal in card.meals" :key="meal.type" class="mra-meal-row"><text class="mra-meal-label">{{meal.name}}</text><text class="mra-meal-names">{{meal.summary}}</text></view>
        <view class="mra-card-footer"><text class="mra-caption">{{card.summary}}</text><button class="mra-link" :disabled="locked" @click="select(card.plan)">查看餐单<text>→</text></button></view>
      </view>
      <view v-if="!state.plans.length&&!state.busy&&!state.error&&!state.pending&&state.memberId" class="mra-empty">

        <text class="mra-empty-title">第一份餐单，从今天开始</text>
        <text class="mra-caption">还没有保存的餐单。<br/>和营养师聊聊，为自己安排一日三餐。</text>
        <button class="mra-primary" @click="chat">和营养师聊聊<text>→</text></button>
      </view>
      <view v-if="!state.members.length&&!state.busy&&!state.error" class="mra-empty">
        <text class="mra-empty-title">暂时没有可查看的成员</text>
        <button class="mra-primary" @click="load">重新读取成员与餐单<text>→</text></button>
      </view>
      <view v-if="state.offset>0||state.nextOffset!==null" class="mra-pagination">
        <button :disabled="locked||state.offset===0" @click="client.page(Math.max(0,state.offset-20))">上一页</button><button :disabled="locked||state.nextOffset===null" @click="client.page(state.nextOffset)">下一页</button>
      </view>
      <button v-if="state.memberId&&(state.plans.length||state.offset>0)&&!state.pending" class="mra-refresh" :disabled="state.busy" @click="client.page(state.offset)">刷新列表</button>
    </template>

    <template v-else>
      <text v-if="state.busy" class="mra-loading" role="status">正在核对餐单与使用状态…</text>
      <view v-if="state.plan" class="mra-card mra-detail">
        <view class="mra-card-heading"><view><text class="mra-caption">{{detailDate.caption}}</text><text class="mra-card-title">{{detailDate.title}}的餐单</text></view><text class="mra-badge">已保存</text></view>
        <view v-for="meal in state.plan.meals||[]" :key="meal.meal_type" class="mra-detail-meal">
          <text class="mra-detail-label">{{meals[meal.meal_type]||meal.meal_type}}</text>
          <view v-for="(dish,index) in meal.dishes||[]" :key="index" class="mra-dish"><text>{{dish.name}}</text><text class="mra-caption">{{plannedGrams(dish.planned_grams)}}</text></view>
          <text v-if="!meal.dishes?.length" class="mra-caption">本餐未记录</text>
        </view>
        <view v-for="(person,id) in state.plan.members||{}" :key="id" class="mra-person">
          <text class="mra-person-title">{{state.members.find(m=>m.id===id)?.display_name||'共餐成员'}} · 个人计划份量</text>
          <view v-for="meal in person.meals||[]" :key="meal.meal_type"><text class="mra-caption">{{meals[meal.meal_type]||meal.meal_type}}：{{meal.dishes?.map(d=>d.name+' '+plannedGrams(d.planned_grams)).join('、')||'本餐未记录'}}</text></view>
        </view>
        <view class="mra-nutrition"><text class="mra-caption">计划热量</text><text>{{state.plan.nutrition?.totals?.energy_kcal??'未知'}}<text class="mra-caption"> kcal</text></text></view>
        <view class="mra-review">
          <button class="mra-review-toggle" :aria-expanded="reviewExpanded" @click="reviewExpanded=!reviewExpanded"><view><text>餐单状态与版本</text><text class="mra-caption">{{reviewLabel}}</text></view><text>{{reviewExpanded?'收起':'展开'}} ›</text></button>
          <view v-if="reviewExpanded" class="mra-review-body">
            <text class="mra-caption">保存版本：第{{state.plan.version}}版</text>
            <text class="mra-caption">专业状态：{{state.approval?.available?'当前专业批准有效':reviewNames[state.approval?.professional_review]||'尚无当前有效专业批准'}}</text>
            <text class="mra-caption">采用状态：{{state.adoption?.current?'已正式采用':'本餐单尚未正式采用'}}</text>
            <template v-if="!state.adoption?.current">
              <text v-if="!state.approval?.available" class="mra-caption">需当前餐单版本通过专业批准后才能采用。</text>
              <template v-if="state.previous.length">
                <text class="mra-person-title">将被替代的当日采用</text>
                <text v-for="old in state.previous" :key="old.adoption_id" class="mra-caption">{{old.plan_date}} · 餐单第{{old.plan_version}}版 · 涉及{{old.member_ids?.length||1}}位成员</text>
                <label class="mra-replace"><switch :checked="replace" :disabled="locked" @change="replace=$event.detail.value"/>我确认整体替代上述当日采用</label>
              </template>
              <button class="mra-primary" :disabled="locked||state.blocked||!state.approval?.available||(state.previous.length&&!replace)" @click="client.adopt(replace)">确认正式采用当前批准版本</button>
            </template>
            <template v-else>
              <textarea v-model="reason" class="text-area" maxlength="500" placeholder="填写取消采用原因" :disabled="locked"/>
              <button class="secondary-button" :disabled="locked||!reason.trim()" @click="client.withdraw(reason)">确认取消这份采用</button>
              <text class="mra-caption">取消保留历史，实际饮食记录不随之删除。</text>
            </template>
            <button class="mra-link mra-detail-refresh" :disabled="locked" @click="select(state.plan)">重新核对餐单与批准</button>
          </view>
        </view>
      </view>
      <button class="mra-refresh" @click="back">返回餐单列表</button>
    </template>
    <text class="mra-bottom-note">餐单记录计划，实际吃了什么可在饮食记录中查看。</text>
  </view>
</template>

<style>
/* mra-* classes are unique to this page. */
.meal-archive{padding:0 40rpx calc(48rpx + env(safe-area-inset-bottom));color:#353b46;background:#f5f6fa;background-image:radial-gradient(ellipse at 0% 0%,rgba(125,174,255,.44),transparent 70%),radial-gradient(ellipse at 100% 0%,rgba(206,178,245,.38),transparent 76%);background-size:100% 410rpx;background-repeat:no-repeat}
.mra-back{width:80rpx;min-height:80rpx;text-align:left;color:#667182;font-size:60rpx;line-height:1.3}
.mra-heading{display:flex;flex-direction:column;padding:16rpx 6rpx 54rpx;font-size:54rpx;font-weight:700;line-height:1.38;letter-spacing:-.8rpx}
.mra-section-heading,.mra-card-heading,.mra-card-footer,.mra-nutrition{display:flex;align-items:center;justify-content:space-between;gap:24rpx}
.mra-section-heading{margin:0 6rpx 30rpx}.mra-section-title{font-size:40rpx;font-weight:600;flex-shrink:0}.mra-meta{max-width:48%;font-size:22rpx;color:#747e8d;text-align:right;overflow-wrap:anywhere}
.mra-card,.mra-empty{padding:44rpx 42rpx;border-radius:48rpx;background:#fff}.mra-card{margin-bottom:32rpx}.mra-card-heading{margin-bottom:36rpx}.mra-card-heading>view{min-width:0}.mra-card-title{display:block;margin-top:8rpx;font-size:38rpx;font-weight:600;overflow-wrap:anywhere}
.mra-caption{display:block;color:#747e8d;font-size:23rpx;line-height:1.85;overflow-wrap:anywhere}.mra-badge{flex-shrink:0;padding:10rpx 16rpx;border-radius:16rpx;background:#edf2fc;color:#476fc3;font-size:22rpx}
.mra-meal-row{display:flex;gap:26rpx;padding:22rpx 0;font-size:26rpx;line-height:1.8}.mra-meal-label{flex-shrink:0;color:#747e8d}.mra-meal-names{min-width:0;overflow-wrap:anywhere}
.mra-card-footer{margin-top:32rpx;padding-top:26rpx;border-top:1rpx solid #eef1f6}.mra-link,.mra-refresh{display:flex;align-items:center;justify-content:center;min-height:88rpx;font-size:25rpx;color:#476fc3}.mra-link{gap:24rpx}.mra-link>text{font-size:32rpx}.mra-refresh{margin:4rpx auto 0;padding:16rpx 24rpx;color:#788aa6}
.mra-empty{padding-top:64rpx;padding-bottom:48rpx;text-align:center}.mra-empty-title{display:block;margin-bottom:20rpx;font-size:34rpx;font-weight:500}
.mra-primary{display:flex;align-items:center;justify-content:space-between;gap:20rpx;min-height:96rpx;margin-top:40rpx;padding:24rpx 34rpx;border-radius:28rpx;background:linear-gradient(135deg,#e2efff,#c9ddfb 50%,#b9cdf3);box-shadow:inset 0 2rpx 5rpx #fff9,0 6rpx 18rpx #7896c824;color:#31588f;font-size:28rpx}.mra-primary>text{font-size:36rpx}
.mra-bottom-note{display:block;margin:32rpx 14rpx 0;color:#747e8d;text-align:center;font-size:22rpx;line-height:1.8}
.mra-pagination,.mra-members{display:flex;gap:24rpx}.mra-pagination{margin-top:24rpx}.mra-pagination button{flex:1;min-height:88rpx;padding:18rpx 24rpx;border-radius:22rpx;background:#fff;color:#476fc3;font-size:26rpx}
.mra-members{flex-wrap:wrap;gap:16rpx;margin:0 6rpx 32rpx}.mra-members button{max-width:100%;min-height:88rpx;padding:18rpx 28rpx;border-radius:24rpx;background:#e9eef7;color:#69778c;font-size:26rpx;overflow-wrap:anywhere;text-align:left}.mra-members button.chosen{background:#fff;color:#476fc3;box-shadow:0 6rpx 18rpx #3e578012}
.mra-alert,.mra-recovery{display:flex;flex-direction:column;gap:20rpx;padding:32rpx;margin-bottom:32rpx;border-radius:32rpx;background:#fff;font-size:27rpx;overflow-wrap:anywhere}.mra-alert>text{color:#a53936}.mra-alert>button{align-self:flex-start;min-height:88rpx;color:#476fc3;font-size:26rpx}.mra-recovery .mra-section-title{font-size:32rpx}.mra-recovery .mra-primary{margin-top:8rpx}
.mra-notice,.mra-loading{display:block;margin:12rpx 6rpx 28rpx;color:#69778c;font-size:26rpx;line-height:1.8}
.mra-detail{margin-top:16rpx}.mra-detail-meal,.mra-person{padding:28rpx 0;border-top:1rpx solid #eef1f6}.mra-detail-label{display:block;margin-bottom:18rpx;color:#476fc3;font-size:24rpx}.mra-dish{display:flex;align-items:baseline;justify-content:space-between;gap:24rpx;padding:8rpx 0;font-size:28rpx}.mra-dish>text:first-child{min-width:0;overflow-wrap:anywhere}.mra-dish>.mra-caption{flex-shrink:0}.mra-person-title{display:block;margin-bottom:14rpx;font-size:27rpx;font-weight:500}
.mra-nutrition{padding:26rpx 0;border-top:1rpx solid #eef1f6;font-size:30rpx}.mra-nutrition .mra-caption{display:inline}
.mra-review{border-top:1rpx solid #eef1f6}.mra-review-toggle{display:flex;align-items:center;justify-content:space-between;gap:20rpx;width:100%;min-height:100rpx;padding:28rpx 0;text-align:left;font-size:27rpx}.mra-review-toggle .mra-caption{margin-top:10rpx}.mra-review-toggle>text{flex-shrink:0;color:#788aa6;font-size:23rpx}.mra-review-body{display:flex;flex-direction:column;gap:16rpx}.mra-review-body .mra-primary{justify-content:center;margin-top:18rpx}.mra-replace{display:flex;align-items:center;gap:12rpx;font-size:25rpx}
@media(max-width:350px){.meal-archive{padding-left:28rpx;padding-right:28rpx}.mra-heading{font-size:48rpx}.mra-card{padding:42rpx 34rpx}.mra-meal-row{gap:20rpx;font-size:25rpx}.mra-section-title{font-size:37rpx}}
</style>
