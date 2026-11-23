<script setup>
import { computed, reactive, ref } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'
import ExclusivePlanDeck from './ExclusivePlanDeck.vue'
import { createExclusivePlanClient, exclusivePlanState, planTiers } from '../services/exclusive-planning.js'

async function open() { await client.open() }
async function startPlan() { await client.act('ensure') }
const active = ref(false)
const state = reactive(exclusivePlanState()), client = createExclusivePlanClient(state)
const ready = computed(() => state.status === 'ready' && state.plans.length === 3)
const cards = computed(() => planTiers.map(tier => state.plans.find(plan => plan.tier_code === tier) || { tier_code: tier }))
const preparing = computed(() => state.status === 'generating' && !!state.group?.group_id && !state.error)
const reading = computed(() => state.busy || (state.status === 'reading' && !state.error))
const cardAction = computed(() => ready.value ? '查看计划' : preparing.value ? '正在生成' : reading.value ? '正在读取' : canStart.value ? '生成计划' : state.error ? '待重试' : '待准备')
const canStart = computed(() => !state.busy && ['empty', 'stale'].includes(state.status))
const back = () => uni.navigateBack()
function stop() { active.value = false; client.stop() }
function detail(plan) {
  if (active.value && canStart.value) return startPlan()
  if (!active.value || state.busy || !ready.value) return
  const current = state.plans.find(item => item.tier_code === plan.tier_code && item.plan_sn === plan.plan_sn && item.plan_version === plan.plan_version)
  if (!current) return
  const query = state.group.preview_only
    ? 'group_id=' + encodeURIComponent(state.group.group_id) + '&tier=' + encodeURIComponent(current.tier_code)
    : 'plan_sn=' + encodeURIComponent(current.plan_sn) + '&plan_version=' + current.plan_version
  uni.navigateTo({ url: '/pages/exclusive-plans/detail?' + query })
}
onShow(() => { active.value = true; open() })
onHide(stop)
onUnload(stop)
</script>

<template>
  <view class="screen exclusive-overview">
    <AppNavBar title="AI 专属计划"><template #left><button class="overview-back" aria-label="返回" @click="back">‹</button></template></AppNavBar>
    <view class="overview-hero"><text class="hero-eyebrow">为家人的每一餐，多想一点</text><view class="hero-title"><text>接下来 </text><text class="hero-number">21</text><text> 天，</text><text class="hero-line">好好吃饭。</text></view><text class="hero-caption">根据家庭档案，安排全家的三餐。</text><view class="calendar-stack" aria-hidden="true"><view class="calendar-page"><view class="calendar-header"><text>三餐计划</text></view><view class="calendar-date"><text class="calendar-number">21</text><text class="calendar-unit">天</text></view><view class="calendar-grid"/></view><view class="calendar-ring ring-left"/><view class="calendar-ring ring-right"/></view></view>
    <view class="overview-family"><view><AppIcon name="family" :size="28"/><text>为全家安排</text></view><text>21 天 · 每日三餐</text></view>
    <view class="overview-heading"><text>选一份适合家的计划</text><text>三种选择</text></view>
    <ExclusivePlanDeck :plans="cards" :action-label="cardAction" :disabled="(!ready && !canStart) || state.busy || !active" @detail="detail"/>
    <text v-if="preparing" class="overview-notice" role="status">正在为家人准备计划，可以离开页面，稍后回来查看。</text>
    <text v-else-if="reading" class="overview-notice" role="status">正在读取已保存的计划…</text>
    <view v-else-if="!ready && (!canStart || state.error)" class="overview-error"><text class="error-title">{{ state.status === 'unavailable' ? '专属计划暂未开放' : '计划暂时无法读取' }}</text><text v-if="state.error && state.error !== '专属计划暂未开放'" class="error-copy">{{ state.error }}</text><button v-if="state.status !== 'unavailable'" class="overview-retry" :disabled="state.busy" @click="canStart ? startPlan() : state.status === 'failed' ? client.act('retry') : open()">重新读取</button></view>
    <text v-if="state.error && state.traceId" class="overview-notice" selectable>请求编号 {{state.traceId}}</text>
    <text v-if="ready && state.error" class="overview-notice">{{ state.error }}</text>
  </view>
</template>

<style scoped>
.exclusive-overview{min-height:100vh;box-sizing:border-box;overflow:hidden}.exclusive-overview button::after{border:0}
.overview-back{min-width:44px;min-height:44px;margin:0 0 0 -7px;padding:0 7px;background:transparent;text-align:left;font-size:31px;line-height:1.4}
.overview-hero{position:relative;box-sizing:border-box}.hero-title{position:relative;z-index:1}.hero-line{display:block}.hero-eyebrow,.hero-caption{display:block}
.calendar-stack{position:absolute;isolation:isolate;box-sizing:border-box}.calendar-stack::before{content:'';position:absolute;z-index:-1}.calendar-page{position:relative;height:100%;overflow:hidden;box-sizing:border-box;background:#fff}.calendar-header{display:flex;align-items:center;justify-content:center;box-sizing:border-box;color:#fff}.calendar-date{display:flex;align-items:baseline;justify-content:center;box-sizing:border-box}.calendar-ring{position:absolute;z-index:2;box-sizing:border-box}
.overview-family,.overview-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.overview-error{display:flex;align-items:center;flex-direction:column;gap:12px;box-sizing:border-box;text-align:center}.error-copy{line-height:1.8;overflow-wrap:anywhere}.overview-retry{width:100%;box-sizing:border-box;color:#fff;line-height:1.6}
.exclusive-overview{padding:0 20px calc(24px + env(safe-area-inset-bottom));color:#3d354c;background-color:#e9e3f7;background-image:radial-gradient(ellipse at 100% 100%,#e8d9f4 0%,transparent 48%),linear-gradient(180deg,#d3defb 0%,#e0e4fc 40%,#eae6f7 100%);background-size:100% 100%;background-repeat:no-repeat}
.overview-back{color:#685c7d}.overview-hero{min-height:0;padding:13px 2px 0}.hero-eyebrow{margin-bottom:8px;font-size:11px;color:#8a7a9c;letter-spacing:.3px;font-weight:400;line-height:1.5}.hero-title{font-size:26px;line-height:1.38;letter-spacing:.2px;font-weight:600;color:#3b354c}.hero-number{font-size:31px;line-height:1;color:#8253c0;letter-spacing:0}.hero-caption{margin-top:8px;color:#7d6d8d;font-size:12px;font-weight:400;line-height:1.7}
.calendar-stack{width:77px;height:88px;right:9px;top:29px;border-radius:12px;transform:rotate(5deg);box-shadow:0 9px 20px #70529014}.calendar-stack::before{inset:4px -4px -5px 4px;border:1px solid #ffffffbb;border-radius:12px;background:#e2d9f2}.calendar-page{border:1px solid #d5c9eb;border-radius:12px}.calendar-header{height:23px;padding-top:0;background:#a78acf;border-bottom:1px solid #a78acf;font-size:9px;line-height:1.5;letter-spacing:1px}.calendar-date{height:41px;gap:2px;padding-top:3px;color:#8c68b7}.calendar-number{font-size:32px;line-height:1.2;font-weight:500;letter-spacing:0}.calendar-unit{font-size:10px;color:#8c68b7}.calendar-grid{width:60px;height:14px;margin:1px auto 0;background-image:radial-gradient(circle,#d8cce8 1.5px,transparent 1.8px);background-size:8.5px 7px}.calendar-ring{top:-6px;width:6px;height:14px;border:1.5px solid #a498bd;border-radius:4px;background:#b8abc9;box-shadow:inset 1px 0 0 #ded5ea}.ring-left{left:14px}.ring-right{right:14px}
.overview-family{padding:14px 2px 0;font-size:12px;line-height:1.6;color:#887896;gap:10px}.overview-family>view{display:flex;align-items:center;gap:6px;min-width:0}.overview-family>text:last-child{font-size:11px;color:#887896;white-space:nowrap}.overview-heading{margin:16px 0 13px;font-size:16px;font-weight:400;line-height:1.5}.overview-heading>text:last-child{font-size:11px;color:#9683a4}
.overview-notice{padding:14px 3px 0;font-size:12px;line-height:1.8;color:#877193}.overview-error{margin-top:16px;padding:28px 20px;border:1px solid #fff;border-radius:21px;background:#ffffffd9}.error-title{font-size:17px;color:#5f466f}.error-copy{font-size:13px;color:#877193}.overview-retry{min-height:44px;padding:12px 18px;border-radius:14px;background:#8552ce;font-size:14px}
@media(max-width:350px){.exclusive-overview{padding-left:16px;padding-right:16px}.overview-hero{padding-left:1px}.hero-title{font-size:24px}.hero-number{font-size:29px}.hero-caption{font-size:11px}.calendar-stack{width:68px;height:81px;top:28px;right:2px}.calendar-header{height:21px;font-size:8px}.calendar-date{height:37px;padding-top:3px}.calendar-number{font-size:29px}.calendar-grid{width:53px;height:12px;background-size:7.5px 6px}.overview-family{font-size:11px}.overview-family>text:last-child{font-size:10px}.overview-heading{font-size:15px}}

</style>
