<script setup>
import { reactive, ref } from 'vue'
import { onLoad, onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import { createHealthPlanClient, healthPlanState } from '../../services/health-plan-client.js'
const initialPlan=ref('');
const state = reactive(healthPlanState()), memberId = ref(''), replace = ref(false), reason = ref('')
const client = createHealthPlanClient({ state })
const reviewNames = { approved: '已专业批准', not_reviewed: '尚未专业审核', submitted: '待审核', returned: '需补充资料', invalidated: '原批准已失效' }
const meals = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }
onLoad(options => { memberId.value = options.memberId || '';initialPlan.value=options.planId||'' })
onShow(() => { replace.value = false; reason.value = ''; void client.open(memberId.value).then(()=>{const plan=state.plans.find(p=>p.plan_id===initialPlan.value);if(plan)void client.detail(plan)}) })
onHide(() => client.discard()); onUnload(() => client.discard())
function select(row) { replace.value = false; reason.value = ''; void client.detail(row) }
</script>
<template>
  <view class="screen health-plans"><AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack()">‹</button><text class="nav-title">餐单与正式采用</text></view></AppNavBar>
    <view class="page-heading"><text class="display-title">核对好，再采用</text><text class="subtitle">草稿保存、专业批准、正式采用和实际摄入分别记录。</text></view>
    <text v-if="state.error" class="inline-error">{{state.error}}</text><text v-if="state.notice" class="safe-note">{{state.notice}}</text><text v-if="state.busy" class="safe-note">正在重新核对服务端餐单与批准…</text>
    <button v-if="!state.members.length" class="secondary-button" :disabled="state.busy" @click="client.open(memberId)">重新读取成员与餐单</button>
    <view class="choices"><button v-for="member in state.members" :key="member.id" :class="{active:state.memberId===member.id}" :disabled="state.busy||!!state.pending" @click="replace=false;client.open(member.id)">{{member.display_name}}</button></view>
    <view v-if="state.pending" class="card section"><text>上次操作结果尚未确认，请先恢复原请求。</text><button class="primary-button" :disabled="state.busy" @click="client.retry()">核对并重试原采用 / 取消操作</button></view>
    <view class="card section"><text class="section-title">已保存餐单</text><text v-if="!state.plans.length&&!state.busy&&!state.error" class="helper">本页暂无服务端已保存餐单。</text><button v-for="plan in state.plans" :key="plan.plan_id" class="plan-row" :disabled="state.busy||!!state.pending" @click="select(plan)"><text>{{plan.plan_date}} · v{{plan.version}}</text><text>查看草稿、专业状态与当前采用 ›</text></button><view class="choices"><button :disabled="state.busy||!!state.pending||state.offset===0" @click="client.page(Math.max(0,state.offset-20))">上一页</button><button :disabled="state.busy||!!state.pending||state.nextOffset===null" @click="client.page(state.nextOffset)">下一页</button><button :disabled="state.busy||!!state.pending" @click="client.page()">刷新列表</button></view></view>
    <view v-if="state.plan" class="card section"><text class="section-title">{{state.plan.plan_date}} · 餐单 v{{state.plan.version}}</text><text class="helper">专业状态：{{state.approval?.available?'当前专业批准有效':reviewNames[state.approval?.professional_review]||'尚无当前有效专业批准'}}</text><text class="helper">采用状态：{{state.adoption?.current?'已正式采用':'本餐单尚未正式采用'}}</text>
      <view v-for="meal in state.plan.meals||[]" :key="meal.meal_type" class="meal"><text class="section-title">{{meals[meal.meal_type]}}</text><text v-for="(dish,index) in meal.dishes" :key="index">{{dish.name}} · {{dish.planned_grams??'份量未知'}}{{dish.planned_grams?'g':''}}</text></view>
      <view v-for="(person,id) in state.plan.members||{}" :key="id" class="meal"><text>{{state.members.find(m=>m.id===id)?.display_name||'共餐成员'}} · 个人计划份量</text><view v-for="meal in person.meals||[]" :key="meal.meal_type"><text>{{meals[meal.meal_type]}}：{{meal.dishes?.map(d=>d.name+' '+(d.planned_grams??'未知')+'g').join('、')}}</text></view></view>
      <text class="helper">计划营养：{{state.plan.nutrition?.totals?.energy_kcal??'未知'}} kcal；计划不自动记为已吃。</text>
      <template v-if="!state.adoption?.current"><text v-if="!state.approval?.available" class="safe-note">需当前餐单版本通过专业批准后才能采用。</text><template v-if="state.previous.length"><text class="section-title">将被替代的当日采用</text><text v-for="old in state.previous" :key="old.adoption_id" class="helper">{{old.plan_date}} · 餐单 v{{old.plan_version}} · 涉及{{old.member_ids?.length||1}}位成员</text><label><switch :checked="replace" :disabled="state.busy||!!state.pending" @change="replace=$event.detail.value"/>我确认整体替代上述当日采用</label></template><button class="primary-button" :disabled="state.busy||!!state.pending||state.blocked||!state.approval?.available||(state.previous.length&&!replace)" @click="client.adopt(replace)">确认正式采用当前批准版本</button></template>
      <template v-else><textarea v-model="reason" class="text-area" maxlength="500" placeholder="填写取消采用原因" :disabled="state.busy||!!state.pending"/><button class="secondary-button" :disabled="state.busy||!!state.pending||!reason.trim()" @click="client.withdraw(reason)">确认取消这份采用</button><text class="helper">取消保留历史，实际饮食记录不随之删除。</text></template>
      <button class="secondary-button" :disabled="state.busy||!!state.pending" @click="select(state.plan)">重新读取当前餐单与批准</button>
    </view>
  </view>
</template>
<style scoped>.health-plans{padding-bottom:60rpx}.section,.meal,.plan-row{display:flex;flex-direction:column;gap:18rpx}.section{padding:28rpx;margin:24rpx 0}.meal{padding:22rpx;background:#f4f7f3;border-radius:18rpx;font-size:26rpx}.choices{display:flex;gap:12rpx;flex-wrap:wrap;margin-top:20rpx}.choices button{font-size:24rpx;padding:12rpx 18rpx;background:#eef2ed}.choices button.active{background:#246b50;color:#fff}.plan-row{padding:24rpx;background:#f4f7f3;text-align:left;font-size:26rpx}.plan-row text:last-child,.helper{font-size:25rpx;color:#63636b;line-height:1.65}.section-title{font-size:31rpx;font-weight:600}.safe-note{text-align:left}label{font-size:25rpx;line-height:1.7}button[disabled]{opacity:.5}</style>
