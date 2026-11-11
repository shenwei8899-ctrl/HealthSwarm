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
 <view class="screen order-screen" :class="{'has-payment-dock':order&&allowed('pay')}"><view class="order-page-wash" aria-hidden="true"/><AppNavBar title="订单详情"><template #left><button class="icon-button" aria-label="返回" @click="back">‹</button></template><template #right><button class="refresh-link" :disabled="busy" @click="load">{{busy?'读取中':'刷新'}}</button></template></AppNavBar>
  <text v-if="error" class="inline-error" role="alert">{{error}}</text><text v-if="message" class="safe-note">{{message}}</text>
  <view v-if="pending" class="card detail-card"><text>上次售后申请结果待确认</text><button class="primary-button" :disabled="busy" @click="retrySale">确认原售后申请</button></view>
  <template v-if="order">
   <view class="order-status"><text class="status-title">{{order.label}}</text><text class="status-description">{{statusDescription}}</text></view>
   <view v-if="deliveryStep>=0" class="delivery-progress"><view v-for="(label,index) in ['已下单','配送中',order.status==='delivered'?'已收货':'待收货']" :key="index" class="progress-step" :class="{complete:index<=deliveryStep}"><view class="progress-point">{{index<=deliveryStep?'✓':''}}</view><text>{{label}}</text></view></view>
   <view class="card order-goods"><view class="card-heading"><text>订单商品</text><text>{{order.items.length}} 项</text></view><view v-for="item in order.items" :key="item.id" class="order-item"><FoodImageSlot :src="item.image" :label="item.name" fallback-icon class="order-image"/><view class="order-item-copy"><text>{{item.name}}</text><text>{{item.sku_snapshot?.sku_name||''}}</text></view><view class="order-item-amount"><text>¥{{money(item.priceCents*item.quantity)}}</text><text>×{{item.quantity}}</text></view></view><view class="order-total"><text>订单金额</text><text>¥{{money(order.totalCents)}}</text></view></view>
   <view v-if="order.address" class="card order-address"><view class="address-icon" aria-hidden="true">⌖</view><view><text>{{order.address.receiver}} · {{order.address.mobile}}</text><text>{{order.address.region}} {{order.address.detail}}</text></view></view>
   <view class="card order-meta"><text class="card-heading">订单信息</text><view><text>订单编号</text><button @click="uni.setClipboardData({data:order.id})">{{order.id}} <text>复制</text></button></view><view v-if="order.createdAt"><text>下单时间</text><text>{{dateText(order.createdAt)}}</text></view><view><text>支付状态</text><text>{{paymentLabel}}</text></view></view>
   <text v-if="order.localTestPayment" class="safe-note">本地测试订单 · 测试付款不扣款</text>
   <view v-if="allowed('receive')||(order.status==='delivered'&&order.mealSnapshot)||allowed('afterSale')" class="order-primary-actions"><button v-if="allowed('receive')" class="primary-button" :disabled="busy" @click="action('receipt')">确认收货</button><button v-if="order.status==='delivered'&&order.mealSnapshot" class="primary-button" :disabled="busy" @click="cook">开始做饭，记一餐</button><button v-if="allowed('afterSale')" class="secondary-button" :disabled="busy" @click="afterSale">申请售后</button></view>
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
      >
   <view v-if="allowed('pay')" class="order-payment-dock" role="group" aria-label="订单支付"><button v-if="order.localTestPayment" class="primary-button" :disabled="busy" @click="localPay">本地测试支付（不扣款）</button><button v-else class="primary-button" :disabled="busy" @click="pay">微信支付 ¥{{money(order.totalCents)}}</button></view>
   </template
    ></view
  >
</template>
<style scoped>
.order-screen{position:relative;z-index:0;background:var(--ui-canvas);color:var(--ui-text);padding-left:24rpx;padding-right:24rpx}
.refresh-link,.order-meta button,.order-secondary-actions button,.order-screen .icon-button{margin:0;border:0;background:transparent}
.refresh-link::after,.order-meta button::after,.order-secondary-actions button::after,.order-screen .icon-button::after{border:0}
.order-page-wash,.order-screen::after{position:fixed;z-index:-1;left:0;right:0;height:360px;pointer-events:none;background-repeat:no-repeat;background-size:100% 100%}
.order-page-wash{top:0;background-image:radial-gradient(ellipse at 0% 0%,rgba(125,174,255,.48),rgba(125,174,255,0) 72%),radial-gradient(ellipse at 100% 0%,rgba(206,178,245,.40),rgba(206,178,245,0) 75%)}
.order-screen::after{content:'';bottom:0;height:240px;background-image:radial-gradient(ellipse at 0% 100%,rgba(125,174,255,.10),rgba(125,174,255,0) 72%),radial-gradient(ellipse at 100% 100%,rgba(206,178,245,.14),rgba(206,178,245,0) 75%)}
.refresh-link{display:flex;align-items:center;justify-content:center;min-width:84rpx;min-height:44px;padding:0 12rpx;border-radius:999rpx;color:var(--ui-muted);font-size:25rpx;font-weight:500}
.order-status{padding:28rpx 14rpx 30rpx}.status-title{display:block;font-size:48rpx;font-weight:600;line-height:1.4}.status-description{display:block;font-size:27rpx;color:var(--ui-muted);margin-top:10rpx;line-height:1.7}
.order-screen .card{border:1px solid rgba(255,255,255,.6);border-radius:36rpx;background:rgba(255,255,255,.82);box-shadow:none}
.delivery-progress{display:flex;justify-content:space-between;padding:24rpx 12rpx;margin:0 0 24rpx;border:1px solid var(--ui-bubble-line);border-radius:36rpx;background:var(--ui-bubble);box-shadow:var(--ui-bubble-shadow)}
.progress-step{display:flex;flex:1;position:relative;flex-direction:column;align-items:center;gap:12rpx;font-size:24rpx;color:var(--ui-muted)}.progress-step:before{content:'';position:absolute;top:24rpx;left:50%;width:100%;height:3rpx;background:var(--ui-line)}.progress-step:last-child:before{display:none}.progress-point{width:48rpx;height:48rpx;border:1px solid var(--ui-bubble-line);border-radius:50%;background:#e7e7ef;box-shadow:0 0 0 6rpx #f6f7fa;position:relative;z-index:1;color:#fff;display:flex;align-items:center;justify-content:center;font-size:26rpx}.complete .progress-point{background:var(--ui-accent)}.complete:not(:last-child):before{background:#a7a5b5}.complete>text{color:var(--ui-text);font-weight:500}
.order-goods{padding:28rpx 28rpx 0}.card-heading{display:flex;justify-content:space-between;align-items:center;color:var(--ui-text);font-size:28rpx;font-weight:500;margin-bottom:10rpx}.card-heading>text:last-child{font-size:24rpx;font-weight:400;color:var(--ui-muted)}
.order-item{display:flex;align-items:center;gap:22rpx;padding:24rpx 0}.order-item+.order-item{border-top:1rpx solid rgba(116,113,127,.06)}.order-image{width:100rpx;height:100rpx;border-radius:20rpx;background:rgba(235,238,244,.48)}.order-image :deep(.fallback-plate){width:26px;height:26px;border:1px solid #c4c8d3;box-shadow:inset 0 0 0 5px #f5f6f9;background:#eceef4}.order-item-copy{flex:1;min-width:0}.order-item-copy>text:first-child{display:block;font-size:29rpx;font-weight:500;line-height:1.5;overflow-wrap:anywhere}.order-item-copy>text+text{display:block;font-size:24rpx;color:var(--ui-muted);margin-top:8rpx;line-height:1.6}.order-item-amount{flex-shrink:0;text-align:right;font-size:27rpx;font-weight:500;font-variant-numeric:tabular-nums}.order-item-amount text{display:block}.order-item-amount text+text{margin-top:8rpx;font-size:24rpx;font-weight:400;color:var(--ui-muted)}
.order-total{display:flex;justify-content:space-between;align-items:baseline;gap:16rpx;border-top:1rpx solid rgba(116,113,127,.10);margin-top:8rpx;padding:24rpx 0;font-size:27rpx}.order-total>text:last-child{font-size:36rpx;font-weight:600;font-variant-numeric:tabular-nums}
.order-screen .order-address{border:0;border-radius:28rpx;background:rgba(255,255,255,.42)}.order-address{display:flex;align-items:center;gap:18rpx;margin-top:24rpx;padding:22rpx 28rpx;font-size:27rpx}.address-icon{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:36rpx;height:48rpx;font-size:34rpx;color:var(--ui-muted)}.order-address>view:last-child{flex:1;min-width:0}.order-address text{display:block;line-height:1.65;font-weight:400;overflow-wrap:anywhere}.order-address text+text{font-size:24rpx;font-weight:400;color:var(--ui-muted);margin-top:6rpx}
.order-screen .order-meta{border:0;border-radius:0;background:transparent}.order-meta{margin:30rpx 0 6rpx;padding:14rpx 28rpx}.order-meta>.card-heading{margin-bottom:14rpx}.order-meta>view{display:flex;justify-content:space-between;align-items:center;gap:18rpx;min-height:64rpx;font-size:24rpx;color:var(--ui-muted);line-height:1.7}.order-meta>view>text:first-child{flex-shrink:0}.order-meta>view>text:last-child{min-width:0;text-align:right;overflow-wrap:anywhere;color:var(--ui-text)}.order-meta button{flex:1;min-width:0;font-size:23rpx;min-height:44px;overflow-wrap:anywhere;text-align:right;color:var(--ui-text)}.order-meta button>text{display:inline-block;margin-left:10rpx;padding:3rpx 12rpx;border:0;border-radius:8rpx;background:rgba(116,113,127,.06);color:var(--ui-muted);font-size:22rpx}
.order-primary-actions{display:flex;flex-direction:column;gap:14rpx;margin-top:26rpx}.order-primary-actions:empty{display:none}.order-primary-actions .primary-button{min-height:92rpx;font-size:30rpx;font-weight:600;border:0;box-shadow:none}.order-primary-actions .secondary-button{border-radius:999rpx;border-color:var(--ui-bubble-line);background:var(--ui-bubble);font-weight:500;box-shadow:var(--ui-bubble-shadow)}
.order-secondary-actions{display:flex;justify-content:center;gap:8rpx 20rpx;flex-wrap:wrap;margin-top:14rpx}.order-secondary-actions button{font-size:24rpx;min-height:44px;padding:6rpx 4rpx;color:var(--ui-muted)}
.detail-card{padding:26rpx;margin:22rpx 0;display:flex;flex-direction:column;gap:18rpx;font-size:27rpx;line-height:1.7}.choices{display:flex;flex-wrap:wrap;gap:12rpx}.choices button{min-height:44px;padding:14rpx 20rpx;border:1rpx solid var(--ui-line);border-radius:24rpx;background:rgba(255,255,255,.5);font-size:27rpx}.choices .selected{background:var(--ui-user);border-color:#c9bfdc;color:var(--ui-user-text)}.sale-row{display:flex;align-items:center;flex-wrap:wrap;gap:12rpx;font-size:27rpx}.sale-row input{width:100rpx}.choices image{width:130rpx;height:130rpx;border-radius:24rpx}.detail-card>text{overflow-wrap:anywhere}.detail-card .field-input{width:100%;max-width:100%;border-radius:24rpx;background:rgba(255,255,255,.6)}.sale-row .field-input{width:100rpx}.order-screen>.safe-note{margin:16rpx 4rpx;text-align:left}
@media(max-width:350px){.order-goods,.order-meta,.order-address{padding-left:20rpx;padding-right:20rpx}.order-item{gap:14rpx}.order-image{width:92rpx;height:104rpx}.order-item-copy>text:first-child{font-size:27rpx}.order-meta>view{gap:12rpx}}
@media(max-height:480px){.order-page-wash,.order-screen::after{height:260px}}
/* #ifdef H5 */
.order-page-wash,.order-screen::after{max-width:480px;margin-left:auto;margin-right:auto}
/* #endif */
.order-screen.has-payment-dock{padding-bottom:calc(env(safe-area-inset-bottom) + 160rpx)}
.order-payment-dock{position:fixed;z-index:20;left:24rpx;right:24rpx;bottom:calc(env(safe-area-inset-bottom) + 24rpx);background:transparent}
.order-payment-dock .primary-button{width:100%;min-height:48px;height:100rpx;border:0;border-radius:999rpx;background:#75658c;color:#fff;font-size:30rpx;font-weight:600;box-shadow:0 6rpx 20rpx rgba(83,65,108,.12)}
.order-payment-dock .primary-button:active{background:#635477}.order-payment-dock .primary-button::after{border:0}
/* #ifdef H5 */
.order-payment-dock{max-width:calc(480px - 48rpx);margin-left:auto;margin-right:auto}
/* #endif */</style>
