<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { backHome } from '../../utils/profile.js'
import { getOrders, orderStatus } from '../../utils/orders.js'
import { mealToRoute } from '../../utils/meal-flow.js'

const orders = ref([])
const tab = ref('all')
const tabs = [
  { id: 'all', label: '全部' },
  { id: 'delivery', label: '进行中' },
  { id: 'complete', label: '已完成' },
]
const filtered = computed(() => orders.value.filter(order => tab.value === 'all' || (tab.value === 'delivery' ? ['pending','paid','partial','paused','refund_pending'].includes(order.status) : ['delivered','cancelled'].includes(order.status))))
onShow(() => { orders.value = getOrders() })
function total(order) { return (order.totalCents / 100).toFixed(2) }
function detail(order, mode = '') { uni.navigateTo({ url: '/pages/orders/detail?id=' + encodeURIComponent(order.id) + (mode ? '&mode=' + mode : '') }) }
function reorder(order) { uni.navigateTo({ url: '/pages/shop/index?meal=' + mealToRoute(order.meal) + '&reorder=' + encodeURIComponent(order.id) + (order.caseId ? '&case=diabetes' : '') }) }
function nutritionist() { uni.reLaunch({ url: '/pages/chat/index' }) }
</script>

<template>
  <view class="screen orders-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">我的订单</text><text class="pill">测试数据</text></view></AppNavBar>
    <view class="orders-hero">
      <text class="eyebrow">ORDER DESK · 一餐之后还有交付</text>
      <text class="display-title">买到了哪一步，<br />一眼看明白。</text>
      <text class="hero-copy">查看配送进度、发起售后或按原清单再买一单。全部为虚拟订单，不连接真实商家。</text>
    </view>
    <view class="order-tabs">
      <button v-for="item in tabs" :key="item.id" :class="{ active: tab === item.id }" @click="tab = item.id">{{ item.label }}</button>
    </view>
    <view v-if="filtered.length" class="order-list">
      <view v-for="order in filtered" :key="order.id" class="order-card card" @click="detail(order)">
        <view class="order-head"><view><text>{{order.sourcePlanId?'21天 AI专属计划':'普通食材订单'}}</text><text class="small">{{ order.displayTime }} · {{ order.id }}</text></view><text class="status">{{ orderStatus(order).label }}</text></view>
        <view class="item-preview">
          <view v-for="item in order.items.slice(0, 4)" :key="item.id" class="item-icon">{{ item.icon }}</view>
          <view class="item-summary"><text>{{ order.items[0]?.name }}{{ order.items.length > 1 ? '等 ' + order.items.length + ' 件' : '' }}</text><text class="small">{{ orderStatus(order).detail }}</text></view>
        </view>
        <text v-if="order.sourcePlanId" class="batch-summary">已收 {{order.receivedBatchIndices?.length||0}}／{{order.deliveryBatches?.length||21}} 批 · 下一批 {{order.deliveryBatches?.find(b=>!order.receivedBatchIndices?.includes(b.index))?.date||'暂无'}}</text>
        <view class="order-total"><text>实付（演示）</text><text>¥{{ total(order) }}</text></view>
        <view class="order-actions">
          <button @click.stop="detail(order, 'logistics')">查看物流</button>
          <button @click.stop="detail(order, 'service')">申请售后</button>
          <button class="strong" @click.stop="reorder(order)">再买一单</button>
        </view>
      </view>
    </view>
    <view v-else class="empty-card card">
      <view class="empty-mark">▤</view><text class="section-title">这里还没有订单</text><text>从 AI 推荐的食材包完成一次模拟购买，订单会出现在这里。</text><button class="primary-button" @click="nutritionist">返回营养师</button>
    </view>
    <view class="demo-footer">演示订单仅在本次原型体验中保存，不会扣款、发货或创建真实售后工单。</view>
  </view>
</template>

<style scoped>
.orders-screen { padding-bottom: 70rpx; }.orders-hero { margin-top: 48rpx; }.orders-hero .display-title { display: block; font-size: 50rpx; line-height: 1.25; }.hero-copy { display: block; margin-top: 20rpx; color: #667970; font-size: 23rpx; line-height: 1.7; }
.order-tabs { display: grid; grid-template-columns: repeat(3,1fr); gap: 10rpx; margin: 34rpx 0 24rpx; padding: 8rpx; border-radius: 22rpx; background: #e8eadc; }.order-tabs button { min-height: 62rpx; border-radius: 17rpx; color: #718179; font-size: 21rpx; font-weight: 700; }.order-tabs button.active { background: white; color: #246b50; box-shadow: 0 7rpx 18rpx rgba(37,71,56,.08); }
.order-list { display: flex; flex-direction: column; gap: 18rpx; }.order-card { padding: 24rpx; }.order-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16rpx; }.order-head > view { display: flex; flex-direction: column; gap: 7rpx; }.order-head > view text:first-child { color: #1d1d1f; font-size: 25rpx; font-weight: 800; }.small { color: #7b8983; font-size: 18rpx; }.status { padding: 8rpx 13rpx; border-radius: 999rpx; background: #edf3dc; color: #246b50; font-size: 18rpx; font-weight: 800; }
.item-preview { display: flex; align-items: center; margin-top: 22rpx; padding: 18rpx; border-radius: 22rpx; background: #f0eee4; }.item-icon { width: 58rpx; height: 58rpx; display: flex; align-items: center; justify-content: center; margin-right: -9rpx; border: 4rpx solid #f0eee4; border-radius: 18rpx; background: #dce9d4; font-size: 30rpx; }.item-summary { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 7rpx; margin-left: 22rpx; }.item-summary text:first-child { overflow: hidden; color: #1d1d1f; font-size: 22rpx; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.batch-summary{display:block;margin-top:13rpx;color:#4f6b60;font-size:18rpx;font-weight:800}
.order-total { display: flex; align-items: baseline; justify-content: flex-end; gap: 12rpx; padding: 20rpx 2rpx 16rpx; color: #718179; font-size: 18rpx; }.order-total text:last-child { color: #a84e39; font-family:inherit; font-size: 31rpx; font-weight: 800; }.order-actions { display: flex; justify-content: flex-end; gap: 10rpx; padding-top: 16rpx; border-top: 1rpx solid rgba(24,54,46,.08); }.order-actions button { min-height: 58rpx; padding: 0 17rpx; border: 1rpx solid rgba(31,107,82,.14); border-radius: 17rpx; background: #ffffff; color: #536e63; font-size: 19rpx; font-weight: 700; }.order-actions button.strong { background: #246b50; color: white; }
.empty-card { display: flex; flex-direction: column; align-items: center; margin-top: 30rpx; padding: 46rpx 30rpx; text-align: center; }.empty-mark { width: 82rpx; height: 82rpx; display: flex; align-items: center; justify-content: center; margin-bottom: 22rpx; border-radius: 28rpx 28rpx 10rpx; background: #dfead4; color: #246b50; font-size: 38rpx; }.empty-card > text:not(.section-title) { margin: 14rpx 0 26rpx; color: #718179; font-size: 21rpx; line-height: 1.6; }.empty-card .primary-button { width: 100%; }.demo-footer { margin-top: 24rpx; padding: 20rpx; border-radius: 20rpx; background: #efe3d5; color: #786257; font-size: 18rpx; line-height: 1.6; }
</style>
