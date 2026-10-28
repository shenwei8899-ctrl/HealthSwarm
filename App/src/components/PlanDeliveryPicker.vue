<script setup>
import { computed, ref, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { openAddressPicker } from '../services/address-navigation.js'
import { resolveCheckoutAddress } from '../services/address-model.js'
import { commerce } from '../services/commerce.js'
import { useCommercePage } from '../services/commerce-page.js'
const props = defineProps({ sn: String, version: Number, resume: Boolean, disabled: Boolean })
const emit = defineEmits(['change'])
const addresses = ref([]), addressIndex = ref(-1), slots = ref([]), slotIndex = ref(-1), dates = ref([]), dateIndex = ref(-1)
const address = computed(() => addresses.value[addressIndex.value])
const slot = computed(() => slots.value[slotIndex.value])
const date = computed(() => dates.value[dateIndex.value])
let preferredAddressId = ''
const { busy, error, run } = useCommercePage(() => { addresses.value = []; preferredAddressId = ''; clear() })
function clear() { dates.value = []; dateIndex.value = -1; emit('change', null) }
function publish() {
  if (address.value && slot.value && date.value) emit('change', { address_id: address.value.id, delivery_slot_id: slot.value.id, first_delivery_date: date.value.delivery_date })
}
async function loadDates(active, previousDate = '') {
  clear()
  if (!address.value || !slot.value) return
  const result = props.resume
    ? await commerce.planResumeDates(props.sn, address.value.id, slot.value.id)
    : await commerce.planDates(props.sn, props.version, address.value.id, slot.value.id)
  if (active()) {
    dates.value = result.items || []
    dateIndex.value = dates.value.findIndex(item => item.delivery_date === previousDate)
    publish()
  }
}
async function loadSlots(active, previousSlot = null, previousDate = '') {
  clear(); slots.value = []; slotIndex.value = -1
  if (!address.value) return
  const result = await commerce.slots(address.value.id, 'plan')
  if (!active()) return
  if (result.supported === false) throw new Error(result.message || '当前地址暂不支持配送')
  slots.value = (result.items || []).filter(item => item.available)
  const previous = slots.value.findIndex(item => String(item.id) === String(previousSlot))
  slotIndex.value = previous >= 0 ? previous : slots.value.length ? 0 : -1
  if (!slots.value.length) throw new Error('当前地址没有可预约时段')
  await loadDates(active, previousDate)
}
function load() {
  return run(async active => {
    const selected = preferredAddressId || address.value?.id, previousSlot = slot.value?.id, previousDate = date.value?.delivery_date
    clear()
    const result = await commerce.addresses()
    if (!active()) return
    addresses.value = result
    const chosen = resolveCheckoutAddress(result, selected)
    addressIndex.value = chosen ? result.findIndex(item => String(item.id) === String(chosen.id)) : -1
    if (!chosen && selected) { slots.value = []; slotIndex.value = -1; throw new Error('所选地址已被删除，请重新选择收货地址') }
    await loadSlots(active, previousSlot, previousDate)

  })
}
function chooseAddress() { if (!busy.value && !props.disabled) openAddressPicker({ selectedId: address.value?.id, onSelected: id => { preferredAddressId = id } }) }
function selectSlot(event) { if (!busy.value && !props.disabled) { slotIndex.value = Number(event.detail.value); run(loadDates) } }
function selectDate(event) {
  if (busy.value || props.disabled) return
  dateIndex.value = Number(event.detail.value) - 1
  publish()
}
onMounted(load); onShow(load)
</script>
<template>
  <view class="delivery-picker">
    <view class="plan-surface">
      <text class="plan-section-title">送到哪里</text>
      <button class="picker-row address-picker" :disabled="busy||disabled" @click="chooseAddress"><view v-if="address"><text>{{address.name}} · {{address.phone}}</text><text class="plan-caption">{{address.region}} {{address.detail}}</text></view><view v-else><text>请选择收货地址</text><text class="plan-caption">选择或新增一个配送地址</text></view><text>›</text></button>
    </view>
    <view v-if="address" class="plan-surface">
      <text class="plan-section-title">配送安排</text>
      <picker v-if="slots.length" :disabled="busy || disabled" :range="slots.map(item=>item.start_time+'—'+item.end_time)" :value="slotIndex" @change="selectSlot"><view class="picker-row"><text>配送时段</text><text>{{slot?.start_time}}—{{slot?.end_time}} ›</text></view></picker>
      <picker v-if="dates.length" :disabled="busy || disabled" :range="['选择日期',...dates.map(item=>item.delivery_date)]" :value="dateIndex+1" @change="selectDate"><view class="picker-row"><text>首批送达日</text><text>{{date?.delivery_date || '选择日期'}} ›</text></view></picker>
      <text v-if="date" class="plan-caption">开始食用日 · {{date.first_meal_date}}</text>
      <text v-else class="plan-caption">{{busy?'正在查询可预约日期…':dates.length?'食材提前一天送达，次日食用。':'暂时没有可预约日期'}}</text>
    </view>
    <view v-if="error" class="plan-notice"><text>{{error}}</text><button class="plan-text-link" :disabled="busy || disabled" @click="load">重新查询</button></view>
  </view>
</template>
<style scoped>
@import '../styles/exclusive-plan.css';
.picker-row{display:flex;align-items:center;justify-content:space-between;gap:24rpx;padding:24rpx 0;font-size:28rpx;line-height:1.6;min-height:56rpx}.picker-row>view{min-width:0}.picker-row>view>text{display:block}.picker-row>text:last-child{color:#377dc9;text-align:right}.delivery-picker .plan-text-link{width:100%}.address-picker{width:100%;text-align:left}
</style>
