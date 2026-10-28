<script setup>
import { computed, ref, onMounted } from 'vue'
import { onShow, onBackPress } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import { addressApi } from '../services/address-api.js'
import { addressPayload, addressErrors, regionColumns, regionIndices } from '../services/address-model.js'
import { addressBack } from '../services/address-navigation.js'
import { useCommercePage } from '../services/commerce-page.js'
import { storageContext } from '../services/storage.js'

const props = defineProps({ addressId: String, mode: { type: String, default: 'manage' } })
const emit = defineEmits(['saved', 'removed'])
const form = ref({ name: '', phone: '', region: '', area_id: '', detail: '', isDefault: false, label: '' })
const loaded = ref(false), capabilities = ref({}), firstAddress = ref(false), original = ref('')
const fields = ref({}), focus = ref(''), conflict = ref(false), saved = ref(null), pending = ref(null)
const directory = ref([]), indices = ref([0, 0, 0]), regionBusy = ref(false), regionError = ref('')
let owner = storageContext(), regionGeneration = 0, leaving = false
const { busy, error, run } = useCommercePage(() => {
  loaded.value = false; form.value = {}; directory.value = []; saved.value = null; pending.value = null
  original.value = ''; fields.value = {}; regionGeneration++; regionBusy.value = false
})
const locked = computed(() => busy.value || Boolean(pending.value) || Boolean(saved.value))
const columns = computed(() => regionColumns(directory.value, indices.value))
const options = computed(() => columns.value.map(items => items.map(item => item.name)))
const customLabel = computed(() => Boolean(form.value.label) && !['家', '公司', '学校'].includes(form.value.label))
const customOpen = ref(false)
const dirty = computed(() => loaded.value && original.value !== JSON.stringify(addressPayload(form.value)))
const buttonText = computed(() => saved.value ? '已保存，返回' : pending.value ? '确认上次保存结果' : props.mode === 'select' ? '保存并使用' : props.addressId ? '保存修改' : '保存地址')
async function loadRegions() {
  if (regionBusy.value || directory.value.length) return
  const ticket = ++regionGeneration, scope = storageContext(); regionBusy.value = true; regionError.value = ''
  try {
    const result = await addressApi.areas()
    if (ticket === regionGeneration && scope === storageContext()) { directory.value = result; indices.value = regionIndices(result, form.value.area_id) }
  } catch (e) { if (ticket === regionGeneration && scope === storageContext()) regionError.value = e.message || '地区读取失败，请重试' }
  finally { if (ticket === regionGeneration && scope === storageContext()) regionBusy.value = false }
}
function load() {
  return run(async active => {
    const book = await addressApi.book()
    if (!active()) return
    const entry = props.addressId ? book.items.find(item => String(item.id) === String(props.addressId)) : null
    if (props.addressId && !entry) throw new Error('地址不存在或已被删除，请返回地址列表')
    capabilities.value = book.capabilities || {}; firstAddress.value = book.items.length === 0
    form.value = entry ? { ...entry, label: entry.label || '' } : { name: '', phone: '', region: '', area_id: '', detail: '', isDefault: firstAddress.value, label: '' }
    if (form.value.id && !form.value.version) form.value.version = 1
    fields.value = {}; conflict.value = false; pending.value = null; saved.value = null; customOpen.value = false
    original.value = JSON.stringify(addressPayload(form.value)); loaded.value = true
    indices.value = regionIndices(directory.value, form.value.area_id)
    loadRegions()
  })
}
function columnChange(event) {
  const next = [...indices.value], column = event.detail.column
  next[column] = event.detail.value
  if (column === 0) { next[1] = 0; next[2] = 0 }
  if (column === 1) next[2] = 0
  indices.value = next
}
function chooseRegion(event) {
  indices.value = [...event.detail.value]
  const chosen = columns.value.map((items, column) => items[indices.value[column]])
  if (chosen.some(item => !item)) { fields.value.region = '当前地区缺少区县信息，请重新选择'; return }
  form.value.region = chosen.map(item => item.name).join(' '); form.value.area_id = String(chosen[2].id)
  fields.value.region = ''
}
function chooseLabel(label) {
  if (locked.value) return
  customOpen.value = false
  form.value.label = form.value.label === label ? '' : label
}
function chooseCustomLabel() {
  if (locked.value) return
  if (['家', '公司', '学校'].includes(form.value.label)) form.value.label = ''
  customOpen.value = true; fields.value.label = ''
}
function save() {
  if (saved.value) { leaving = true; emit('saved', saved.value); return }
  if (busy.value || !loaded.value || conflict.value) return
  const payload = pending.value ? { ...pending.value } : addressPayload(form.value)
  fields.value = addressErrors(payload)
  const first = Object.keys(fields.value)[0]
  if (first) {
    focus.value = ''; Promise.resolve().then(() => { focus.value = first })
    uni.pageScrollTo({ selector: '#address-' + first, duration: 180 }); return
  }
  if (!capabilities.value.default_address) delete payload.isDefault
  if (!capabilities.value.address_labels) delete payload.label
  return run(async active => {
    try {
      const result = await addressApi.save(payload)
      if (!active()) return
      if (!result?.id) throw Object.assign(new Error('保存结果尚未确认，请重试原操作'), { code: 'NETWORK_ERROR' })
      // Keep the receipt before navigating. A list refresh cannot turn a write into a failure.
      saved.value = result; pending.value = null; original.value = JSON.stringify(addressPayload(form.value))
      leaving = true
      uni.showToast({ title: '地址已保存', icon: 'none' }); emit('saved', result)
    } catch (e) {
      if (active()) { pending.value = e.code === 'NETWORK_ERROR' ? { ...payload } : null; conflict.value = Number(e.code) === 40906 }
      throw e
    }
  })
}
function remove() {
  if (locked.value || !props.addressId) return
  const scope = storageContext()
  uni.showModal({ title: '删除收货地址？', content: '删除后可重新添加，已下单的收货信息不受影响。', confirmText: '删除', confirmColor: '#ba4540', success: result => {
    if (!result.confirm || scope !== storageContext()) return
    run(async active => { await addressApi.remove(props.addressId); if (active()) { leaving = true; emit('removed', { id: props.addressId }) } })
  } })
}
function back() {
  if (busy.value) return
  if (!dirty.value || saved.value) { leaving = true; addressBack(); return }
  const scope = storageContext()
  uni.showModal({ title: pending.value ? '保存结果尚未确认' : '放弃本次修改？', content: pending.value ? '建议先确认上次保存结果，以免重复添加地址。' : '返回后，本次填写的内容不会保存。', confirmText: '继续填写', cancelText: '返回', success: result => {
    if (!result.confirm && scope === storageContext()) { leaving = true; addressBack() }
  } })
}
function reloadConflict() {
  uni.showModal({ title: '重新读取地址？', content: '将使用最新资料替换当前填写内容，请先记下需要保留的修改。', success: result => { if (result.confirm) load() } })
}
onBackPress(() => { if (leaving) return false; if (busy.value || dirty.value) { back(); return true } return false })
onMounted(load)
onShow(() => { if (owner !== storageContext()) { owner = storageContext(); load() } })
</script>
<template>
 <view class="screen address-screen address-form-screen">
  <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" :disabled="busy" @click="back">‹</button><text class="nav-title">{{addressId?'编辑收货地址':'新增收货地址'}}</text><view class="nav-spacer"/></view></AppNavBar>
  <view v-if="!loaded" class="address-state"><text>{{busy?'正在读取地址信息…':error||'地址信息尚未读取'}}</text><button v-if="!busy" class="address-retry" @click="load">重新读取</button></view>
  <template v-else>
   <view class="form-section">
    <view id="address-name" class="form-row"><text class="row-label">收货人</text><view class="field-content"><input v-model="form.name" aria-label="收货人" :disabled="locked" maxlength="50" :focus="focus==='name'" placeholder="请输入收货人姓名或称呼" @input="fields.name=''"/><text v-if="fields.name" class="field-error">{{fields.name}}</text></view></view>
    <view id="address-phone" class="form-row"><text class="row-label">手机号</text><view class="field-content"><input v-model="form.phone" aria-label="手机号" :disabled="locked" type="number" maxlength="11" :focus="focus==='phone'" placeholder="请输入收货人手机号" @input="fields.phone=''"/><text v-if="fields.phone" class="field-error">{{fields.phone}}</text></view></view>
   </view>
   <view class="form-section">
    <view id="address-region" class="form-row"><text class="row-label">所在地区</text><view class="field-content"><picker mode="multiSelector" :range="options" :value="indices" :disabled="locked||regionBusy||!directory.length" @columnchange="columnChange" @change="chooseRegion" @cancel="indices=regionIndices(directory,form.area_id)"><view class="region-value" :class="{placeholder:!form.region}"><text>{{form.region||(regionBusy?'正在读取地区…':'请选择省、市、区')}}</text><text class="region-arrow">›</text></view></picker><text v-if="fields.region" class="field-error">{{fields.region}}</text><view v-if="regionError" class="region-error"><text>{{regionError}}</text><button :disabled="locked||regionBusy" @click="loadRegions">重试</button></view></view></view>
    <view id="address-detail" class="form-row detail-row"><text class="row-label">详细地址</text><view class="field-content"><textarea v-model="form.detail" aria-label="详细地址" :disabled="locked" maxlength="200" auto-height :focus="focus==='detail'" :cursor-spacing="100" placeholder="街道、小区、楼栋、单元、门牌号" @input="fields.detail=''"/><text v-if="fields.detail" class="field-error">{{fields.detail}}</text></view></view>
   </view>
   <view v-if="capabilities.default_address||capabilities.address_labels" class="form-section preferences">
    <label v-if="capabilities.default_address" class="default-row"><view><text class="default-title">设为默认收货地址</text><text class="setting-hint">{{firstAddress?'首条地址将作为默认地址':'下次下单时优先使用'}}</text></view><switch :checked="form.isDefault" color="#25262a" :disabled="locked||firstAddress" aria-label="设为默认收货地址" @change="form.isDefault=$event.detail.value"/></label>
    <view v-if="capabilities.address_labels" id="address-label" class="form-row tag-row"><text class="row-label">地址标签</text><view class="field-content"><view class="tag-options"><button v-for="tag in ['家','公司','学校']" :key="tag" :class="{active:form.label===tag&&!customOpen}" :disabled="locked" @click="chooseLabel(tag)">{{tag}}</button><button :class="{active:customLabel||customOpen}" :disabled="locked" @click="chooseCustomLabel">自定义</button></view><input v-if="customOpen||customLabel" v-model="form.label" class="custom-label" aria-label="自定义地址标签" maxlength="10" :disabled="locked" placeholder="输入标签，最多 10 个字"/><text v-if="fields.label" class="field-error">{{fields.label}}</text></view></view>
   </view>
   <text v-if="!capabilities.default_address" class="address-note">保存后会设为默认收货地址，下次下单时优先使用。</text>
   <view v-if="error" class="form-error" role="alert"><text>{{error}}</text><button v-if="conflict" class="address-retry" @click="reloadConflict">重新读取最新地址</button></view>
   <text v-if="pending" class="address-note">网络中断，暂时保留原填写内容。请点击下方按钮确认上次保存结果。</text>
   <view class="address-bottom"><button v-if="addressId" class="delete-address" :disabled="locked" @click="remove">删除</button><button class="primary-button" :disabled="busy||conflict" @click="save">{{busy?'正在处理…':buttonText}}</button></view>
  </template>
 </view>
</template>
<style scoped>
@import '../styles/address.css';
.address-form-screen{padding-left:24rpx;padding-right:24rpx}.form-section{background:#fff;border-radius:26rpx;padding:0 26rpx;margin-top:24rpx}.form-row{display:flex;align-items:center;gap:22rpx;min-height:112rpx;padding:20rpx 0;border-bottom:1rpx solid #eff0f2;font-size:29rpx}.form-row:last-child{border:0}.row-label{width:138rpx;flex-shrink:0;line-height:1.6;color:#333740}.field-content{flex:1;min-width:0}.field-content input{font-size:29rpx;min-height:64rpx;width:100%;color:#25262a}.field-content textarea{font-size:29rpx;line-height:1.65;width:100%;min-height:112rpx;color:#25262a}.detail-row{align-items:flex-start;padding-top:30rpx;padding-bottom:30rpx}.detail-row .row-label{padding-top:4rpx}.region-value{display:flex;align-items:center;justify-content:space-between;gap:14rpx;min-height:66rpx;line-height:1.6}.region-value>text:first-child{overflow-wrap:anywhere}.placeholder{color:#8a8e97}.region-arrow{font-size:36rpx;color:#9a9fa8;flex-shrink:0}.field-error{display:block;color:#b8413c;font-size:24rpx;line-height:1.6;margin-top:8rpx}.region-error{font-size:24rpx;color:#b8413c;line-height:1.6}.region-error button{min-height:44px;color:#246b50;text-align:left;font-size:25rpx}.default-row{display:flex;align-items:center;justify-content:space-between;gap:16rpx;padding:30rpx 0;border-bottom:1rpx solid #eff0f2}.default-row:last-child{border:0}.default-row>view{flex:1;min-width:0}.default-title{display:block;font-size:29rpx;line-height:1.5}.setting-hint{display:block;color:#8a8e97;font-size:24rpx;margin-top:10rpx;line-height:1.55}.default-row switch{flex-shrink:0;transform:scale(.85);transform-origin:right center}.tag-row{align-items:flex-start;padding:26rpx 0 30rpx}.tag-row .row-label{padding-top:14rpx}.tag-options{display:flex;flex-wrap:wrap;gap:14rpx}.tag-options button{min-width:118rpx;min-height:44px;background:#f5f6f7;border:1rpx solid transparent;border-radius:14rpx;font-size:26rpx;padding:15rpx 20rpx;color:#616873}.tag-options button.active{background:#eef1f0;border-color:#68756f;color:#25382d}.field-content .custom-label{font-size:26rpx;border-bottom:1rpx solid #e6e8ec;margin-top:16rpx}.form-error{margin:24rpx 6rpx;color:#b8413c;font-size:26rpx;line-height:1.6}.delete-address{display:flex;align-items:center;justify-content:center;width:30%;min-height:44px;border:1rpx solid #d6d9df;border-radius:999rpx;font-size:29rpx;background:#fff;color:#626872}
</style>
