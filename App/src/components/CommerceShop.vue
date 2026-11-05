<script setup>
import { openAddressPicker } from '../services/address-navigation.js'
import { resolveCheckoutAddress } from '../services/address-model.js'
import { ref, computed, onMounted } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppNavBar from "./AppNavBar.vue";
import { commerce } from "../services/commerce.js";
import { useCommercePage } from "../services/commerce-page.js";

const props = defineProps({ route: { type: Object, default: () => ({}) } });
const cartOnly = computed(() => props.route.cart === '1');
const products = ref([]),
  cart = ref([]),
  preferredAddressId = ref(""),
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
  address.value = null; preferredAddressId.value = "";
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
const go = (path) => {
  if (path === '/pages/address/index') { quote.value = null; openAddressPicker({ selectedId: address.value?.id, onSelected: id => { preferredAddressId.value = id; quote.value = null } }); return }
  uni.navigateTo({ url: path });
};
const back = () => uni.navigateBack();
async function read(active) {
  const [catalog, basket, addresses, savedMenu] = await Promise.all([
    cartOnly.value ? Promise.resolve({items:[],has_more:false}) : commerce.products(),
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
  address.value = resolveCheckoutAddress(addresses, preferredAddressId.value || address.value?.id);
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
    <AppNavBar centered
      ><view class="nav-row"
        ><button class="icon-button" aria-label="返回" @click="back">‹</button
        ><text class="nav-title">{{cartOnly?'核对采购商品':'选购食材'}}</text
        ><view class="nav-spacer"/></view
      ></AppNavBar
    >
    <view class="page-heading"><view class="heading-copy"
      ><text class="display-title">{{cartOnly?'核对已选商品':'挑选今天需要的食材'}}</text
      ><text class="subtitle"
        >核对商品、数量、配送地址和价格后下单。</text
      ></view><button class="orders-link" @click="go('/pages/orders/index')">我的订单 <text>›</text></button></view>
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
    ><view class="refresh-row"><text>商品与配送信息</text><button class="refresh-button" :disabled="busy" @click="load">
      {{ busy ? "正在更新…" : "刷新" }}
    </button></view>
    <view v-if="!cartOnly && ready && !products.length" class="card commerce-card"
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
    <view class="card commerce-card cart-card"
      ><view class="card-heading"><text class="section-title">已选商品</text><text class="section-meta">{{cart.length}} 种</text></view>
      <view v-if="!cart.length" class="cart-empty"><view class="empty-bag" aria-hidden="true"/><text class="empty-title">{{ready?'还没有选择商品':'正在读取商品…'}}</text><text class="subtitle">{{ready?'从餐单或对话食材包选购后，在这里核对。':'请稍候，正在同步购物车。'}}</text></view>
      <view v-for="item in cart" :key="item.cart_item_id" class="cart-row"
        ><button
          class="item-check" :class="{ 'is-selected': item.selected }" :aria-label="(item.selected?'取消选择':'选择')+item.product_name" :disabled="busy || !item.valid"
          @click="change(() => commerce.select(item, !item.selected))"
        >
          {{ item.selected ? "✓" : "" }}</button
        ><view class="grow"
          ><text>{{ item.product_name }}</text
          ><text class="subtitle">{{
            item.valid
              ? "¥" + money(item.unit_price_cent)
              : item.invalid_reason || "当前不可购买"
          }}</text><text class="subtitle">{{ item.sku_name }} · 可售 {{ item.available_quantity }}</text></view
        ><button
          class="quantity-button" aria-label="减少数量" :disabled="busy || item.quantity <= 1"
          @click="change(() => commerce.quantity(item, item.quantity - 1))"
        >
          −</button
        ><text class="quantity-value">{{ item.quantity }}</text
        ><button
          class="quantity-button" aria-label="增加数量" :disabled="busy || !item.valid"
          @click="change(() => commerce.quantity(item, item.quantity + 1))"
        >
          ＋</button
        ><button class="remove-button" :disabled="busy" @click="change(() => commerce.remove(item))">
          移除
        </button></view
      >
    </view>
    <button
      class="card commerce-card address-button"
      :disabled="busy"
      @click="go('/pages/address/index')"
    >
      <view class="address-copy"><text class="section-meta">配送地址</text><text class="section-title">{{address ? address.name : '添加收货地址'}}<text v-if="address" class="address-phone">{{address.phone}}</text></text><text class="address-detail">{{address ? address.region+' '+address.detail : '选择地址，确认配送范围与运费'}}</text></view><text class="row-chevron">›</text>
    </button>
    <view v-if="address" class="card commerce-card delivery-status">
      <view class="card-heading"><text class="section-title">配送信息</text><text v-if="deliveryState==='supported'" class="delivery-badge">可配送</text></view>
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
        class="slot-button" :class="{ selected: String(slot) === String(s.id) }"
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
    <view v-if="!quote" class="checkout-dock"><text class="checkout-hint">{{!ready?'正在读取采购信息':!cart.length?'选择商品后即可核对价格':!address?'请先添加收货地址':deliveryState!=='supported'?'请先确认配送范围':'核对价格后，再确认下单'}}</text><button
      class="primary-button checkout-button"
      :disabled="busy || !ready || deliveryState !== 'supported' || !cart.some((i) => i.selected && i.valid)"
      @click="preview"
    >
      核对商品与价格
    </button></view>
    <view v-if="quote" class="card commerce-card quote-card"
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
.commerce-screen{background-color:var(--ui-canvas,#f6f7fa);background-image:radial-gradient(ellipse at 0% 0%,rgba(125,174,255,.44),transparent 70%),radial-gradient(ellipse at 100% 0%,rgba(206,178,245,.38),transparent 76%);background-size:100% 410rpx;background-repeat:no-repeat;color:var(--ui-text,#35343f);padding:20rpx 36rpx calc(env(safe-area-inset-bottom) + 228rpx);font-size:28rpx;line-height:1.65}
.nav-spacer{width:80rpx;flex:none}.commerce-screen .icon-button{min-width:44px;min-height:44px}.page-heading{display:flex;align-items:flex-start;gap:20rpx;margin:30rpx 0 22rpx}.heading-copy{flex:1;min-width:0}.commerce-screen .display-title{font-size:40rpx;font-weight:500;line-height:1.4}.commerce-screen .subtitle{display:block;color:var(--ui-muted,#74717f);font-size:25rpx;line-height:1.65}.heading-copy .subtitle{margin-top:12rpx}.orders-link{display:flex;align-items:center;gap:8rpx;flex:none;min-height:44px;font-size:25rpx;color:var(--ui-muted,#74717f)}.orders-link text{font-size:36rpx}
.commerce-card{padding:30rpx;margin:22rpx 0;display:flex;flex-direction:column;gap:16rpx;box-sizing:border-box;background:linear-gradient(180deg,rgba(255,255,255,.30),rgba(255,255,255,.96));border:1px solid rgba(255,255,255,.88);border-radius:38rpx;box-shadow:inset 0 1px 0 #fff}.commerce-screen .section-title{font-size:30rpx;font-weight:500;line-height:1.5}.card-heading{display:flex;align-items:center;justify-content:space-between;gap:16rpx}.section-meta{font-size:24rpx;color:var(--ui-muted,#74717f)}
.refresh-row{display:flex;align-items:center;justify-content:space-between;gap:16rpx;color:var(--ui-muted,#74717f);font-size:24rpx}.refresh-button{min-height:44px;padding:8rpx 22rpx;font-size:25rpx;color:var(--ui-text,#35343f)}.cart-empty{display:flex;flex-direction:column;align-items:center;text-align:center;padding:24rpx 10rpx 20rpx;gap:12rpx}.empty-title{font-size:29rpx;font-weight:500}.empty-bag{position:relative;width:56rpx;height:52rpx;border:2rpx solid #aaa6b8;border-radius:12rpx 12rpx 16rpx 16rpx;margin:14rpx 0 12rpx;background:linear-gradient(145deg,#f3f0fa,#e9edf7)}.empty-bag::before{content:'';position:absolute;left:17rpx;top:-15rpx;width:19rpx;height:22rpx;border:2rpx solid #aaa6b8;border-bottom:0;border-radius:15rpx 15rpx 0 0}
.product-row,.cart-row{display:flex;flex-direction:row;align-items:center;gap:14rpx}.product-row image{width:112rpx;height:112rpx;border-radius:22rpx;flex:none}.grow{flex:1;min-width:0}.grow text{display:block;overflow-wrap:anywhere}.cart-row{flex-wrap:wrap;border-top:1rpx solid var(--ui-line,#eae8f0);padding:24rpx 0 8rpx}.cart-row .grow{flex-basis:calc(100% - 110rpx)}.cart-row button{font-size:25rpx;min-height:44px}.item-check{display:flex;align-items:center;justify-content:center;min-width:44px;width:44px;flex:none;color:#fff;background:radial-gradient(circle at center,#edeaf3 15px,transparent 16px);font-size:28rpx}.item-check.is-selected{background:radial-gradient(circle at center,#303739 15px,transparent 16px)}.quantity-button{width:44px;background:#f0eff5;border-radius:16rpx}.quantity-value{min-width:40rpx;text-align:center;font-variant-numeric:tabular-nums}.remove-button{margin-left:auto;padding:0 16rpx;color:var(--ui-muted,#74717f)}
.address-button{width:100%;text-align:left;flex-direction:row;align-items:center;gap:20rpx;color:inherit;white-space:normal;line-height:1.65}.address-copy{display:flex;flex-direction:column;gap:12rpx;flex:1;min-width:0}.address-phone{display:inline-block;font-size:26rpx;font-weight:400;margin-left:18rpx;color:var(--ui-muted,#74717f)}.address-detail{font-size:26rpx;color:var(--ui-muted,#74717f);overflow-wrap:anywhere}.row-chevron{font-size:42rpx;color:#928e9e;flex:none}.delivery-badge{font-size:23rpx;color:#4b786b;background:#eaf3ef;padding:4rpx 16rpx;border-radius:999rpx}.delivery-status{gap:12rpx}.slot-button{font-size:26rpx;min-height:44px;padding:18rpx 24rpx;border-radius:20rpx;background:#f1f0f6;text-align:left}.slot-button.selected{background:var(--ui-accent,#303739);color:#fff}
.commerce-screen .primary-button{background:var(--ui-accent,#303739);color:#fff;border:0;border-radius:28rpx;min-height:48px;padding:22rpx;font-size:29rpx;font-weight:500;line-height:1.5}.commerce-screen .secondary-button{font-size:26rpx;min-height:44px;padding:16rpx 24rpx;border:1rpx solid #e5e2ec;border-radius:22rpx;background:rgba(255,255,255,.6);line-height:1.6}.commerce-screen button[disabled]{opacity:.5}.commerce-screen .checkout-button[disabled]{opacity:1;background:#e2e3eb;color:#797783}.checkout-dock{position:fixed;z-index:12;left:24rpx;right:24rpx;bottom:calc(env(safe-area-inset-bottom) + 20rpx);padding:14rpx;box-sizing:border-box;border:1px solid rgba(255,255,255,.88);border-radius:40rpx;background:linear-gradient(180deg,rgba(245,245,252,.96),rgba(255,255,255,.98));box-shadow:inset 0 1px 0 #fff,0 6rpx 24rpx rgba(78,76,112,.04)}.checkout-hint{display:block;text-align:center;font-size:23rpx;line-height:1.5;color:var(--ui-muted,#74717f);margin:2rpx 0 12rpx}.checkout-button{width:100%}.quote-card{gap:22rpx}.commerce-screen .inline-error{font-size:26rpx;overflow-wrap:anywhere}.commerce-screen button:active:not([disabled]){opacity:.75}
.cart-row .grow{flex-basis:calc(100% - 44px - 14rpx)}
/* #ifdef H5 */
.checkout-dock{max-width:calc(480px - 48rpx);margin:0 auto}
/* #endif */
</style>
