<script setup>
import { ref, computed, onMounted } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppNavBar from "./AppNavBar.vue";
import { commerce } from "../services/commerce.js";
import { useCommercePage } from "../services/commerce-page.js";

const props = defineProps({ route: { type: Object, default: () => ({}) } });
const products = ref([]),
  cart = ref([]),
  address = ref(null),
  quote = ref(null),
  slots = ref([]),
  slot = ref(0);
const deliveryState = ref("unselected"), deliveryMessage = ref("");
const next = ref(""),
  more = ref(false),
  ready = ref(false),
  mealName = computed(() => props.route.meal || (props.route.daily ? "dinner" : "")),
  menu = ref(null),
  sourceNote = computed(() => props.route.plan ? "周期计划暂不能购买。" : ""),
  created = ref(""),
  pending = ref(null);
const { busy, error, run } = useCommercePage(() => {
  menu.value = null;
  products.value = [];
  cart.value = [];
  address.value = null;
  slots.value = [];
  quote.value = null;
  ready.value = false;
  pending.value = null;
  created.value = "";
  next.value = "";
  more.value = false;
  deliveryState.value = "unselected";
  deliveryMessage.value = "";
});
const money = (cents) => (Number(cents || 0) / 100).toFixed(2);
const go = (path) => uni.navigateTo({ url: path });
const back = () => uni.navigateBack();
async function read(active) {
  const [catalog, basket, addresses, savedMenu] = await Promise.all([
    commerce.products(),
    commerce.cart(),
    commerce.addresses(),
    mealName.value ? commerce.meal(mealName.value, props.route.date) : Promise.resolve(null),
  ]);
  if (!active()) return;
  menu.value = savedMenu;
  products.value = catalog.items;
  next.value = catalog.next_cursor;
  more.value = catalog.has_more;
  cart.value = basket.items;
  address.value = addresses.find((a) => a.isDefault) || null;
  slots.value = [];
  slot.value = 0;
  quote.value = null;
  ready.value = true;
  pending.value = commerce.pendingOrder();
  await checkDelivery(active);
}
async function checkDelivery(active) {
  slots.value = [];
  slot.value = 0;
  quote.value = null;
  deliveryMessage.value = "";
  if (!address.value) { deliveryState.value = "unselected"; return; }
  deliveryState.value = "checking";
  try {
    const delivery = await commerce.slots(address.value.id);
    if (active()) {
      if (delivery.supported === false) {
        deliveryState.value = "unsupported";
        deliveryMessage.value = delivery.message || "当前地址暂不支持配送，请更换收货地址";
        return;
      }
      deliveryState.value = "supported";
      deliveryMessage.value = delivery.message || "当前地址支持配送";
      slots.value = delivery.items.filter((s) => s.available);
      slot.value = slots.value[0]?.id || 0;
    }
  } catch (e) {
    if (!active()) return;
    if ([401, "SESSION_CHANGED"].includes(e.code)) throw e;
    deliveryState.value = Number(e.code) === 40914 ? "unsupported" : "error";
    deliveryMessage.value = deliveryState.value === "unsupported" ? e.message : "配送状态暂时无法确认，请重新检查";
  }
}
function retryDelivery() { return run(checkDelivery); }
function load() {
  return run(read);
}
onMounted(load);
onShow(load);
function loadMore() {
  return run(async (active) => {
    const page = await commerce.products(next.value);
    if (active()) {
      products.value.push(...page.items);
      next.value = page.next_cursor;
      more.value = page.has_more;
    }
  });
}
function change(operation) {
  return run(async (active) => {
    quote.value = null;
    const result = await operation();
    if (active()) cart.value = result.items;
  });
}
function addMeal() {
  return change(() => commerce.addMeal(menu.value));
}
function preview() {
  return run(async (active) => {
    if (commerce.pendingOrder()) throw new Error("请先确认上次下单结果");
    if (!address.value) throw new Error("请先选择配送地址");
    if (deliveryState.value !== "supported") throw new Error(deliveryMessage.value || "请先确认配送状态");
    if (!cart.value.some((i) => i.selected && i.valid))
      throw new Error("请勾选可购买的商品");
    const result = await commerce.quote(
      cart.value,
      address.value.id,
      slot.value,
      menu.value?.available ? menu.value : null,
    );
    if (active()) quote.value = result;
  });
}
function submit() {
  return run(async (active) => {
    if (
      !quote.value?.checkout_token ||
      Date.parse(quote.value.expires_at) <= Date.now()
    ) {
      quote.value = null;
      throw new Error("报价已失效，请重新核对商品和价格");
    }
    let result;
    try {
      result = await commerce.createOrder(quote.value.checkout_token);
    } finally {
      if (active()) pending.value = commerce.pendingOrder();
    }
    if (!active()) return;
    created.value = result.order_sn;
    quote.value = null;
    go("/pages/orders/detail?id=" + encodeURIComponent(created.value));
  });
}
function retryOrder() {
  return run(async (active) => {
    let result;
    try {
      result = await commerce.retryOrder();
    } finally {
      if (active()) pending.value = commerce.pendingOrder();
    }
    if (active()) {
      created.value = result.order_sn;
      quote.value = null;
      go("/pages/orders/detail?id=" + encodeURIComponent(created.value));
    }
  });
}
</script>

<template>
  <view class="screen commerce-screen">
    <AppNavBar
      ><view class="nav-row"
        ><button class="icon-button" @click="back">‹</button
        ><text class="nav-title">选购食材</text
        ><button class="text-button" @click="go('/pages/orders/index')">
          订单
        </button></view
      ></AppNavBar
    >
    <view class="page-heading"
      ><text class="display-title">挑选今天需要的食材</text
      ><text class="subtitle"
        >核对商品、数量、配送地址和价格后下单。</text
      ></view
    >
    <view v-if="mealName && ready" class="card commerce-card">
      <text class="section-title">{{ menu?.date }} · {{ { breakfast:'早餐', lunch:'午餐', dinner:'晚餐' }[mealName] || mealName }}安排</text>
      <text v-if="menu?.is_local_fixture" class="safe-note">本地联调菜单与商品 · 未经个体化营养评估</text>
      <text v-for="dish in menu?.dishes || []" :key="dish.recipe_ref">{{ dish.recipe_name }}</text>
      <text v-if="!menu?.available" class="inline-error">{{ menu?.message || '本餐菜单或商品尚不可购买，请核对下列原因。' }}</text>
      <text v-for="(issue, n) in menu?.issues || []" :key="n">{{ issue.message || issue.issue_code }}</text>
      <view v-for="item in menu?.items || []" :key="item.sku.sku_id">
        <text>{{ item.sku.product_name }} · {{ item.sku.sku_name }} · ¥{{ money(item.sku.price_cent) }} · 可售 {{ item.sku.available_quantity }} · 本餐 {{ item.quantity }}件</text>
      </view>
      <button v-if="menu?.available" class="primary-button" :disabled="busy || !!pending" @click="addMeal">选购本餐食材</button>
      <text v-if="menu?.available" class="subtitle">加入后可调整数量。菜谱保持购买时的版本；采购数量变化不会自动重新计算营养。</text>
    </view>
    <text v-if="sourceNote" class="safe-note">{{ sourceNote }}</text>
    <view v-if="pending" class="card commerce-card"
      ><text>上次下单结果尚未确认，请先查看订单或重试原下单。</text
      ><button
        class="secondary-button"
        :disabled="busy"
        @click="go('/pages/orders/index')"
      >
        查看订单</button
      ><button class="primary-button" :disabled="busy" @click="retryOrder">
        重试原下单
      </button></view
    >
    <text v-if="error" class="inline-error">{{ error }}</text
    ><button class="secondary-button" :disabled="busy" @click="load">
      {{ busy ? "正在处理…" : "刷新商品与购物车" }}
    </button>
    <view v-if="ready && !products.length" class="card commerce-card"
      ><text>暂时没有可购买的商品</text></view
    >
    <view
      v-for="item in products"
      :key="item.sku_id"
      class="card commerce-card product-row"
      ><image
        v-if="item.image_url"
        :src="item.image_url"
        mode="aspectFill"
      /><view class="grow"
        ><text class="section-title">{{ item.product_name }}</text
        ><text class="subtitle"
          >{{ item.sku_name }} · {{ item.net_content?.value
          }}{{ item.net_content?.unit }}</text
        ><text>¥{{ money(item.price_cent) }}</text></view
      ><button
        :disabled="busy"
        class="secondary-button"
        @click="change(() => commerce.add(item.sku_id))"
      >
        加入
      </button></view
    >
    <button
      v-if="more"
      :disabled="busy"
      class="secondary-button"
      @click="loadMore"
    >
      加载更多商品
    </button>
    <view class="card commerce-card"
      ><text class="section-title">购物车</text
      ><text v-if="!cart.length" class="subtitle">还没有选择商品</text>
      <view v-for="item in cart" :key="item.cart_item_id" class="cart-row"
        ><button
          :disabled="busy || !item.valid"
          @click="change(() => commerce.select(item, !item.selected))"
        >
          {{ item.selected ? "☑" : "□" }}</button
        ><view class="grow"
          ><text>{{ item.product_name }}</text
          ><text class="subtitle">{{
            item.valid
              ? "¥" + money(item.unit_price_cent)
              : item.invalid_reason || "当前不可购买"
          }}</text><text class="subtitle">{{ item.sku_name }} · 可售 {{ item.available_quantity }}</text></view
        ><button
          :disabled="busy || item.quantity <= 1"
          @click="change(() => commerce.quantity(item, item.quantity - 1))"
        >
          −</button
        ><text>{{ item.quantity }}</text
        ><button
          :disabled="busy || !item.valid"
          @click="change(() => commerce.quantity(item, item.quantity + 1))"
        >
          ＋</button
        ><button :disabled="busy" @click="change(() => commerce.remove(item))">
          移除
        </button></view
      >
    </view>
    <button
      class="card commerce-card address-button"
      :disabled="busy"
      @click="go('/pages/address/index')"
    >
      <text class="section-title">{{
        address ? address.name + " " + address.phone : "选择配送地址"
      }}</text
      ><text v-if="address">{{ address.region }} {{ address.detail }}</text>
    </button>
    <view v-if="address" class="card commerce-card delivery-status">
      <text class="section-title">配送状态</text>
      <text :class="{ 'inline-error': deliveryState === 'unsupported' || deliveryState === 'error' }">{{ deliveryState === 'checking' ? '正在检查配送范围…' : deliveryMessage }}</text>
      <text v-if="deliveryState === 'supported'" class="subtitle">运费以结算时核价为准。</text>
      <button v-if="deliveryState === 'unsupported'" class="secondary-button" :disabled="busy" @click="go('/pages/address/index')">更换收货地址</button>
      <button v-if="deliveryState === 'unsupported' || deliveryState === 'error'" class="secondary-button" :disabled="busy" @click="retryDelivery">重新检查配送</button>
    </view>
    <view v-if="slots.length" class="card commerce-card"
      ><text class="section-title">配送时段</text
      ><button
        v-for="s in slots"
        :key="s.id"
        :disabled="busy"
        :class="{ selected: String(slot) === String(s.id) }"
        @click="
          slot = s.id;
          quote = null;
        "
      >
        {{ s.name || s.start_time + "—" + s.end_time }} · ¥{{
          money(s.extra_fee_cent)
        }}
      </button></view
    >
    <button
      class="primary-button"
      :disabled="busy || !ready || deliveryState !== 'supported' || !cart.some((i) => i.selected && i.valid)"
      @click="preview"
    >
      核对商品与价格
    </button>
    <view v-if="quote" class="card commerce-card"
      ><text class="section-title">结算确认</text
      ><text
        >{{ quote.address_snapshot?.receiver }}
        {{ quote.address_snapshot?.mobile }}</text
      ><text
        >{{ quote.address_snapshot?.region }}
        {{ quote.address_snapshot?.detail }}</text
      ><text v-for="item in quote.items" :key="item.sku_id"
        >{{ item.snapshot?.product_name }} × {{ item.quantity }} · ¥{{
          money(item.line_amount_cent)
        }}</text
      ><text
        >商品 ¥{{ money(quote.goods_amount_cent) }} · 配送 ¥{{
          money(quote.shipping_fee_cent)
        }}
        · 优惠 ¥{{ money(quote.discount_amount_cent) }}</text
      ><text class="section-title"
        >应付 ¥{{ money(quote.payable_amount_cent) }}</text
      ><button class="primary-button" :disabled="busy" @click="submit">
        确认下单</button
      ><button class="secondary-button" :disabled="busy" @click="quote = null">
        返回修改
      </button></view
    >
    <button
      v-if="created"
      class="secondary-button"
      @click="go('/pages/orders/detail?id=' + encodeURIComponent(created))"
    >
      查看刚创建的订单
    </button>
  </view>
</template>

<style scoped>
.commerce-screen {
  padding-bottom: 60rpx;
}
.commerce-card {
  padding: 26rpx;
  margin: 22rpx 0;
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}
.product-row,
.cart-row {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 14rpx;
}
.product-row image {
  width: 120rpx;
  height: 120rpx;
  border-radius: 18rpx;
}
.grow {
  flex: 1;
  min-width: 0;
}
.grow text {
  display: block;
}
.cart-row {
  flex-wrap: wrap;
  border-bottom: 1px solid #eee;
  padding: 14rpx 0;
}
.cart-row button {
  font-size:25rpx;
  padding: 10rpx;
}
.address-button {
  width: 100%;
  text-align: left;
}
.text-button {
  font-size: 26rpx;
  color: #292a2e;
}
.selected {
  background: #292a2e;
  color: white;
}
</style>
