<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { computed, ref } from 'vue'
import { onLoad,onShow } from '@dcloudio/uni-app'
import { mockService } from '../../services/mock.js'
import { backHome } from '../../utils/profile.js'
import { createDeliveryBatches, defaultPlanStartDate, getExclusivePlan,adaptExclusivePlan } from '../../utils/exclusive-plans.js'

const plan = ref(adaptExclusivePlan(getExclusivePlan('balanced')))
const startDate = ref(defaultPlanStartDate())
const address = ref('')
onShow(()=>{const selected=mockService.selectedAddress();address.value=selected?selected.name+' · '+selected.phone+'\n'+selected.region+' '+selected.detail:''})
const batches = computed(() => createDeliveryBatches(plan.value, startDate.value, 21))
const total = computed(() => ((plan.value.totalEstimateCents || plan.value.estimateCents) / 100).toFixed(2))
onLoad(options => { plan.value = adaptExclusivePlan(getExclusivePlan(options.id)) })
function changeDate(event) { startDate.value = event.detail.value }
function chooseAddress(){uni.navigateTo({url:'/pages/address/index'})}
function pay() {
  if(plan.value.blocked.length)return uni.showToast({title:'请先补充档案后重新检查',icon:'none'})
  if(!address.value)return uni.showToast({title:'请先选择配送地址',icon:'none'})
  uni.navigateTo({ url: '/pages/shop/index?meal=dinner&source=exclusive-plan&checkout=1&plan=' + plan.value.id + '&start=' + startDate.value + '&batches=21' })
}
</script>

<template>
  <view class="screen schedule-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">确认配送</text><text class="pill">21 次</text></view></AppNavBar>
    <view class="schedule-head"><text class="eyebrow">AI专属计划 · 配送安排</text><text class="display-title">先确定送到哪里，<br />再安排 21 批。</text><text>顺序固定为“地址 → 第1批预计送达日 → 21批配送”。日期与菜品均为测试数据。</text></view>
    <button class="address-card card" @click="chooseAddress"><view><text class="section-title">配送地址</text><text>{{address||'还没有收货地址'}}</text></view><text>{{address?'更换':'新增'}} ›</text></button>
    <view class="date-card card">
      <view><text class="section-title">第1批预计送达日</text><text>{{address?'选择可预约日期':'请先选地址'}}</text></view>
      <picker v-if="address" mode="date" :value="startDate" :start="defaultPlanStartDate()" @change="changeDate"><view class="date-select"><text>{{ startDate }}</text><text>›</text></view></picker>
      <text class="date-note">计划生效日 = 第1批食材的预计送达日，不是支付日。可预约日期正式版由履约服务返回。</text>
    </view>
    <view class="batch-head"><view><text class="section-title">配送批次</text><text>{{ plan.name }} · 共21次</text></view><text>每日一批</text></view>
    <view class="batch-list">
      <view v-for="batch in batches" :key="batch.index" class="batch-row">
        <view class="batch-line"><text></text></view>
        <view class="batch-copy"><view><text>第{{ batch.index }}天</text><text>{{ batch.date }} 送达</text></view><text>{{ batch.dishes.join('、') }}</text></view>
      </view>
    </view>
    <view class="schedule-note">实际商品、库存、配送范围与时间需在正式商城再次确认。本页不创建真实订阅或配送。</view>
    <view class="bottom-bar"><view><text>一次支付总价 · 测试</text><text>¥{{ total }}</text><text>首批预计送达 {{ startDate }}</text></view><button class="primary-button" @click="pay">核对商品与价格，去结算 →</button></view>
  </view>
</template>

<style scoped>
.schedule-screen { padding-bottom: calc(env(safe-area-inset-bottom) + 190rpx); }.schedule-head { margin-top: 46rpx; }.schedule-head .display-title { display: block; font-size: 50rpx; line-height: 1.25; }.schedule-head > text:last-child { display: block; margin-top: 18rpx; color: #687a72; font-size: 22rpx; line-height: 1.65; }
.address-card{width:100%;display:flex;align-items:center;justify-content:space-between;margin-top:28rpx;padding:24rpx;text-align:left}.address-card>view{display:flex;flex-direction:column;gap:9rpx}.address-card>view text:last-child{max-width:470rpx;color:#6c7e75;font-size:19rpx;line-height:1.5;white-space:pre-line}.address-card>text:last-child{color:#246b50;font-size:20rpx;font-weight:800}
.date-card { margin-top: 30rpx; padding: 26rpx; }.date-card > view:first-child { display: flex; align-items: center; justify-content: space-between; }.date-card > view:first-child > text:last-child { color: #7c8b84; font-size: 18rpx; }.date-select { display: flex; align-items: center; justify-content: space-between; min-height: 80rpx; margin-top: 18rpx; padding: 0 20rpx; border-radius: 18rpx; background: #eef1e5; color: #1f5f49; }.date-select text:first-child { font-family:inherit; font-size: 29rpx; font-weight: 800; }.date-select text:last-child { font-size: 34rpx; }.date-note { display: block; margin-top: 15rpx; color: #859089; font-size: 18rpx; }
.batch-head { display: flex; align-items: flex-end; justify-content: space-between; margin: 42rpx 0 20rpx; }.batch-head > view { display: flex; flex-direction: column; gap: 7rpx; }.batch-head > view text:last-child,.batch-head > text { color: #77877f; font-size: 19rpx; }.batch-list { padding: 4rpx 0 6rpx; }.batch-row { display: grid; grid-template-columns: 32rpx 1fr; min-height: 112rpx; }.batch-line { position: relative; }.batch-line::after { content: ''; position: absolute; left: 12rpx; top: 22rpx; bottom: -22rpx; width: 2rpx; background: #cfd8ce; }.batch-row:last-child .batch-line::after { display: none; }.batch-line text { position: relative; z-index: 2; width: 20rpx; height: 20rpx; display: block; margin: 17rpx 0 0 3rpx; border: 4rpx solid #f5f5f7; border-radius: 50%; background: #7da58c; }.batch-copy { padding: 10rpx 0 24rpx 8rpx; }.batch-copy > view { display: flex; align-items: baseline; gap: 14rpx; }.batch-copy > view text:first-child { color: #1d1d1f; font-size: 24rpx; font-weight: 800; }.batch-copy > view text:last-child { color: #5f754e; font-size: 22rpx; font-weight: 700; }.batch-copy > text { display: block; margin-top: 10rpx; color: #7b8983; font-size: 20rpx; line-height: 1.55; }.schedule-note { margin-top: 18rpx; padding: 20rpx; border-radius: 20rpx; background: #efe1d4; color: #775d52; font-size: 18rpx; line-height: 1.6; }
.bottom-bar { position: fixed; z-index: 10; left: 0; right: 0; bottom: 0; display: flex; align-items: center; gap: 18rpx; padding: 20rpx 30rpx calc(env(safe-area-inset-bottom) + 20rpx); border-top: 1rpx solid rgba(24,54,46,.08); background: rgba(255,253,247,.97); }.bottom-bar > view { width: 190rpx; display: flex; flex-direction: column; gap: 4rpx; color: #718179; font-size: 17rpx; }.bottom-bar > view text:nth-child(2) { color: #a64e39; font-family:inherit; font-size: 31rpx; font-weight: 800; }.bottom-bar .primary-button { flex: 1; min-height: 82rpx; margin: 0; font-size: 23rpx; }
</style>
