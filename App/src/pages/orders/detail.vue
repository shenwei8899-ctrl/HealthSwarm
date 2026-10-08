<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { backHome } from '../../utils/profile.js'
import { getOrder, orderStatus, updateOrder } from '../../utils/orders.js'
import { mealToRoute } from '../../utils/meal-flow.js'
import FlowRibbon from '../../components/FlowRibbon.vue'

const orderId = ref('')
const order = ref(null)
const logisticsOpen = ref(false)
const batchesOpen = ref(false)
const requestedMode = ref('')
const selectedBatchIndex = ref(1)
const hasBatches = computed(() => Boolean(order.value?.deliveryBatches?.length))
const selectedBatch = computed(() => order.value?.deliveryBatches?.find(batch => batch.index === selectedBatchIndex.value))
const receivedBatchIndices = computed(() => order.value?.receivedBatchIndices?.length ? order.value.receivedBatchIndices : order.value?.sourcePlanId && order.value?.status === 'delivered' ? [1] : [])
const delivered = computed(() => hasBatches.value ? receivedBatchIndices.value.includes(selectedBatchIndex.value) : order.value?.status === 'delivered')
const status = computed(() => ['paused','refund_pending','cancelled'].includes(order.value?.status) ? orderStatus(order.value) : hasBatches.value
  ? delivered.value
    ? { label: '本批已送达', detail: `第 ${selectedBatchIndex.value} 批食材已确认收到` }
    : { label: '本批待配送', detail: `第 ${selectedBatchIndex.value} 批食材等待收货确认` }
  : orderStatus(order.value))
const total = computed(() => order.value ? (order.value.totalCents / 100).toFixed(2) : '0.00')
onLoad(options => { orderId.value = options.id || ''; requestedMode.value = options.mode || ''; logisticsOpen.value = options.mode === 'logistics'; selectedBatchIndex.value = Math.max(1, Number(options.batch) || 1) })
onShow(() => { order.value = getOrder(orderId.value); if (hasBatches.value && !selectedBatch.value) selectedBatchIndex.value = 1; if (requestedMode.value === 'service') { requestedMode.value = ''; setTimeout(requestAfterSale, 350) } })
function reload(patch) { order.value = updateOrder(orderId.value, patch) }
function confirmReceived() {
  const content = hasBatches.value ? `确认收到第 ${selectedBatchIndex.value} 批食材？这是演示操作，仅标记当前批次；其余批次仍按计划展示。` : '这是演示操作。确认后订单将标记为“已送达”，并出现烹饪入口。'
  uni.showModal({ title: '确认收到食材？', content, confirmText: '确认收到', success: ({ confirm }) => {
    if (!confirm) return
    if (hasBatches.value) {
      const received = [...new Set([...receivedBatchIndices.value, selectedBatchIndex.value])].sort((a, b) => a - b)
      reload({ receivedBatchIndices: received, status: received.length === order.value.deliveryBatches.length ? 'delivered' : 'partial', deliveredAt: new Date().toISOString() })
    } else reload({ status: 'delivered', deliveredAt: new Date().toISOString() })
  }, fail: () => {
    uni.showToast({ title: '收货确认窗口未能打开，请重试', icon: 'none' })
  } })
}
function selectBatch(index) { selectedBatchIndex.value = index; batchesOpen.value = false }
function requestAfterSale() {
  if (!order.value) return
  const expected = ['希望补发', '希望退款', '请工作人员联系我']
  uni.showActionSheet({ itemList: expected, success: ({ tapIndex }) => {
    const expectation = expected[tapIndex]
    const choices = ['商品问题', '少件／漏件', '配送问题']
    uni.showActionSheet({ itemList: choices, success: ({ tapIndex: reasonIndex }) => {
      const reason = choices[reasonIndex]
      const batchText = hasBatches.value ? `批次：第${selectedBatchIndex.value}批\n` : ''
      uni.showModal({ title: '提交售后摘要？', content: `订单：${order.value.id}\n${batchText}问题：${reason}\n期望：${expectation}\n\n测试环境不会产生真实退款或补发。`, confirmText: '提交测试申请', success: ({ confirm }) => {
        if (!confirm) return
        reload({ afterSale: { batchIndex: hasBatches.value ? selectedBatchIndex.value : null, reason, expectation, status: '已提交', createdAt: new Date().toISOString() } })
        uni.showToast({ title: '测试申请已记录', icon: 'success' })
      } })
    } })
  } })
}
function togglePause(){const pausing=order.value.status!=='paused';uni.showModal({title:pausing?'暂停剩余计划？':'恢复计划？',content:pausing?`将从第 ${selectedBatchIndex.value} 批后的可变更、未发货批次开始暂停。已发货和已收货批次不变。`:'恢复后需依据实际运力生成新排程并再次确认。',confirmText:pausing?'确认暂停':'确认恢复',success:({confirm})=>{if(confirm)reload({status:pausing?'paused':'partial',planPaused:pausing})}})}
function cancelRemaining(){const remaining=(order.value.deliveryBatches?.length||21)-receivedBatchIndices.value.length;uni.showModal({title:'取消剩余计划',content:`可申请取消的测试批次：${remaining} 批\n实时退款预览：待商城服务计算\n\n已发货／已收货批次的商品问题需单独发起逐批售后。`,confirmText:'提交测试申请',success:({confirm})=>{if(confirm)reload({status:'refund_pending',refundPreview:'待服务端计算'})}})}
function changeBatchAddress(){if(delivered.value)return uni.showToast({title:'已发货／收货批次请联系配送',icon:'none'});uni.showModal({title:`修改第 ${selectedBatchIndex.value} 批地址`,content:'只修改当前未发货批次，其他批次不变。正式版需选择地址并重新核对履约能力。',confirmText:'保存测试地址',success:({confirm})=>{if(confirm)uni.showToast({title:'当前批次地址已更新',icon:'success'})}})}
function reorder() { uni.navigateTo({ url: '/pages/shop/index?meal=' + mealToRoute(order.value.meal) + '&reorder=' + encodeURIComponent(order.value.id) + (order.value.caseId ? '&case=diabetes' : '') }) }
const cookingMeals=computed(()=>selectedBatch.value?.meals || order.value?.cookingGuides?.[0]?.guides.map(g=>({type:g.meal,name:g.dishes.join('、')})) || (order.value?.cookingGuide?[{type:order.value.cookingGuide.meal,name:order.value.cookingGuide.dishes.join('、')}]:[]))
function cook(mealName) { if (delivered.value) uni.navigateTo({ url: '/pages/cook/index?id=' + encodeURIComponent(order.value.id) + '&meal='+mealToRoute(mealName) + (hasBatches.value ? '&batch=' + selectedBatchIndex.value : '') }) }
function nutritionist() { uni.reLaunch({ url: '/pages/chat/index' }) }
</script>

<template>
  <view v-if="order" class="screen detail-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">订单详情</text><text class="pill">演示</text></view></AppNavBar>
    <FlowRibbon :current="4" class="detail-flow" />
    <view class="status-hero" :class="{ delivered }">
      <view><text class="eyebrow">{{ delivered ? 'DELIVERED' : 'PREPARING' }}</text><text class="display-title">{{ status.label }}</text><text>{{ status.detail }}</text></view>
      <view class="status-mark">{{ delivered ? '✓' : '···' }}</view>
    </view>
    <view class="progress-card card">
      <view class="progress-head"><text class="section-title">配送进度</text><button @click="logisticsOpen = true">查看物流 ›</button></view>
      <view class="progress-track"><view class="active"><text>1</text><text>已支付</text></view><view :class="{ active: true }"></view><view class="active"><text>2</text><text>商家备货</text></view><view :class="{ active: delivered }"></view><view :class="{ active: delivered }"><text>3</text><text>已送达</text></view></view>
      <text class="progress-note">{{ delivered ? (hasBatches ? '当前批次已确认收到，可以查看这一批的烹饪指引。' : '已由用户确认收到演示食材，现在可以进入烹饪指引。') : '本原型不会自动假设食材已经送达；收到后请主动确认当前批次。' }}</text>
    </view>
    <view v-if="order.deliveryBatches?.length" class="card batches-card">
      <view class="progress-head"><view><text class="section-title">计划配送批次</text><text>{{ order.planName }} · 已收 {{ receivedBatchIndices.length }} / {{ order.deliveryBatches.length }} 批</text></view><button @click="batchesOpen = true">切换批次 ›</button></view>
      <view class="selected-batch"><text>当前查看：第 {{ selectedBatch.index }} 批 · {{ selectedBatch.date }}</text><text>{{ selectedBatch.dishes.join('、') }}</text></view>
      <view v-for="batch in order.deliveryBatches.slice(0, 3)" :key="batch.index" class="batch-preview"><text>第{{ batch.index }}天</text><view><text>{{ batch.date }} 送达</text><text>{{ batch.dishes.join('、') }}</text></view></view>
      <text class="batch-hint">其余 {{ order.deliveryBatches.length - 3 }} 次已排入计划，日期与菜品均为演示。</text>
    </view>
    <view class="card goods-card">
      <view class="card-title"><text class="section-title">商品清单</text><text>{{ order.items.length }} 件</text></view>
      <view v-for="item in order.items" :key="item.id" class="goods-row"><view class="goods-icon">{{ item.icon }}</view><view><text>{{ item.name }}</text><text>{{ item.pack }}{{ item.unit }}/包 × {{ item.quantity }}</text></view><text>¥{{ (item.priceCents * item.quantity / 100).toFixed(2) }}</text></view>
      <view class="total-row"><text>实付（演示）</text><text>¥{{ total }}</text></view>
    </view>
    <view class="card info-card"><text class="section-title">配送信息</text><text>{{ order.contact }}</text><text>{{ order.address }}</text><text>订单编号：{{ order.id }}</text><text>下单时间：{{ order.displayTime }}</text></view>
    <view v-if="order.afterSale" class="after-sale-note"><text>售后申请已记录</text><text>{{ order.afterSale.reason }} · 仅为原型演示，不会产生退款或客服工单。</text></view>
    <view v-if="hasBatches" class="plan-actions card"><text class="section-title">计划管理</text><view><button @click="togglePause">{{order.status==='paused'?'恢复计划':'从可变更批次开始暂停'}}</button><button @click="changeBatchAddress">修改当前批次地址</button><button class="danger" @click="cancelRemaining">取消剩余计划／退款预览</button></view><text>暂停、恢复和取消只影响可变更的未发货批次；已收批次售后与剩余计划退款分开。</text></view>
    <view class="service-actions"><button @click="logisticsOpen = true">查看物流</button><button @click="requestAfterSale">申请售后</button><button @click="reorder">再买一单</button></view>
    <button v-if="!delivered" class="primary-button receive-button" @click="confirmReceived">{{ hasBatches ? '确认已收到第' + selectedBatchIndex + '批食材' : '确认已收到食材' }}</button>
    <view v-else class="card cooking-meals"><view v-for="m in cookingMeals" :key="m.type"><view><text>{{m.type}}</text><text>{{m.name}}</text></view><button class="primary-button" @click="cook(m.type)">开始做饭</button></view></view>
    <button class="secondary-button" @click="nutritionist">返回营养师</button>

    <view v-if="logisticsOpen" class="sheet-mask"><view class="sheet logistics-sheet">
      <view class="sheet-head"><view><text class="eyebrow">演示物流</text><text class="section-title">配送进度</text></view><button @click="logisticsOpen = false">×</button></view>
      <view class="timeline">
        <view class="done"><text></text><view><text>订单已支付</text><text>{{ order.displayTime }} · 模拟支付成功</text></view></view>
        <view class="done"><text></text><view><text>商家备货中</text><text>正在按清单准备食材（固定演示状态）</text></view></view>
        <view :class="{ done: delivered }"><text></text><view><text>{{ delivered ? '用户已确认收货' : '等待配送与收货确认' }}</text><text>{{ delivered ? '当前批次可查看烹饪步骤' : '不会自动模拟送达' }}</text></view></view>
      </view>
      <text class="demo-label">无真实骑手、运单号或预计送达时间。</text>
      <button class="primary-button" @click="logisticsOpen = false">我知道了</button>
    </view></view>
    <view v-if="batchesOpen" class="sheet-mask"><view class="sheet batches-sheet">
      <view class="sheet-head"><view><text class="eyebrow">{{ order.planName }}</text><text class="section-title">{{ order.deliveryBatches.length }} 次配送</text></view><button @click="batchesOpen = false">×</button></view>
      <scroll-view class="batch-scroll" scroll-y>
        <button v-for="batch in order.deliveryBatches" :key="batch.index" class="sheet-batch" :class="{ selected: batch.index === selectedBatchIndex }" @click="selectBatch(batch.index)"><text>第{{ batch.index }}天</text><view><text>{{ batch.date }} 送达 · {{ receivedBatchIndices.includes(batch.index) ? '已收到' : '待确认' }}</text><text>{{ batch.dishes.join('、') }}</text></view><text>›</text></button>
      </scroll-view>
      <text class="demo-label">配送批次为测试数据，不会生成真实订阅或物流。</text>
      <button class="primary-button" @click="batchesOpen = false">关闭</button>
    </view></view>
  </view>
</template>

<style scoped>
.cooking-meals{padding:24rpx;margin:24rpx 0}.cooking-meals>view{display:flex;justify-content:space-between;gap:18rpx;align-items:center;padding:20rpx 0;border-bottom:1rpx solid #dce5d5}.cooking-meals>view>view{flex:1;display:flex;flex-direction:column;gap:10rpx;font-size:23rpx}.cooking-meals .primary-button{min-height:70rpx;font-size:22rpx;padding:0 18rpx}
.detail-screen { padding-bottom: 70rpx; }.detail-flow { margin-top: 20rpx; }.status-hero { display: flex; align-items: center; justify-content: space-between; margin-top: 34rpx; padding: 30rpx; border-radius: 34rpx; background: #246b50; color: white; box-shadow: 0 20rpx 40rpx rgba(31,107,82,.17); }.status-hero.delivered { background: #315f4f; }.status-hero > view:first-child { display: flex; flex-direction: column; gap: 9rpx; }.status-hero .eyebrow { color: #e0eee5; }.status-hero .display-title { font-size: 46rpx; }.status-hero > view:first-child > text:last-child { color: #d6e5d9; font-size: 20rpx; }.status-mark { width: 76rpx; height: 76rpx; display: flex; align-items: center; justify-content: center; border-radius: 26rpx 26rpx 9rpx; background: #e9ecea; color: #1d1d1f; font-size: 34rpx; font-weight: 900; }
.progress-card,.goods-card,.info-card,.batches-card { margin-top: 22rpx; padding: 26rpx; }.progress-head,.card-title { display: flex; align-items: center; justify-content: space-between; }.progress-head > view { display: flex; flex-direction: column; gap: 7rpx; }.progress-head > view > text:last-child { color: #75867e; font-size: 18rpx; }.progress-head button { color: #246b50; font-size: 20rpx; font-weight: 800; }.card-title > text:last-child { color: #7a8982; font-size: 19rpx; }
.progress-track { display: grid; grid-template-columns: 1fr 44rpx 1fr 44rpx 1fr; align-items: start; margin-top: 25rpx; }.progress-track > view:nth-child(even) { height: 3rpx; margin-top: 23rpx; background: #d9e1d7; }.progress-track > view:nth-child(even).active { background: #246b50; }.progress-track > view:nth-child(odd) { display: flex; flex-direction: column; align-items: center; gap: 8rpx; color: #8a9891; font-size: 17rpx; text-align: center; }.progress-track > view:nth-child(odd) text:first-child { width: 46rpx; height: 46rpx; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: #e3e9df; color: #74857d; font-weight: 800; }.progress-track > view:nth-child(odd).active { color: #246b50; font-weight: 800; }.progress-track > view:nth-child(odd).active text:first-child { background: #246b50; color: white; }.progress-note { display: block; margin-top: 22rpx; padding: 17rpx; border-radius: 17rpx; background: #eef2df; color: #5e7469; font-size: 19rpx; line-height: 1.55; }
.goods-row { display: flex; align-items: center; gap: 15rpx; padding: 18rpx 0; border-bottom: 1rpx solid rgba(24,54,46,.08); }.goods-icon { width: 66rpx; height: 66rpx; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; border-radius: 19rpx; background: #e8eedb; font-size: 34rpx; }.goods-row > view:nth-child(2) { flex: 1; display: flex; flex-direction: column; gap: 6rpx; }.goods-row > view:nth-child(2) text:first-child { color: #264b3f; font-size: 22rpx; font-weight: 700; }.goods-row > view:nth-child(2) text:last-child { color: #7c8a84; font-size: 18rpx; }.goods-row > text:last-child { color: #9d4d39; font-size: 21rpx; font-weight: 700; }.total-row { display: flex; align-items: baseline; justify-content: space-between; padding-top: 22rpx; color: #6c7d75; font-size: 20rpx; }.total-row text:last-child { color: #aa4e38; font-family:inherit; font-size: 34rpx; font-weight: 800; }
.batch-preview { display: grid; grid-template-columns: 78rpx 1fr; gap: 12rpx; padding: 17rpx 0; border-bottom: 1rpx solid rgba(24,54,46,.08); }.batch-preview > text { color: #1f5f49; font-size: 20rpx; font-weight: 800; }.batch-preview > view { display: flex; flex-direction: column; gap: 6rpx; }.batch-preview > view text:first-child { color: #5e754f; font-size: 20rpx; font-weight: 700; }.batch-preview > view text:last-child { color: #7b8983; font-size: 18rpx; line-height: 1.45; }.batch-hint { display: block; margin-top: 16rpx; color: #829089; font-size: 18rpx; }.batch-scroll { max-height: 630rpx; margin: 22rpx 0; }.sheet-batch { display: grid; grid-template-columns: 75rpx 1fr; gap: 12rpx; padding: 16rpx 0; border-bottom: 1rpx solid rgba(24,54,46,.08); }.sheet-batch > text { color: #1f5f49; font-size: 20rpx; font-weight: 800; }.sheet-batch > view { display: flex; flex-direction: column; gap: 6rpx; }.sheet-batch > view text:first-child { color: #557348; font-size: 20rpx; font-weight: 700; }.sheet-batch > view text:last-child { color: #7c8b84; font-size: 18rpx; line-height: 1.45; }.batches-sheet .demo-label { display: block; margin-bottom: 18rpx; }
.selected-batch { display: flex; flex-direction: column; gap: 8rpx; margin-top: 18rpx; padding: 18rpx; border-radius: 17rpx; background: #edf3e5; }.selected-batch text:first-child { color: #246b50; font-size: 20rpx; font-weight: 800; }.selected-batch text:last-child { color: #5c7469; font-size: 18rpx; line-height: 1.45; }
.sheet-batch { width: 100%; grid-template-columns: 75rpx 1fr 24rpx; align-items: center; border-radius: 0; background: transparent; text-align: left; }.sheet-batch::after { border: 0; }.sheet-batch.selected { background: #edf3e5; }.sheet-batch > text:last-child { color: #8a9a8c; font-size: 27rpx; }
.info-card { display: flex; flex-direction: column; gap: 12rpx; }.info-card > text:not(.section-title) { color: #6f7f78; font-size: 20rpx; line-height: 1.5; }.after-sale-note { display: flex; flex-direction: column; gap: 8rpx; margin-top: 20rpx; padding: 20rpx; border-radius: 20rpx; background: #f2dfd3; color: #795043; }.after-sale-note text:first-child { font-size: 22rpx; font-weight: 800; }.after-sale-note text:last-child { font-size: 19rpx; line-height: 1.5; }.service-actions { display: grid; grid-template-columns: repeat(3,1fr); gap: 10rpx; margin: 24rpx 0 14rpx; }.service-actions button { min-height: 66rpx; border: 1rpx solid rgba(31,107,82,.16); border-radius: 19rpx; background: rgba(255,255,255,.76); color: #426357; font-size: 20rpx; font-weight: 700; }.receive-button { margin-top: 12rpx; }
.plan-actions{margin-top:20rpx;padding:23rpx}.plan-actions>view{display:grid;grid-template-columns:1fr;gap:9rpx;margin-top:15rpx}.plan-actions button{min-height:63rpx;border:1rpx solid #a7baaf;border-radius:17rpx;color:#315d4d;font-size:19rpx;font-weight:800}.plan-actions button.danger{border-color:#d5a391;color:#994b36}.plan-actions>text:last-child{display:block;margin-top:14rpx;color:#75857e;font-size:18rpx;line-height:1.55}
.sheet-head { display: flex; align-items: flex-start; justify-content: space-between; }.sheet-head > view { display: flex; flex-direction: column; gap: 7rpx; }.sheet-head > button { color: #60736a; font-size: 40rpx; }.timeline { margin: 26rpx 0; }.timeline > view { position: relative; display: flex; gap: 17rpx; min-height: 88rpx; }.timeline > view > text:first-child { position: relative; z-index: 2; width: 22rpx; height: 22rpx; flex: 0 0 auto; margin-top: 4rpx; border: 4rpx solid #d5ddd4; border-radius: 50%; background: white; }.timeline > view:not(:last-child)::after { content: ''; position: absolute; left: 9rpx; top: 26rpx; bottom: 0; width: 3rpx; background: #d5ddd4; }.timeline > view.done > text:first-child { border-color: #246b50; background: #e0eee5; }.timeline > view.done:not(:last-child)::after { background: #246b50; }.timeline > view > view { display: flex; flex-direction: column; gap: 7rpx; }.timeline > view > view text:first-child { color: #6f7f77; font-size: 22rpx; font-weight: 800; }.timeline > view.done > view text:first-child { color: #1f5f49; }.timeline > view > view text:last-child { color: #89968f; font-size: 18rpx; line-height: 1.45; }.logistics-sheet .demo-label { display: block; margin-bottom: 22rpx; }
</style>
