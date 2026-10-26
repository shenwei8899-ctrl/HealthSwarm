<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
import PlanOrderControls from './PlanOrderControls.vue'
const back = () => uni.navigateBack();
import { ref, computed, onMounted } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppNavBar from "./AppNavBar.vue";
import { commerce } from "../services/commerce.js";
import { useCommercePage } from "../services/commerce-page.js";
const props = defineProps({ id: { type: String, required: true } });
const orderId = computed(() => props.id);
const pending = ref(null),
  order = ref(null),
  events = ref([]),
  history = ref([]),
  form = ref(null),
  eligibility = ref(null),
  message = ref(""),
  batch = ref("");
const { busy, error, run } = useCommercePage(() => {
  order.value = null;
  events.value = [];
  history.value = [];
  pending.value = null;
  form.value = null;
  eligibility.value = null;
  message.value = "";
});
const money = (cents) => (Number(cents || 0) / 100).toFixed(2);
const allowed = (action) => order.value?.allowedActions.includes(action);
async function read(active) {
  const [detail, after] = await Promise.all([
    commerce.order(orderId.value),
    commerce.afterSales(orderId.value),
  ]);
  if (active()) {
    order.value = detail;
    history.value = after;
    pending.value = commerce.pendingAfterSale(orderId.value);
  }
}
function load() {
  return run(read);
}
onMounted(load);
onShow(load);
function action(name) {
  return run(async (active) => {
    const result = await commerce.action(orderId.value, name);
    if (active()) order.value = result;
  });
}
function pay() {
  return run(async (active) => {
    const result = await commerce.payOrder(orderId.value);
    if (!active()) return;
    message.value =
      result.status === "paid"
        ? "支付已确认"
        : result.interrupted
          ? "支付未完成或结果待确认，请刷新查询。"
          : "支付结果待确认，请刷新查询。";
    await read(active);
  });
}
function localPay() {
  uni.showModal({ title: '本地测试支付', content: '此操作不扣款，只验证本地订单、库存和履约流程。', confirmText: '测试付款', success: ({confirm}) => {
    if (confirm) run(async (active) => { await commerce.localTestPay(orderId.value); if (active()) message.value = '本地测试付款已由后端确认 · 未实际扣款'; await read(active); });
  } });
}
function cook() { uni.navigateTo({ url: '/pages/cook/index?commerce=1&id=' + encodeURIComponent(orderId.value) }); }
function query() {
  return run(async (active) => {
    const result = await commerce.paymentStatus(orderId.value);
    if (active())
      message.value =
        result.status === "paid"
          ? "支付已确认"
          : "当前支付状态：" + result.status;
    await read(active);
  });
}
function logistics() {
  return run(async (active) => {
    const result = await commerce.logistics(orderId.value);
    if (active()) events.value = result.events;
  });
}
function repurchase() {
  const names=(order.value?.items||[]).map(item=>item.name||item.product_name||item.title).filter(Boolean).join('、');
  const question=names?'我想再买 '+names+' 对应的食材包，有哪些可选？':'我想再买上次订单里的食材包，请帮我核对。';
  uni.navigateTo({url:'/pages/chat/index?question='+encodeURIComponent(question)});
}
function afterSale() {
  return run(async (active) => {
    if (commerce.pendingAfterSale(orderId.value))
      throw new Error("上次售后提交结果尚未确认，请先重试原申请");
    const result = await commerce.eligibility(orderId.value);
    if (active()) {
      eligibility.value = result;
      batch.value = "";
      form.value = {
        type: "reship",
        reason_code: result.allowed_reason_codes[0] || "",
        description: "",
        evidence_urls: [],
        items: result.items
          .filter((i) => i.eligible)
          .map((i) => ({
            order_item_id: i.id,
            quantity: 1,
            selected: false,
            max: Number(i.nums),
            name: i.title,
            delivery_batch_id: i.delivery_batch_id,
          })),
      };
    }
  });
}
function photo() {
  return run(async (active) => {
    const paths = await new Promise((resolve, reject) =>
      uni.chooseImage({
        count: 3 - form.value.evidence_urls.length,
        sizeType: ["compressed"],
        success: (r) => resolve(r.tempFilePaths),
        fail: reject,
      }),
    );
    for (const path of paths) {
      if (!active()) return;
      const url = await commerce.upload(path);
      if (active()) form.value.evidence_urls.push(url);
    }
  });
}
function retrySale() {
  return run(async (active) => {
    const result = await commerce.retryAfterSale(orderId.value);
    if (active()) {
      message.value = "已确认" + result.items.length + "件商品的售后申请。";
      form.value = null;
      await read(active);
    }
  });
}
function submit() {
  return run(async (active) => {
    const items = form.value.items
      .filter(
        (i) =>
          i.selected &&
          (!batch.value || String(i.delivery_batch_id) === String(batch.value)),
      )
      .map((i) => ({
        order_item_id: i.order_item_id,
        quantity: Number(i.quantity),
      }));
    if (items.length !== 1) throw new Error("请每次选择一件受影响商品申请售后");
    if (order.value.type === "plan" && !batch.value)
      throw new Error("请先选择配送批次");
    let result;
    try {
      result = await commerce.submitAfterSale({
        order_sn: orderId.value,
        type: form.value.type,
        reason_code: form.value.reason_code,
        description: form.value.description,
        evidence_urls: [...form.value.evidence_urls],
        items,
      });
    } catch (e) {
      if (active()) pending.value = commerce.pendingAfterSale(orderId.value);
      throw e;
    }
    if (active()) {
      message.value =
        "已提交" +
        result.items.length +
        "件商品的售后申请，处理结果请以实际回执为准。";
      form.value = null;
      await read(active);
    }
  });
}
const reasons = {
  not_received: "未收到",
  wrong_item: "商品不符",
  missing_item: "少件漏件",
  quality_issue: "商品质量",
  damaged: "破损",
  other: "其他问题",
  platform_non_delivery: "未履约",
  legal_mandatory: "其他需核对事项",
};
const afterStatus = {
  1: "已提交",
  2: "审核通过，查看处理结果",
  3: "已拒绝",
  4: "已撤销",
  5: "已处理",
};
const deliveryStep=computed(()=>order.value?.status==='delivered'?2:order.value?.status==='shipping'?1:order.value?.status==='paid'?0:-1)
const statusDescription=computed(()=>({pending:'核对订单后，完成付款。',paid:'订单已确认，等待配送。',shipping:'食材正在送往你家。',delivered:'食材已收到，一起做顿好饭。',cancelled:'订单已结束。',refund_pending:'售后处理中，请查看处理结果。'}[order.value?.status]||''))
const paymentLabel=computed(()=>({paid:'已支付',unpaid:'未支付',paying:'结果待确认',refunding:'退款中',refund_pending:'退款处理中',refunded:'已退款'}[order.value?.paymentStatus]||'待核对'))
function dateText(value){const d=new Date(value);if(!Number.isFinite(d.getTime()))return '';return d.getFullYear()+'年'+(d.getMonth()+1)+'月'+d.getDate()+'日 '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')}

</script>
<template>
 <view class="screen order-screen"><AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="back">‹</button><text class="nav-title">订单详情</text><button class="refresh-link" :disabled="busy" @click="load">{{busy?'读取中':'刷新'}}</button></view></AppNavBar>
  <text v-if="error" class="inline-error" role="alert">{{error}}</text><text v-if="message" class="safe-note">{{message}}</text>
  <view v-if="pending" class="card detail-card"><text>上次售后申请结果待确认</text><button class="primary-button" :disabled="busy" @click="retrySale">确认原售后申请</button></view>
  <template v-if="order">
   <view class="order-status"><text class="status-title">{{order.label}}</text><text class="status-description">{{statusDescription}}</text></view>
   <view v-if="deliveryStep>=0" class="delivery-progress"><view v-for="(label,index) in ['已下单','配送中',order.status==='delivered'?'已收货':'待收货']" :key="index" class="progress-step" :class="{complete:index<=deliveryStep}"><view class="progress-point">{{index<=deliveryStep?'✓':''}}</view><text>{{label}}</text></view></view>
   <view class="card order-goods"><view class="card-heading"><text>订单商品</text><text>{{order.items.length}} 项</text></view><view v-for="item in order.items" :key="item.id" class="order-item"><FoodImageSlot :src="item.image" :label="item.name" class="order-image"/><view class="order-item-copy"><text>{{item.name}}</text><text>{{item.sku_snapshot?.sku_name||''}}</text></view><view class="order-item-amount"><text>¥{{money(item.priceCents*item.quantity)}}</text><text>×{{item.quantity}}</text></view></view><view class="order-total"><text>订单金额</text><text>¥{{money(order.totalCents)}}</text></view></view>
   <view v-if="order.address" class="card order-address"><view class="address-icon" aria-hidden="true">⌖</view><view><text>{{order.address.receiver}} · {{order.address.mobile}}</text><text>{{order.address.region}} {{order.address.detail}}</text></view></view>
   <view class="card order-meta"><text class="card-heading">订单信息</text><view><text>订单编号</text><button @click="uni.setClipboardData({data:order.id})">{{order.id}} <text>复制</text></button></view><view v-if="order.createdAt"><text>下单时间</text><text>{{dateText(order.createdAt)}}</text></view><view><text>支付状态</text><text>{{paymentLabel}}</text></view></view>
   <text v-if="order.localTestPayment" class="safe-note">本地测试订单 · 测试付款不扣款</text>
   <view class="order-primary-actions"><button v-if="order.localTestPayment&&allowed('pay')" class="primary-button" :disabled="busy" @click="localPay">本地测试支付（不扣款）</button><button v-if="allowed('pay')&&!order.localTestPayment" class="primary-button" :disabled="busy" @click="pay">微信支付 ¥{{money(order.totalCents)}}</button><button v-if="allowed('receive')" class="primary-button" :disabled="busy" @click="action('receipt')">确认收货</button><button v-if="order.status==='delivered'&&order.mealSnapshot" class="primary-button" :disabled="busy" @click="cook">开始做饭，记一餐</button><button v-if="allowed('afterSale')" class="secondary-button" :disabled="busy" @click="afterSale">申请售后</button></view>
   <view class="order-secondary-actions"><button v-if="order.status==='pending'" :disabled="busy" @click="query">查询支付结果</button><button v-if="allowed('cancel')" :disabled="busy" @click="action('cancel')">取消订单</button><button :disabled="busy" @click="logistics">查看物流</button><button v-if="allowed('repurchase')" :disabled="busy" @click="repurchase">再买一单</button></view>
      <PlanOrderControls v-if="order.type==='plan' && order.plan" :order="order" @changed="load"/>
      <view v-if="events.length" class="card detail-card"
        ><text class="section-title">物流进度</text
        ><text v-for="(event, index) in events" :key="event.id || index"
          >{{ event.description || event.event_type }}
          {{
            event.occurred_at
              ? new Date(Number(event.occurred_at) * 1000).toLocaleString()
              : ""
          }}</text
        ></view
      ><view v-if="form" class="card detail-card"
        ><text class="section-title">申请售后</text
        ><view v-if="order.type === 'plan'"
          ><text>选择批次</text
          ><button
            v-for="b in order.batches"
            :key="b.id"
            :disabled="
              busy || !['shipped', 'delivering', 'delivered'].includes(b.status)
            "
            :class="{ selected: String(batch) === String(b.id) }"
            @click="
              batch = b.id;
              form.items.forEach((i) => (i.selected = false));
            "
          >
            第{{ b.batch_no }}批 · {{ b.delivery_date }}
          </button></view
        ><view
          v-for="item in form.items.filter(
            (i) =>
              order.type !== 'plan' ||
              String(i.delivery_batch_id) === String(batch),
          )"
          :key="item.order_item_id"
          class="sale-row"
          ><button :disabled="busy" @click="form.items.forEach(i => i.selected = i === item ? !i.selected : false)">
            {{ item.selected ? "☑" : "□" }} {{ item.name }}</button
          ><input
            v-model="item.quantity"
            class="field-input"
            type="number"
            :disabled="busy"
          /><text>最多{{ item.max }}件</text></view
        ><text>期望结果</text
        ><view class="choices"
          ><button
            v-for="choice in [
              { id: 'reship', name: '希望补发' },
              { id: 'refund_only', name: '希望退款' },
              { id: 'contact', name: '请工作人员联系我' },
            ]"
            :key="choice.id"
            :disabled="busy"
            :class="{ selected: form.type === choice.id }"
            @click="form.type = choice.id"
          >
            {{ choice.name }}
          </button></view
        ><text>问题原因</text
        ><view class="choices"
          ><button
            v-for="reason in eligibility.allowed_reason_codes"
            :key="reason"
            :disabled="busy"
            :class="{ selected: form.reason_code === reason }"
            @click="form.reason_code = reason"
          >
            {{ reasons[reason] || reason }}
          </button></view
        ><textarea
          class="field-input"
          v-model="form.description"
          maxlength="500"
          placeholder="说明受影响的商品和问题"
          :disabled="busy"
        /><view class="choices"
          ><image
            v-for="(photo, index) in form.evidence_urls"
            :key="photo"
            :src="photo"
            mode="aspectFill"
            @click="!busy && form.evidence_urls.splice(index, 1)"
          /><button
            :disabled="busy || form.evidence_urls.length >= 3"
            @click="photo"
          >
            添加照片（最多3张）
          </button></view
        ><text class="subtitle"
          >期望结果需要工作人员核对；提交不会直接完成退款。</text
        ><button class="primary-button" :disabled="busy" @click="submit">
          确认提交售后申请</button
        ><button class="secondary-button" :disabled="busy" @click="form = null">
          暂不提交
        </button></view
      ><view v-if="history.length" class="card detail-card"
        ><text class="section-title">售后记录</text
        ><text v-for="entry in history" :key="entry.id"
          >{{ entry.aftersale_sn }} ·
          {{ afterStatus[entry.status] || "处理中" }} · {{ entry.reason }}</text
        ></view
      ></template
    ></view
  >
</template>
<style scoped>
.order-screen{background:#fafbfc}.refresh-link{min-width:80rpx;min-height:44px;color:#0674ed;font-size:25rpx}.order-status{padding:30rpx 8rpx 22rpx}.status-title{display:block;font-size:54rpx;font-weight:500;line-height:1.3;letter-spacing:-1rpx}.status-description{display:block;font-size:28rpx;color:#7e8aa1;margin-top:14rpx;line-height:1.6}.delivery-progress{display:flex;justify-content:space-between;margin:14rpx 12rpx 32rpx}.progress-step{display:flex;flex:1;position:relative;flex-direction:column;align-items:center;gap:12rpx;font-size:24rpx;color:#65728c}.progress-step:before{content:'';position:absolute;top:24rpx;left:50%;width:100%;height:3rpx;background:#dce1eb}.progress-step:last-child:before{display:none}.progress-point{width:48rpx;height:48rpx;border-radius:50%;background:#e2e6ee;box-shadow:0 0 0 6rpx #fafbfc;position:relative;z-index:1;color:#fff;display:flex;align-items:center;justify-content:center;font-size:28rpx}.complete .progress-point{background:#2184ff}.complete:not(:last-child):before{background:#80b8ff}.order-goods{padding:24rpx 22rpx 0}.card-heading{display:flex;justify-content:space-between;color:#6f7d96;font-size:25rpx;font-weight:500;margin-bottom:10rpx}.card-heading>text:last-child{font-weight:400;color:#65728c}.order-item{display:flex;align-items:center;gap:20rpx;padding:18rpx 0}.order-image{width:116rpx;height:116rpx;border-radius:18rpx}.order-item-copy{flex:1;min-width:0}.order-item-copy>text:first-child{display:block;font-size:29rpx;font-weight:500;line-height:1.5;overflow-wrap:anywhere}.order-item-copy>text+text{display:block;font-size:24rpx;color:#65728c;margin-top:8rpx}.order-item-amount{flex-shrink:0;text-align:right;font-size:27rpx;font-variant-numeric:tabular-nums}.order-item-amount text{display:block}.order-item-amount text+text{margin-top:8rpx;font-size:24rpx;color:#65728c}.order-total{display:flex;justify-content:space-between;align-items:baseline;border-top:1rpx solid #edf0f5;margin-top:10rpx;padding:20rpx 0;font-size:27rpx}.order-total>text:last-child{font-size:36rpx;font-weight:500}.order-address{display:flex;align-items:center;gap:20rpx;margin-top:16rpx;padding:24rpx;font-size:28rpx}.address-icon{font-size:44rpx;color:#53617a}.order-address>view:last-child{flex:1;min-width:0}.order-address text{display:block;line-height:1.6;overflow-wrap:anywhere}.order-address text+text{font-size:25rpx;color:#65728c;margin-top:6rpx}.order-meta{margin:16rpx 0;padding:24rpx}.order-meta>view{display:flex;justify-content:space-between;align-items:center;gap:20rpx;margin-top:6rpx;font-size:24rpx;color:#65728c;line-height:1.7}.order-meta>view>text:first-child{flex-shrink:0}.order-meta>view>text:last-child{text-align:right}.order-meta button{font-size:24rpx;min-height:44px;overflow-wrap:anywhere;text-align:right}.order-meta button>text{color:#0674ed;margin-left:8rpx}.order-primary-actions{display:flex;flex-direction:column;gap:16rpx;margin-top:26rpx}.order-primary-actions .secondary-button{border-radius:999rpx}.order-secondary-actions{display:flex;justify-content:center;gap:24rpx;flex-wrap:wrap;margin-top:10rpx}.order-secondary-actions button{font-size:25rpx;min-height:44px;color:#7b89a0}.detail-card{padding:26rpx;margin:22rpx 0;display:flex;flex-direction:column;gap:18rpx;font-size:27rpx;line-height:1.7}.choices{display:flex;flex-wrap:wrap;gap:12rpx}.choices button{min-height:72rpx;padding:14rpx 20rpx;border:1rpx solid #e7e8ed;border-radius:16rpx;font-size:27rpx}.choices .selected{background:#edf5ff;border-color:#2085fa;color:#0674ed}.sale-row{display:flex;align-items:center;flex-wrap:wrap;gap:12rpx;font-size:27rpx}.sale-row input{width:100rpx}.choices image{width:130rpx;height:130rpx;border-radius:16rpx}.detail-card>text{overflow-wrap:anywhere}
</style>
