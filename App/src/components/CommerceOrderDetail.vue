<script setup>
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
</script>
<template>
  <view class="screen"
    ><AppNavBar
      ><view class="nav-row"
        ><button class="icon-button" @click="back">‹</button
        ><text class="nav-title">订单详情</text><text /></view></AppNavBar
    ><text v-if="error" class="inline-error">{{ error }}</text
    ><text v-if="message" class="safe-note">{{ message }}</text
    ><button class="secondary-button" :disabled="busy" @click="load">
      {{ busy ? "正在处理…" : "刷新订单" }}</button
    ><view v-if="pending" class="card detail-card"
      ><text
        >上次售后申请结果尚未确认。请重试原申请，系统会核对原提交结果。</text
      ><button class="primary-button" :disabled="busy" @click="retrySale">
        重试并确认原售后申请
      </button></view
    ><template v-if="order"
      ><view class="card detail-card"
        ><text class="display-title">{{ order.label }}</text
        ><text>{{ order.id }}</text
        ><text class="section-title"
          >订单金额 ¥{{ money(order.totalCents) }}</text
        ><text v-if="order.address"
          >{{ order.address.receiver }} {{ order.address.mobile }} ·
          {{ order.address.region }} {{ order.address.detail }}</text
        ><text v-for="item in order.items" :key="item.id"
          >{{ item.name }} × {{ item.quantity }} · ¥{{
            money(item.priceCents * item.quantity)
          }}</text
        ></view
      ><text v-if="order.localTestPayment" class="safe-note">本地联调环境 · 测试付款不扣款，不代表真实微信支付已开通。</text>
      <button v-if="order.localTestPayment && allowed('pay')" class="primary-button" :disabled="busy" @click="localPay">本地测试支付（不扣款）</button>
      <button v-if="order.status === 'delivered' && order.mealSnapshot" class="primary-button" :disabled="busy" @click="cook">查看本餐做法并记餐</button>
      <view class="actions"
        ><button
          v-if="allowed('pay') && !order.localTestPayment"
          class="primary-button"
          :disabled="busy"
          @click="pay"
        >
          微信支付</button
        ><button
          v-if="order.status === 'pending'"
          class="secondary-button"
          :disabled="busy"
          @click="query"
        >
          查询支付结果</button
        ><button
          v-if="allowed('cancel')"
          class="secondary-button"
          :disabled="busy"
          @click="action('cancel')"
        >
          取消未支付订单</button
        ><button
          v-if="allowed('receive')"
          class="primary-button"
          :disabled="busy"
          @click="action('receipt')"
        >
          确认收货</button
        ><button class="secondary-button" :disabled="busy" @click="logistics">
          查看物流</button
        ><button
          v-if="allowed('afterSale')"
          class="secondary-button"
          :disabled="busy"
          @click="afterSale"
        >
          申请售后</button
        ><button
          v-if="allowed('repurchase')"
          class="secondary-button"
          :disabled="busy"
          @click="repurchase"
        >
          再买一单
        </button></view
      ><view v-if="order.batches.length" class="card detail-card"
        ><text class="section-title">配送批次</text
        ><text v-for="b in order.batches" :key="b.id"
          >第{{ b.batch_no }}批 · {{ b.delivery_date }} · {{ b.status }}</text
        ><text class="subtitle"
          >计划取消和退款规则尚未定稿，新的计划购买暂未开放。</text
        ></view
      ><view v-if="events.length" class="card detail-card"
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
.detail-card {
  padding: 28rpx;
  margin: 24rpx 0;
  display: flex;
  flex-direction: column;
  gap: 18rpx;
}
.actions,
.choices {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
}
.actions button {
  flex: 1 1 40%;
  padding: 18rpx;
}
.choices button {
  padding: 14rpx;
  font-size: 25rpx;
}
.selected {
  background: #246b50;
  color: white;
}
.sale-row {
  display: flex;
  align-items: center;
  gap: 12rpx;
}
.sale-row input {
  width: 100rpx;
}
.choices image {
  width: 130rpx;
  height: 130rpx;
  border-radius: 16rpx;
}
</style>
