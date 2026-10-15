<script setup>
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
</script>
<template>
  <view class="screen"
    ><AppNavBar
      ><view class="nav-row"
        ><button class="icon-button" @click="back">‹</button
        ><text class="nav-title">我的订单</text><text /></view></AppNavBar
    ><view class="page-heading"
      ><text class="display-title">订单与配送进度</text
      ><text class="subtitle">查看支付、配送和售后的实际状态。</text></view
    ><view class="tabs"
      ><button
        v-for="item in [
          { id: 'all', name: '全部' },
          { id: 'delivery', name: '进行中' },
          { id: 'complete', name: '已完成' },
        ]"
        :key="item.id"
        :class="{ selected: tab === item.id }"
        @click="tab = item.id"
      >
        {{ item.name }}
      </button></view
    ><text v-if="error" class="inline-error">{{ error }}</text
    ><button class="secondary-button" :disabled="busy" @click="load()">
      {{ busy ? "正在读取…" : "刷新订单" }}</button
    ><view
      v-for="order in filtered"
      :key="order.id"
      class="card order-card"
      @click="detail(order)"
      ><text class="section-title"
        >{{ order.type === "plan" ? "21天计划" : "食材订单" }} ·
        {{ order.label }}</text
      ><text class="subtitle">{{ order.id }}</text
      ><text v-for="item in order.items.slice(0, 3)" :key="item.id"
        >{{ item.name }} × {{ item.quantity }}</text
      ><text>订单金额 ¥{{ (order.totalCents / 100).toFixed(2) }}</text
      ><button class="secondary-button" @click.stop="detail(order)">
        查看订单
      </button></view
    ><text v-if="!busy && !filtered.length" class="safe-note"
      >当前没有此类订单</text
    ><button
      v-if="orders.length < total"
      :disabled="busy"
      class="secondary-button"
      @click="load(true)"
    >
      加载更多订单
    </button></view
  >
</template>
<style scoped>
.order-card {
  padding: 28rpx;
  margin: 24rpx 0;
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}
.tabs {
  display: flex;
  gap: 12rpx;
  margin: 24rpx 0;
}
.tabs button {
  flex: 1;
  padding: 18rpx;
}
.selected {
  background: #246b50;
  color: white;
}
</style>
