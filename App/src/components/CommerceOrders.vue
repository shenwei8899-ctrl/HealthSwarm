<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
import AppIcon from './AppIcon.vue'
const back = () => uni.navigateBack();
import { ref, computed, onMounted } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppNavBar from "./AppNavBar.vue";
import { commerce } from "../services/commerce.js";
import { useCommercePage } from "../services/commerce-page.js";
const orders = ref([]),
  page = ref(1),
  total = ref(0),
  tab = ref("all");
const { busy, error, run } = useCommercePage(() => {
  orders.value = [];
  total.value = 0;
});
const complete = (order) => ["delivered", "cancelled"].includes(order.status);
const filtered = computed(() =>
  orders.value.filter(
    (o) =>
      tab.value === "all" ||
      (tab.value === "complete" ? complete(o) : !complete(o)),
  ),
);
function load(append = false) {
  return run(async (active) => {
    const number = append ? page.value + 1 : 1;
    const result = await commerce.orders(number);
    if (active()) {
      orders.value = append ? [...orders.value, ...result.items] : result.items;
      page.value = result.page;
      total.value = result.total;
    }
  });
}
onMounted(() => load());
onShow(() => load());
function detail(order) {
  uni.navigateTo({
    url: "/pages/orders/detail?id=" + encodeURIComponent(order.id),
  });
}

const orderDate=value=>{const date=new Date(value);return Number.isFinite(date.getTime())?`${date.getMonth()+1}月${date.getDate()}日 ${String(date.getHours()).padStart(2,'0')}:${String(date.getMinutes()).padStart(2,'0')}`:''}
</script>
<template>

 <view class="screen orders-screen"><AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="back">‹</button><text class="nav-title">我的订单</text><button class="refresh-link" :disabled="busy" @click="load()">{{busy?'读取中':'刷新'}}</button></view></AppNavBar>
  <view class="orders-heading"><text>订单与配送</text></view>
  <view class="tabs"><button v-for="item in [{id:'all',name:'全部'},{id:'delivery',name:'进行中'},{id:'complete',name:'已完成'}]" :key="item.id" :class="{selected:tab===item.id}" :aria-pressed="tab===item.id" @click="tab=item.id">{{item.name}}</button></view>
  <text v-if="error" class="inline-error" role="alert">{{error}}</text>
  <button v-for="order in filtered" :key="order.id" class="order-card" @click="detail(order)"><view class="order-top"><text>{{order.type==='plan'?'计划订单':'食材订单'}}</text><text class="order-state" :class="{attention:order.status==='pending'}">{{order.label}}</text></view><text v-if="order.createdAt" class="order-date">{{orderDate(order.createdAt)}}</text><view v-for="item in order.items.slice(0,2)" :key="item.id" class="order-product"><FoodImageSlot :src="item.image" :label="item.name" class="order-thumb"/><view class="product-copy"><text>{{item.name}}</text><text>数量 {{item.quantity}}</text></view></view><text v-if="order.items.length>2" class="more-items">共 {{order.items.length}} 项商品</text><view class="order-bottom"><view><text>订单金额</text><text class="order-amount">¥{{(order.totalCents/100).toFixed(2)}}</text></view><text class="order-link">查看订单 ›</text></view></button>
  <view v-if="!busy&&!error&&!filtered.length" class="orders-empty"><AppIcon name="order" :size="60"/><text>暂无{{tab==='delivery'?'进行中':tab==='complete'?'已完成':''}}订单</text></view>
  <button v-if="orders.length<total" :disabled="busy" class="more-button" @click="load(true)">{{busy?'正在读取…':'加载更多'}}</button>
 </view>
</template>
<style scoped>

.orders-screen{background:#fafbfc}.refresh-link{min-width:44px;min-height:44px;color:#0674ed;font-size:26rpx}.orders-heading{padding:32rpx 4rpx 32rpx;font-size:50rpx;line-height:1.3;font-weight:500}.tabs{display:flex;padding:5rpx;background:#f0f2f6;border-radius:999rpx;margin-bottom:26rpx;gap:6rpx}.tabs button{flex:1;min-height:44px;font-size:28rpx;color:#65728c;border-radius:999rpx;display:flex;align-items:center;justify-content:center}.tabs .selected{background:#fff;color:#252b35;box-shadow:0 2rpx 8rpx rgba(34,43,58,.05);font-weight:500}.order-card{display:block;width:100%;text-align:left;padding:24rpx;margin:0 0 20rpx;background:#fff;border:1rpx solid #e7ebf2;border-radius:28rpx;color:#252b35}.order-top{display:flex;justify-content:space-between;align-items:center;gap:20rpx;font-size:30rpx;font-weight:500}.order-state{font-size:26rpx;color:#65728c;font-weight:400}.order-state.attention{color:#0674ed}.order-date{display:block;color:#65728c;font-size:24rpx;margin-top:8rpx}.order-product{display:flex;align-items:center;gap:22rpx;margin-top:24rpx}.order-thumb{width:112rpx;height:112rpx;border-radius:18rpx}.product-copy{flex:1;min-width:0}.product-copy>text{display:block;font-size:29rpx;line-height:1.55;overflow-wrap:anywhere}.product-copy>text+text{font-size:25rpx;color:#65728c;margin-top:10rpx}.more-items{display:block;font-size:25rpx;color:#65728c;padding-top:20rpx}.order-bottom{display:flex;justify-content:space-between;align-items:center;gap:18rpx;border-top:1rpx solid #edf0f5;padding-top:22rpx;margin-top:24rpx}.order-bottom>view{display:flex;align-items:baseline;gap:14rpx;font-size:25rpx;color:#65728c}.order-amount{font-size:35rpx;font-weight:600;color:#252b35;font-variant-numeric:tabular-nums}.order-link{font-size:25rpx;color:#0674ed;white-space:nowrap}.orders-empty{padding:90rpx 20rpx;display:flex;flex-direction:column;align-items:center;gap:24rpx;color:#65728c;font-size:29rpx}.more-button{width:100%;min-height:44px;font-size:27rpx;color:#0674ed}
@media(max-width:350px){.tabs button{font-size:14px}.order-date,.product-copy>text+text,.order-link,.order-bottom>view,.more-items{font-size:12px}.product-copy>text{font-size:14px}.order-top{font-size:15px}.order-state{font-size:13px}}
</style>
