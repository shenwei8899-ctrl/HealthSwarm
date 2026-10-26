<script setup>
import AppIcon from './AppIcon.vue'
const props=defineProps({editId:String,newAddress:Boolean});
let opened=false;
const back = () => uni.navigateBack();
import { ref, computed, onMounted } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppNavBar from "./AppNavBar.vue";
import { commerce } from "../services/commerce.js";
import { useCommercePage } from "../services/commerce-page.js";
const addresses = ref([]),
  form = ref(null), regions = ref([]), indices = ref([0, 0, 0]);
const provinces = computed(() => regions.value.filter(a => Number(a.level) === 1));
const cities = computed(() => regions.value.filter(a => String(a.pid) === String(provinces.value[indices.value[0]]?.id)));
const districts = computed(() => regions.value.filter(a => String(a.pid) === String(cities.value[indices.value[1]]?.id)));
const regionOptions = computed(() => [provinces.value.map(a => a.name), cities.value.map(a => a.name), districts.value.map(a => a.name)]);
function resetRegion() {
  const district = regions.value.find(a => String(a.id) === String(form.value?.area_id));
  const city = regions.value.find(a => String(a.id) === String(district?.pid));
  const provinceIndex = Math.max(0, provinces.value.findIndex(a => String(a.id) === String(city?.pid)));
  indices.value = [provinceIndex, 0, 0];
  indices.value = [provinceIndex, Math.max(0, cities.value.findIndex(a => a.id === city?.id)), 0];
  indices.value = [indices.value[0], indices.value[1], Math.max(0, districts.value.findIndex(a => a.id === district?.id))];
}
function columnChange(e) {
  const next = [...indices.value]; next[e.detail.column] = e.detail.value;
  if (e.detail.column === 0) { next[1] = 0; next[2] = 0; }
  if (e.detail.column === 1) next[2] = 0;
  indices.value = next;
}
function chooseRegion(e) {
  indices.value = [...e.detail.value];
  const province = provinces.value[indices.value[0]], city = cities.value[indices.value[1]], district = districts.value[indices.value[2]];
  if (!province || !city || !district) { error.value = '当前地区缺少完整区县信息，请选择其他地区'; return; }
  form.value.region = [province.name, city.name, district.name].join(' ');
  form.value.area_id = String(district.id);
}
const { busy, error, run } = useCommercePage(() => {
  addresses.value = [];
  form.value = null;
});
function load() {
  return run(async (active) => {
    const [result, directory] = await Promise.all([commerce.addresses(), commerce.areas()]);
    if (active()) { addresses.value = result; regions.value = directory; if(!opened&&(props.editId||props.newAddress)){const target=props.editId?result.find(a=>String(a.id)===props.editId):null;if(props.editId&&!target)throw new Error('地址不存在，请返回重新选择');edit(target);opened=true} }
  });
}
onMounted(load);
onShow(load);
function edit(address) {
  form.value = address
    ? { ...address }
    : { name: "", phone: "", region: "", detail: "" };
  resetRegion();
}
function save() {
  return run(async (active) => {
    const payload = { ...form.value };
    if (!payload.area_id || !payload.region) throw new Error("请先选择完整省、市、区");
    await commerce.saveAddress(payload);
    const result = await commerce.addresses();
    if (active()) {
      addresses.value = result;
      form.value = null;
    }
  });
}
function select(address) {
  return run(async (active) => {
    await commerce.selectAddress(address.id);
    if (active()) uni.navigateBack();
  });
}


</script>
<template>

 <view class="screen address-screen">
  <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="back">‹</button><text class="nav-title">配送地址</text><button class="refresh-link" :disabled="busy" @click="load">{{busy?'读取中':'刷新'}}</button></view></AppNavBar>
  <view class="address-heading"><text>送到哪里？</text></view>
  <text v-if="error&&!form" class="inline-error" role="alert">{{error}}</text>
  <view v-if="!busy&&!addresses.length" class="address-empty"><AppIcon name="family" :size="54"/><text>还没有收货地址</text></view>
  <view v-for="a in addresses" :key="a.id" class="address-card" :class="{chosen:a.isDefault}">
   <button class="address-main" :disabled="busy" :aria-pressed="a.isDefault" @click="select(a)"><view class="address-check" :class="{active:a.isDefault}">{{a.isDefault?'✓':''}}</view><view class="address-copy"><view class="person-line"><text>{{a.name}}</text><text>{{a.phone}}</text></view><text class="address-detail">{{a.region}} {{a.detail}}</text><text v-if="a.isDefault" class="selected-label">当前使用</text></view></button><button class="address-edit" :disabled="busy" :aria-label="'编辑'+a.name+'的地址'" @click="edit(a)">编辑</button>
  </view>
  <button class="primary-button add-address" :disabled="busy" @click="edit()">＋ 新增收货地址</button>
  <view v-if="form" class="address-mask" @click.self="!busy&&(form=null)"><view class="address-editor" role="dialog" aria-modal="true" :aria-label="form.id?'编辑地址':'新增地址'">
   <view class="editor-heading"><text>{{form.id?'编辑地址':'新增地址'}}</text><button :disabled="busy" aria-label="关闭地址编辑" @click="form=null">×</button></view>
   <scroll-view class="address-editor-body" scroll-y>
    <view class="address-fields"><label><text>收件人</text><input v-model="form.name" :disabled="busy" maxlength="50" placeholder="姓名"/></label><label><text>手机号码</text><input v-model="form.phone" :disabled="busy" type="number" maxlength="11" placeholder="用于配送联系"/></label><view class="region-field"><text>所在地区</text><picker mode="multiSelector" :range="regionOptions" :value="indices" :disabled="busy||!regions.length" @columnchange="columnChange" @change="chooseRegion" @cancel="resetRegion"><view class="region-display" :class="{placeholder:!form.region}">{{form.region||'选择省、市、区'}} <text>›</text></view></picker></view><label class="detail-field"><text>详细地址</text><textarea v-model="form.detail" :disabled="busy" maxlength="200" auto-height placeholder="街道、小区、楼栋及门牌号"/></label></view>
    <text v-if="error" class="inline-error" role="alert">{{error}}</text>
   </scroll-view>
   <view class="address-editor-footer"><button class="primary-button" :disabled="busy" @click="save">{{busy?'正在保存…':'保存地址'}}</button></view>
  </view></view>
 </view>
</template>
<style scoped>

.address-screen{background:#fafbfc}.refresh-link{min-width:44px;min-height:44px;color:#0674ed;font-size:26rpx}.address-heading{padding:32rpx 4rpx 36rpx;font-size:50rpx;line-height:1.3;font-weight:500}.address-card{display:flex;align-items:center;border:1rpx solid #e7ebf2;border-radius:26rpx;background:#fff;margin-bottom:18rpx;padding:8rpx 10rpx 8rpx 4rpx}.address-card.chosen{border-color:#bad7ff}.address-main{flex:1;min-width:0;display:flex;align-items:flex-start;gap:18rpx;padding:24rpx 18rpx;text-align:left}.address-check{width:36rpx;height:36rpx;margin-top:4rpx;border:2rpx solid #bbc5d6;border-radius:50%;flex-shrink:0;font-size:25rpx;display:flex;align-items:center;justify-content:center;color:#fff}.address-check.active{background:#0879f9;border-color:#0879f9}.address-copy{flex:1;min-width:0}.person-line{display:flex;gap:16rpx;align-items:baseline;flex-wrap:wrap;font-size:29rpx;color:#252b35}.person-line>text:first-child{font-weight:500}.person-line>text+text{font-size:26rpx;color:#65728c}.address-detail{display:block;font-size:27rpx;line-height:1.7;margin-top:12rpx;color:#65728c;overflow-wrap:anywhere}.selected-label{display:inline-block;font-size:24rpx;color:#0674ed;margin-top:10rpx}.address-edit{flex-shrink:0;min-width:44px;min-height:44px;color:#0674ed;font-size:26rpx}.add-address{width:100%;margin-top:30rpx}.address-empty{padding:60rpx 24rpx;display:flex;align-items:center;flex-direction:column;gap:24rpx;color:#65728c;font-size:28rpx}.address-mask{position:fixed;inset:0;z-index:100;background:rgba(24,29,36,.28);display:flex;align-items:flex-end}.address-editor{width:100%;max-height:90vh;background:#fff;border-radius:36rpx 36rpx 0 0;display:flex;flex-direction:column;overflow:hidden}.editor-heading{display:flex;align-items:center;justify-content:space-between;padding:18rpx 32rpx 8rpx;font-size:35rpx;font-weight:500;flex-shrink:0}.editor-heading button{width:44px;height:44px;font-size:36rpx;color:#65728c}.address-editor-body{height:auto;max-height:58vh;min-height:0}.address-fields{margin:8rpx 32rpx 16rpx;border:1rpx solid #e7ebf2;border-radius:24rpx;padding:0 24rpx}.address-fields label,.region-field{display:flex;align-items:center;gap:24rpx;min-height:60px;border-bottom:1rpx solid #edf0f5;font-size:28rpx}.address-fields label>text,.region-field>text{width:132rpx;flex-shrink:0;color:#65728c}.address-fields input{flex:1;min-width:0;height:48px;font-size:29rpx}.region-field picker{flex:1;min-width:0}.region-display{display:flex;justify-content:space-between;gap:8rpx;align-items:center;min-height:52px;line-height:1.6;overflow-wrap:anywhere}.placeholder{color:#737e91}.detail-field{border:0!important;align-items:flex-start!important;padding:26rpx 0}.detail-field textarea{flex:1;min-width:0;min-height:100rpx;font-size:29rpx;line-height:1.6}.address-editor-body>.inline-error{margin:0 32rpx}.address-editor-footer{padding:20rpx 32rpx calc(env(safe-area-inset-bottom) + 24rpx);flex-shrink:0;border-top:1rpx solid #edf0f5}.address-editor-footer button{width:100%}button[disabled]{opacity:.45}
@media(max-width:350px){.person-line{font-size:15px}.person-line>text+text,.address-detail,.address-edit{font-size:13px}.address-main{gap:12rpx;padding:20rpx 12rpx}.address-fields label,.region-field{font-size:13px}.address-fields input,.detail-field textarea{font-size:14px}}
/* #ifdef H5 */
.address-editor{max-width:480px;margin:0 auto}
/* #endif */
</style>

<style scoped>
@media(max-width:350px){.selected-label,.refresh-link{font-size:12px}}
</style>
