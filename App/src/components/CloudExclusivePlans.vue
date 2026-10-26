<script setup>
import { computed, reactive } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import FoodImageSlot from './FoodImageSlot.vue'
import { createExclusivePlanClient, exclusivePlanState, planTiers, planTierNames, planMoney } from '../services/exclusive-planning.js'
import { createPlanConsent } from '../services/exclusive-plan-consent.js'
import { request } from '../services/request.js'
import { getSession, sessionRevision } from '../services/session.js'
import { startMemberAnalysis } from '../services/member-profile.js'
const consent = reactive({loading:false,busy:false,members:[],error:'',processor:'',policyVersion:''})
const consentClient = createPlanConsent({state:consent,send:request,family:()=>getSession()?.householdId,revision:sessionRevision,startAnalysis:startMemberAnalysis})
async function open() { await client.open(); if(['consent_required','daily_member_sources_unavailable','daily_member_consent_required'].includes(state.errorCode)) await consentClient.load() }
async function confirmConsent() { if(await consentClient.accept()) await open() }
function stop() {client.stop();consentClient.stop()}
const state = reactive(exclusivePlanState()), client = createExclusivePlanClient(state)
const plan = computed(() => state.plans.find(p => p.tier_code === state.tier))
const names = computed(() => state.group?.members?.map(m => m.name).join('、') || '全家')
const progress = computed(() => Math.min(95, Math.round((state.group?.completed_days || 0) / 63 * 90)))
const back = () => uni.navigateBack()
const preferences = () => uni.navigateTo({url:'/pages/profile/index'})
function detail() { if (plan.value) uni.navigateTo({url:'/pages/exclusive-plans/detail?plan_sn='+encodeURIComponent(plan.value.plan_sn)+'&plan_version='+plan.value.plan_version}) }
onShow(open); onHide(stop); onUnload(stop)
</script>
<template>
  <view class="screen exclusive-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="back">‹</button><text class="nav-title">AI 专属计划</text></view></AppNavBar>
    <view class="plan-heading"><view class="plan-title"><text class="plan-title-line">全家的三餐，</text><text class="plan-title-line">从容安排。</text></view><text class="plan-caption">21 天 · 为{{names}}安排</text></view>
    <template v-if="state.status==='ready' && state.plans.length">
      <view class="tier-switch"><button v-for="tier in planTiers" :key="tier" :class="{chosen:state.tier===tier}" :aria-pressed="state.tier===tier" @click="client.select(tier)">{{planTierNames[tier]}}</button></view>
      <view v-if="plan" class="plan-surface featured-plan">
        <view class="plan-card-heading"><view><text class="plan-section-title">{{plan.tier_name}}</text><text class="plan-caption">{{plan.difference}}</text></view><text class="plan-badge">21 天</text></view>
        <FoodImageSlot class="plan-photo" :src="plan.display?.image_url" :label="plan.tier_name"/>
        <view class="plan-prices"><view><text class="plan-caption">首批食材预估</text><text class="plan-price">{{Number.isSafeInteger(plan.first_batch_goods_cent)?'¥'+planMoney(plan.first_batch_goods_cent):'待报价'}}</text></view><view class="price-right"><text class="plan-caption">21 天食材与服务</text><text class="plan-subprice">{{Number.isSafeInteger(plan.estimated_subtotal_cent)?'¥'+planMoney(plan.estimated_subtotal_cent):'待报价'}}</text><text class="plan-tiny">配送费选址后计算</text></view></view>
        <button class="plan-primary" :disabled="state.busy" @click="detail">查看完整计划 <text>→</text></button>
      </view>
      <view class="plan-tools"><button @click="preferences">调整偏好</button><text>·</text><button :disabled="state.busy" @click="client.act('regenerate')">换一套</button></view>
    </template>
    <view v-else-if="state.status==='generating'" class="plan-surface plan-empty">
      <view class="plan-orbit">21</view><text class="plan-section-title">正在为全家安排三餐</text><view class="plan-progress"><view :style="{width:progress+'%'}"/></view><text class="plan-caption">稍后回来，继续查看</text>
    </view>
    <view v-else class="plan-surface plan-empty"><text class="plan-section-title">{{state.busy?'正在读取计划':state.status==='unavailable'?'专属计划暂未开放':'计划暂未准备好'}}</text><text v-if="state.error" class="plan-caption">{{state.error}}</text><button v-if="!state.busy && state.status!=='unavailable'" class="plan-primary" @click="state.status==='failed'?client.act('retry'):client.act('ensure')">{{state.status==='failed'?'继续准备':'重新读取'}}</button></view>
    <view v-if="consent.loading||consent.members.length||consent.error" class="plan-surface">
      <text class="plan-section-title">确认餐单分析用途</text><text class="plan-caption">使用所选成员的健康资料生成 21 天餐单。处理方：{{consent.processor}}；政策版本：{{consent.policyVersion}}。</text>
      <view v-for="member in consent.members" :key="member.id" class="plan-caption"><checkbox-group v-if="member.canConfirm" @change="member.checked=$event.detail.value.includes(member.id)"><label><checkbox :value="member.id" :checked="member.checked" :disabled="consent.busy"/>同意为{{member.name}}生成餐单，可在隐私设置撤回</label></checkbox-group><text v-else>{{member.name}}的餐单授权须由本人或已验证监护人确认。</text></view>
      <text v-if="consent.error" class="plan-caption">{{consent.error}}</text><button v-if="consent.members.some(m=>m.canConfirm)" class="plan-primary" :disabled="consent.busy||consent.loading" @click="confirmConsent">确认所选成员并继续</button><button class="plan-text-link" :disabled="consent.busy||consent.loading" @click="consentClient.load()">重新读取授权</button>
    </view>
    <view v-if="state.error && state.plans.length" class="plan-notice">{{state.error}}</view>
    <button class="plan-text-link" @click="uni.navigateTo({url:'/pages/health/plans'})">我的餐单 <text>›</text></button>
  </view>
</template>
<style scoped>
@import '../styles/exclusive-plan.css';
.tier-switch{display:flex;padding:7rpx;background:#edf0f4;border-radius:20rpx;margin:8rpx 0 26rpx}.tier-switch button{flex:1;font-size:28rpx;font-weight:400;line-height:68rpx;background:transparent;border-radius:16rpx;color:#6f7890}.tier-switch button.chosen{background:#fff;color:#171d29;box-shadow:0 2rpx 10rpx #202d4010}.plan-card-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:24rpx;margin-bottom:24rpx}.plan-card-heading>view{display:flex;flex-direction:column;gap:12rpx}.plan-prices{display:flex;justify-content:space-between;gap:20rpx;margin:28rpx 0}.plan-prices>view{display:flex;flex-direction:column;gap:8rpx}.price-right{text-align:right}.plan-price{font-size:46rpx;font-weight:600;letter-spacing:-1rpx}.plan-subprice{font-size:30rpx;font-weight:500}.plan-tools{display:flex;align-items:center;justify-content:center;gap:28rpx;margin:26rpx 0;color:#c3c8d2}.plan-tools button{background:transparent;color:#0878f9;font-size:27rpx;padding:16rpx 8rpx}.plan-orbit{width:108rpx;height:108rpx;line-height:108rpx;text-align:center;background:#f0f5ff;color:#1779f5;border-radius:32rpx;font-size:40rpx}.plan-progress{width:100%;height:7rpx;background:#eef2f7;border-radius:8rpx;overflow:hidden;margin:8rpx 0}.plan-progress>view{height:100%;background:#1683fa;transition:width .35s}.featured-plan{margin-top:0}
</style>
