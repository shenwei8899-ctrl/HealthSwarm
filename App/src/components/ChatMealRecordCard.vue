<script setup>
import { reactive, onMounted, onUnmounted, watch } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import { chatMealRecordState, createChatMealRecordClient } from '../services/chat-meal-record.js'
import { mealDay, mealLabels } from '../services/cloud-meals.js'
const props = defineProps({ receipt: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const state = reactive(chatMealRecordState())
const client = createChatMealRecordClient({ state, id: props.receipt.id })
async function refresh() { const record = await client.refresh(); if (record) emit('changed', record) }
async function withdraw() { const record = await client.withdraw(); if (record) emit('changed', record) }
function detail() {
  if (!state.record || state.busy || state.record.status !== 'saved') return
  uni.navigateTo({ url: '/pages/records/detail?id=' + encodeURIComponent(state.record.id) + '&memberId=' + encodeURIComponent(state.record.member_id) })
}
onMounted(refresh); onShow(refresh); onHide(client.hide); onUnload(client.hide)
onUnmounted(client.hide)
watch(() => props.receipt.source_version, () => {
  if (!state.busy && props.receipt.source_version !== state.record?.source_version) void refresh()
})
</script>
<template>
 <view class="chat-meal-record" aria-live="polite">
  <template v-if="state.record">
   <view class="record-heading"><text>{{state.record.status==='withdrawn'?'已撤销这条饮食记录':'已记入饮食记录'}}</text><text>{{mealLabels[state.record.meal_type]}}</text></view>
   <text class="record-subtitle">{{state.record.member_name}} · {{mealDay(state.record.eaten_at)}}</text>
   <view v-for="item in state.record.items" :key="item.name" class="record-food"><text>{{item.name}}</text><text>{{item.quantity_text||'份量未知'}}</text></view>
   <text class="record-note">{{state.record.status==='withdrawn'?'这条记录已从有效饮食记录和后续分析中排除。':'按实际自述保存，未知份量和营养数据保持未知。'}}</text>
   <view v-if="state.record.status==='saved'" class="record-actions"><button :disabled="state.busy" @click="detail">查看记录</button><button :disabled="state.busy" @click="withdraw">{{state.busy?'正在核对…':state.pending?'重试撤销':'撤销记录'}}</button></view>
  </template>
  <text v-else class="record-note">{{state.busy?'正在核对记餐结果…':'记餐结果待核对'}}</text>
  <view v-if="state.error" class="record-error" role="alert"><text>{{state.error}}</text><button :disabled="state.busy" @click="state.pending?withdraw():refresh()">{{state.pending?'重试撤销':'重新读取'}}</button></view>
 </view>
</template>
<style scoped>
.chat-meal-record{margin-top:10px;padding:16px;border:1px solid #e7e2ef;border-radius:18px;background:rgba(255,255,255,.94);color:var(--ui-text);font-size:14px;line-height:1.7}.record-heading,.record-food,.record-actions{display:flex;justify-content:space-between;align-items:center;gap:12px}.record-heading{font-weight:600}.record-heading>text:last-child,.record-subtitle,.record-note,.record-food>text:last-child{color:var(--ui-muted);font-size:12px}.record-subtitle,.record-note{display:block}.record-subtitle{margin-bottom:10px}.record-food{padding:5px 0;align-items:flex-start;overflow-wrap:anywhere}.record-food>text:last-child{flex:none;max-width:45%}.record-note{margin-top:10px}.record-actions{border-top:1px solid #eeebf3;margin-top:12px;padding-top:4px}.record-actions button,.record-error button{min-height:44px;padding:8px 0;background:transparent;color:#6e617f;font-size:13px}.record-error{margin-top:8px;color:#a33b35;font-size:12px}.record-actions button[disabled]{opacity:.5}
</style>
