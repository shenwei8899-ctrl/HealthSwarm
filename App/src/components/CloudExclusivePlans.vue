<script setup>
import { computed, reactive, ref } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import ExclusivePlanDeck from './ExclusivePlanDeck.vue'
import { createExclusivePlanClient, exclusivePlanState } from '../services/exclusive-planning.js'

import { createPlanConsent } from '../services/exclusive-plan-consent.js'
import { request } from '../services/request.js'
import { getSession, sessionRevision } from '../services/session.js'
import { startMemberAnalysis } from '../services/member-profile.js'
const consent = reactive({loading:false,busy:false,members:[],error:'',processor:'',policyVersion:''})
const consentClient = createPlanConsent({state:consent,send:request,family:()=>getSession()?.householdId,revision:sessionRevision,startAnalysis:startMemberAnalysis})
async function open() { await client.open(); if(active.value&&['consent_required','daily_member_sources_unavailable','daily_member_consent_required'].includes(state.errorCode)) await consentClient.load() }
async function confirmConsent() { if(await consentClient.accept()) await open() }
const active = ref(false)
const state = reactive(exclusivePlanState()), client = createExclusivePlanClient(state)
const ready = computed(() => state.status === 'ready' && state.plans.length === 3)
const quietPreparation = computed(() => ['daily_member_sources_unavailable', 'daily_profile_source_unavailable', 'profile_coding_unavailable'].includes(state.errorCode))
const placeholder = computed(() => !ready.value && (state.busy || quietPreparation.value || !state.error && state.status !== 'unavailable' && state.status !== 'failed'))
const back = () => uni.navigateBack()
function stop() { active.value = false; client.stop(); consentClient.stop() }
function detail(plan) {
  if (!active.value || state.busy || !ready.value || state.tier !== plan.tier_code) return
  const current = state.plans.find(item => item.tier_code === plan.tier_code && item.plan_sn === plan.plan_sn && item.plan_version === plan.plan_version)
  if (current) uni.navigateTo({ url: '/pages/exclusive-plans/detail?plan_sn=' + encodeURIComponent(current.plan_sn) + '&plan_version=' + current.plan_version })
}
onShow(() => { active.value = true; open() })
onHide(stop)
onUnload(stop)
</script>

<template>
  <view class="screen exclusive-overview">
    <AppNavBar><view class="nav-row"><button class="overview-back" aria-label="返回" @click="back">‹</button><text class="nav-title">AI 专属计划</text></view></AppNavBar>
    <view class="overview-hero"><text class="hero-eyebrow">为家人的每一餐，多想一点</text><view class="hero-title"><text>接下来 </text><text class="hero-number">21</text><text> 天，</text><text class="hero-line">好好吃饭。</text></view><text class="hero-caption">根据家庭档案，安排全家的三餐。</text><view class="calendar-stack" aria-hidden="true"><view class="calendar-page"><view class="calendar-header"><text>三餐计划</text></view><view class="calendar-date"><text class="calendar-number">21</text><text class="calendar-unit">天</text></view><view class="calendar-grid"/></view><view class="calendar-ring ring-left"/><view class="calendar-ring ring-right"/></view></view>
    <view class="overview-family"><text>♧ &nbsp;为全家安排</text><text>21 天 · 每日三餐</text></view>
    <view class="overview-heading"><text>选一份适合家的计划</text><text>三种选择</text></view>
    <ExclusivePlanDeck v-if="ready" :plans="state.plans" :selected="state.tier" :busy="state.busy" :active="active" @select="client.select" @detail="detail"/>
    <view v-else-if="placeholder" class="overview-placeholder" aria-label="21天计划加载中" :aria-busy="state.busy || state.status === 'generating'">
      <view class="placeholder-tabs"><view/><view/><view/></view><view class="placeholder-card"><view class="placeholder-line line-short"/><view class="placeholder-line line-title"/><view class="placeholder-photo"/><view class="placeholder-line"/><view class="placeholder-line line-medium"/><view class="placeholder-rule"/><view class="placeholder-line"/><view class="placeholder-line line-medium"/><view class="placeholder-rule"/><view class="placeholder-line line-short"/><view class="placeholder-button"/></view>
      <button v-if="!state.busy && state.status !== 'generating'" class="overview-text-button" @click="open">重新读取</button>
    </view>
    <view v-else class="overview-error"><text class="error-title">{{ state.status === 'unavailable' ? '专属计划暂未开放' : '计划暂时无法读取' }}</text><text v-if="state.error && state.error !== '专属计划暂未开放'" class="error-copy">{{ state.error }}</text><button v-if="state.status !== 'unavailable'" class="overview-retry" :disabled="state.busy" @click="state.status === 'failed' ? client.act('retry') : open()">重新读取</button></view>
    <view v-if="consent.loading||consent.members.length||consent.error" class="overview-consent">
      <text class="error-title">确认餐单分析用途</text><text class="error-copy">处理方：{{consent.processor}}；政策版本：{{consent.policyVersion}}。</text>
      <view v-for="member in consent.members" :key="member.id"><checkbox-group v-if="member.canConfirm" @change="member.checked=$event.detail.value.includes(member.id)"><label><checkbox :value="member.id" :checked="member.checked" :disabled="consent.busy"/>同意为{{member.name}}生成餐单</label></checkbox-group><text v-else>{{member.name}}的餐单授权须由本人或已验证监护人确认。</text></view>
      <text v-if="consent.error" class="error-copy" role="alert">{{consent.error}}</text><button v-if="consent.members.some(m=>m.canConfirm)" class="overview-retry" :disabled="consent.busy||consent.loading" @click="confirmConsent">确认所选成员并继续</button><button class="overview-text-button" :disabled="consent.busy||consent.loading" @click="consentClient.load()">重新读取授权</button>
    </view>
    <template v-if="ready"><text v-if="state.error" class="overview-notice">{{ state.error }}</text><button class="overview-text-button" :disabled="state.busy" @click="client.act('regenerate')">↻ &nbsp;换一套计划</button></template>
  </view>
</template>

<style scoped>
.overview-consent{display:flex;flex-direction:column;gap:16px;margin:22px 0;padding:22px 18px;border-radius:20px;background:rgba(255,255,255,.8);font-size:14px;line-height:1.7}

.exclusive-overview{min-height:100vh;box-sizing:border-box;overflow:hidden;color:#353b46;padding:0 36rpx calc(32rpx + env(safe-area-inset-bottom));background-color:#f5f6fa;background-image:radial-gradient(ellipse at 0% 0%,rgba(125,174,255,.65),rgba(125,174,255,0) 72%),radial-gradient(ellipse at 100% 0%,rgba(206,178,245,.55),rgba(206,178,245,0) 75%);background-size:100% 320px;background-position:left top;background-repeat:no-repeat}.exclusive-overview button::after{border:0}.overview-back{min-width:88rpx;min-height:88rpx;margin:0 0 0 -14rpx;padding:0 14rpx;background:transparent;text-align:left;color:#667182;font-size:60rpx;line-height:1.4}.overview-hero{position:relative;min-height:354rpx;box-sizing:border-box;padding:38rpx 12rpx 40rpx}.hero-eyebrow{display:block;margin-bottom:22rpx;font-size:23rpx;color:#78879e;letter-spacing:2rpx;font-weight:500}.hero-title{position:relative;z-index:1;font-size:58rpx;line-height:1.5;font-weight:600;letter-spacing:1rpx}.hero-number{font-size:68rpx;color:#476fc3;letter-spacing:-2rpx}.hero-line{display:block}.hero-caption{display:block;margin-top:20rpx;color:#747e8d;font-size:25rpx;line-height:1.7;font-weight:500}.calendar-stack{position:absolute;right:10rpx;top:96rpx;isolation:isolate;width:174rpx;height:202rpx;box-sizing:border-box;transform:rotate(4deg);box-shadow:0 18rpx 32rpx #617aa41c;border-radius:20rpx}
.calendar-stack::before{content:'';position:absolute;inset:8rpx -8rpx -10rpx 8rpx;z-index:-1;border:2rpx solid #f8fbff;border-radius:20rpx;background:#dfe8f7;transform:rotate(0deg)}
.calendar-page{position:relative;height:100%;overflow:hidden;box-sizing:border-box;border:2rpx solid #cddbef;border-radius:20rpx;background:#fff}
.calendar-header{display:flex;align-items:center;justify-content:center;height:50rpx;box-sizing:border-box;padding-top:8rpx;background:linear-gradient(110deg,#8eafe2,#7299d2);border-bottom:2rpx solid #6c91c7;color:#fff;font-size:21rpx;line-height:1.4;font-weight:500;letter-spacing:2rpx}
.calendar-date{display:flex;align-items:baseline;justify-content:center;gap:4rpx;height:96rpx;box-sizing:border-box;padding-top:10rpx;color:#537bb6}
.calendar-number{font-size:78rpx;line-height:1.1;font-weight:600;letter-spacing:-3rpx}
.calendar-unit{font-size:22rpx;line-height:1.4;color:#8ba1c2}
.calendar-grid{width:126rpx;height:36rpx;margin:4rpx auto 0;background-image:radial-gradient(circle,#c1d1e8 3rpx,transparent 3.5rpx);background-size:18rpx 12rpx;background-repeat:repeat}
.calendar-ring{position:absolute;z-index:2;top:-12rpx;width:13rpx;height:32rpx;box-sizing:border-box;border:3rpx solid #8198b7;border-radius:8rpx;background:#d6e0ee;box-shadow:inset 2rpx 0 0 #fff,0 2rpx 2rpx #48648b18}
.ring-left{left:32rpx}.ring-right{right:32rpx}.overview-family{display:flex;justify-content:space-between;align-items:center;gap:20rpx;padding:24rpx 4rpx 40rpx;color:#69778c;font-size:25rpx;line-height:1.7;font-weight:500}.overview-family text:last-child{font-size:23rpx;color:#8892a2}.overview-heading{display:flex;justify-content:space-between;align-items:center;gap:16rpx;margin:0 4rpx 26rpx;font-size:33rpx;font-weight:500;line-height:1.6}.overview-heading text:last-child{font-size:23rpx;color:#8791a1;font-weight:400}.overview-text-button{display:flex;align-items:center;justify-content:center;margin:16rpx auto 0;min-height:88rpx;padding:12rpx 20rpx;color:#788aa6;background:transparent;font-size:26rpx;line-height:1.6}.overview-error{display:flex;align-items:center;flex-direction:column;gap:24rpx;box-sizing:border-box;padding:70rpx 36rpx;border-radius:42rpx;background:#fff;text-align:center}.error-title{font-size:34rpx;font-weight:500;line-height:1.6}.error-copy,.overview-notice{font-size:26rpx;color:#747e8d;line-height:1.8;word-break:break-word}.overview-notice{display:block;padding:28rpx 8rpx 0}.overview-retry{width:100%;min-height:90rpx;padding:22rpx 30rpx;border-radius:28rpx;color:#fff;background:#476fc3;font-size:28rpx;line-height:1.6}.placeholder-tabs{display:flex;gap:14rpx;padding:10rpx;margin-bottom:44rpx;background:#e9eef7;border-radius:34rpx}.placeholder-tabs>view{flex:1;height:110rpx;border-radius:24rpx;background:#f7f9fc}.placeholder-card{position:relative;padding:46rpx 38rpx;border-radius:48rpx;background:#fff;min-height:710rpx;box-sizing:border-box}.placeholder-line{height:24rpx;margin-bottom:22rpx;width:85%;background:#edf1f7;border-radius:12rpx}.line-short{width:44%}.line-title{height:54rpx;width:38%;margin-bottom:28rpx}.line-medium{width:65%}.placeholder-photo{position:absolute;right:38rpx;top:42rpx;width:190rpx;height:190rpx;border-radius:50%;background:#f0f3f8}.placeholder-card>.placeholder-line:nth-child(4){margin-top:90rpx}.placeholder-rule{height:1rpx;background:#eef1f6;margin:36rpx 0}.placeholder-button{height:94rpx;margin-top:34rpx;border-radius:28rpx;background:#e8eef9}
@media(max-width:350px){.exclusive-overview{padding-left:24rpx;padding-right:24rpx}.overview-hero{padding-left:12rpx}.hero-title{font-size:50rpx}.hero-number{font-size:58rpx}.calendar-stack{right:8rpx;width:154rpx;height:182rpx;top:108rpx}.calendar-header{height:46rpx}.calendar-date{height:84rpx;padding-top:8rpx}.calendar-number{font-size:68rpx}.calendar-grid{width:112rpx;height:30rpx;background-size:16rpx 10rpx;margin-top:4rpx}.calendar-ring{height:30rpx}.ring-left{left:28rpx}.ring-right{right:28rpx}.hero-caption{font-size:24rpx}.overview-family{font-size:24rpx}.overview-heading{font-size:31rpx}}
</style>
