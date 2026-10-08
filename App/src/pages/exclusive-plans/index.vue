<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { computed, ref } from 'vue'
import { getProfile, backHome } from '../../utils/profile.js'
import { EXCLUSIVE_PLANS,adaptExclusivePlan,regenerateExclusivePlans } from '../../utils/exclusive-plans.js'
import { reviewReasons } from '../../utils/demo.js'

import { onShow } from '@dcloudio/uni-app'
const profile = ref(getProfile()),revision=ref(0)
onShow(()=>{profile.value=getProfile();revision.value++})
const plans=computed(()=>{revision.value;return EXCLUSIVE_PLANS.map(p=>adaptExclusivePlan(p,profile.value))})
const memberNames = computed(() => profile.value.members.map(member => member.name).join('、'))
const blockers = computed(() => plans.value.flatMap(p=>p.blocked))
function openPlan(id) { uni.navigateTo({ url: '/pages/exclusive-plans/detail?id=' + id }) }
function refresh() {regenerateExclusivePlans();profile.value=getProfile();revision.value++;uni.showToast({title:'演示菜谱已更新',icon:'none'})}
function goMy() { uni.navigateTo({ url: '/pages/my/index' }) }
</script>

<template>
  <view class="screen plans-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">AI专属计划</text><text class="pill">演示</text></view></AppNavBar>
    <view class="plans-head">
      <text class="eyebrow">FOR YOUR FAMILY</text>
      <text class="display-title">为您推荐的专属计划</text>
      <text class="head-desc">基于 {{ memberNames }} 的家庭档案，综合身体情况、生活习惯及营养目标，为您展示以下计划样例。</text>
    </view>
    <view v-if="blockers.length" class="review-card card">
      <text class="section-title">生成计划前，请先核对健康档案</text>
      <text>{{ blockers.join('；') }}</text>
      <text>资料缺失、已知冲突或无法判断安全时，不提供可购买的个体化计划。</text>
      <text>如需补充资料，请从“我的 → 我的家”进入家庭健康档案。</text>
      <button class="secondary-button" @click="goMy">前往“我的”</button>
    </view>
    <view v-else class="plan-list">
      <button v-for="plan in plans" :key="plan.id" class="plan-card" @click="openPlan(plan.id)">
        <view class="plan-copy">
          <text class="plan-tag">{{ plan.tag }}</text>
          <text class="plan-name">{{ plan.name }}</text>
          <text class="plan-subtitle">{{ plan.subtitle }}</text>
          <view class="plan-price"><text>首批食材约</text><text>¥{{ (plan.estimateCents / 100).toFixed(0) }}</text><text class="plus">＋</text></view><text class="tier-total">21 天约 ¥{{(plan.totalEstimateCents/100).toFixed(0)}} · 测试金额</text>
        </view>
        <image :src="'/static/food/family-meal.jpg'" :alt="plan.name" mode="aspectFill" />
      </button>
    </view>
    <view class="renew-card"><view><text>档案或目标有变化？</text><text>建议及时重新生成专属计划</text></view><button @click="refresh">重新定制</button></view>
    <text class="safe-note page-note">固定计划与价格均为原型演示，不构成个体诊疗建议</text>
  </view>
</template>

<style scoped>
.plans-screen{background:white;padding-bottom:60rpx}.plans-head{margin:40rpx 0 48rpx}.plans-head .eyebrow{display:none}.plans-head .display-title{font-size:50rpx;line-height:1.35}.head-desc{display:block;margin-top:24rpx;color:#63636b;font-size:28rpx;line-height:1.7}.plan-list{display:flex;flex-direction:column;gap:28rpx}.plan-card{position:relative;display:block;width:100%;min-height:330rpx;border-radius:30rpx;overflow:hidden;background:#f5f5f7;text-align:left}.plan-card image{position:absolute;right:-12%;top:0;width:60%;height:100%;z-index:0}.plan-card::before{content:'';position:absolute;inset:0;z-index:1;background:linear-gradient(90deg,#f5f5f7 0%,#f5f5f7 44%,rgba(245,245,247,.8) 54%,rgba(245,245,247,0) 74%)}.plan-copy{position:relative;z-index:2;display:flex;align-items:flex-start;flex-direction:column;width:70%;padding:30rpx;min-height:330rpx}.plan-tag{font-size:22rpx;color:#246b50;background:#eaf2ed;padding:6rpx 14rpx;border-radius:10rpx}.plan-name{font-size:40rpx;font-weight:600;margin-top:16rpx}.plan-subtitle{max-width:310rpx;margin-top:14rpx;font-size:25rpx;line-height:1.55;color:#63636b}.plan-price{display:flex;flex-wrap:wrap;align-items:center;gap:10rpx;margin-top:24rpx;font-size:23rpx;color:#63636b}.plan-price>text:nth-child(2){font-size:38rpx;color:#1d1d1f;font-weight:600}.plan-price .plus{height:52rpx;width:52rpx;display:flex;align-items:center;justify-content:center;background:#1d1d1f;color:#fff;border-radius:14rpx;font-size:34rpx;margin-left:6rpx}.tier-total{font-size:23rpx;margin-top:14rpx;color:#63636b}.renew-card{margin-top:32rpx;padding:26rpx;background:#f0f3f1;border-radius:26rpx;display:flex;align-items:center;gap:18rpx;justify-content:space-between}.renew-card>view{display:flex;flex-direction:column;gap:8rpx;font-size:26rpx}.renew-card>view text:last-child{font-size:23rpx;color:#63636b}.renew-card button{flex-shrink:0;min-height:88rpx;padding:20rpx;background:white;border-radius:18rpx;color:#246b50;font-size:27rpx}.page-note{font-size:23rpx;margin-top:28rpx}.review-card{padding:28rpx;line-height:1.65}.review-card>text{display:block;margin-bottom:20rpx}
</style>
