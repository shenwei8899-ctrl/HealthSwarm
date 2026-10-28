<script setup>
import { ref, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'
import { addressApi } from '../services/address-api.js'
import { addressText } from '../services/address-model.js'
import { addressBack, openAddressEditor } from '../services/address-navigation.js'
import { useCommercePage } from '../services/commerce-page.js'
const props = defineProps({ mode: { type: String, default: 'manage' }, selectedId: String })
const emit = defineEmits(['select'])
const addresses = ref([]), loaded = ref(false)
const { busy, error, run } = useCommercePage(() => { addresses.value = []; loaded.value = false })
function load() {
  return run(async active => {
    const book = await addressApi.book()
    if (active()) { addresses.value = book.items || []; loaded.value = true }
  })
}
function edit(id = '') {
  if (busy.value) return
  openAddressEditor({ id, mode: props.mode, onSaved: result => {
    if (props.mode === 'select') emit('select', result.id, true)
  } })
}
function choose(address) {
  if (busy.value) return
  if (props.mode === 'select') emit('select', address.id)
  else edit(address.id)
}
function setDefault(address) {
  if (address.isDefault) return
  return run(async active => {
    await addressApi.setDefault(address.id)
    if (!active()) return
    addresses.value = addresses.value.map(item => ({ ...item, isDefault: String(item.id) === String(address.id) }))
    uni.showToast({ title: '已设为默认地址', icon: 'none' })
  })
}
function copy(address) {
  uni.setClipboardData({ data: addressText(address), fail: () => uni.showToast({ title: '复制失败，请重试', icon: 'none' }) })
}
onMounted(load); onShow(load)
</script>
<template>
 <view class="screen address-screen address-list-screen">
  <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="addressBack">‹</button><text class="nav-title">{{mode==='select'?'选择收货地址':'收货地址'}}</text><view class="nav-spacer"/></view></AppNavBar>
  <view v-if="error" class="address-state" role="alert"><text>{{error}}</text><button class="address-retry" :disabled="busy" @click="load">重新读取</button></view>
  <view v-else-if="busy&&!loaded" class="address-state"><text>正在读取收货地址…</text></view>
  <view v-else-if="loaded&&!addresses.length" class="address-state"><AppIcon name="family" :size="64"/><text class="address-state-title">还没有收货地址</text><text>添加地址，方便下单时选择。</text></view>
  <view v-if="addresses.length" class="address-list">
   <view v-for="item in addresses" :key="item.id" class="address-row">
    <button class="address-main" :disabled="busy" :aria-label="(mode==='select'?'选用':'编辑')+item.detail" @click="choose(item)">
     <view v-if="mode==='select'" class="selection-check" :class="{active:String(item.id)===String(selectedId)}">{{String(item.id)===String(selectedId)?'✓':''}}</view>
     <view class="address-copy"><text class="region-line">{{item.region}}</text><text class="detail-line">{{item.detail}}</text><view class="person-line"><text>{{item.name}}</text><text>{{item.phone}}</text><text v-if="item.label" class="address-tag">{{item.label}}</text></view></view>
    </button>
    <view class="address-actions"><button class="default-action" :class="{isdefault:item.isDefault}" :disabled="busy||item.isDefault" @click="setDefault(item)"><text class="default-check">{{item.isDefault?'✓':''}}</text><text>{{item.isDefault?'默认地址':'设为默认'}}</text></button><view class="row-tools"><button :disabled="busy" @click="copy(item)">复制</button><button :disabled="busy" :aria-label="'修改'+item.name+'的地址'" @click="edit(item.id)">修改</button></view></view>
   </view>
  </view>
  <text v-if="addresses.length" class="address-note">修改地址簿不会改变已下单的收货地址。</text>
  <view class="address-bottom"><button class="primary-button" :disabled="busy" @click="edit()">＋ 新增收货地址</button></view>
 </view>
</template>
<style scoped>
@import '../styles/address.css';
.address-list-screen{padding-left:24rpx;padding-right:24rpx}.address-list{background:#fff;border-radius:26rpx;overflow:hidden;margin-top:24rpx}.address-row{padding:26rpx 24rpx 14rpx;border-bottom:1rpx solid #edf0f2}.address-row:last-child{border:0}.address-main{display:flex;align-items:flex-start;gap:18rpx;width:100%;text-align:left;padding:4rpx 0 10rpx;min-height:100rpx}.address-copy{flex:1;min-width:0}.region-line{display:block;color:#8a8e97;font-size:25rpx;line-height:1.5;margin-bottom:9rpx}.detail-line{display:block;font-size:33rpx;line-height:1.45;font-weight:600;color:#25262a;overflow-wrap:anywhere}.person-line{display:flex;align-items:baseline;flex-wrap:wrap;gap:8rpx 16rpx;font-size:27rpx;line-height:1.6;margin-top:14rpx;color:#555b65}.person-line>text:first-child{color:#333740}.address-tag{font-size:22rpx;line-height:1.4;border-radius:6rpx;padding:2rpx 8rpx;color:#727984;background:#f2f3f5}.address-actions{display:flex;align-items:center;justify-content:space-between;gap:8rpx;margin-top:7rpx}.default-action{display:flex;align-items:center;gap:10rpx;font-size:24rpx;color:#7b818c;min-height:44px;text-align:left}.default-check{display:flex;align-items:center;justify-content:center;width:30rpx;height:30rpx;border:2rpx solid #d3d7de;border-radius:50%;font-size:22rpx;flex-shrink:0}.address-screen .default-action.isdefault[disabled]{opacity:1}.default-action.isdefault{color:#4b515b;opacity:1}.isdefault .default-check{background:#25262a;border-color:#25262a;color:#fff}.row-tools{display:flex;gap:12rpx}.row-tools button{font-size:25rpx;min-width:44px;min-height:44px;color:#666d78}.selection-check{display:flex;align-items:center;justify-content:center;width:34rpx;height:34rpx;flex-shrink:0;border:2rpx solid #d3d7de;border-radius:50%;margin-top:45rpx;color:#fff;font-size:24rpx}.selection-check.active{background:#25262a;border-color:#25262a}
</style>
