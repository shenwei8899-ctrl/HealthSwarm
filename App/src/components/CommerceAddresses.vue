<script setup>
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
  <view class="screen"
    ><AppNavBar
      ><view class="nav-row"
        ><button class="icon-button" @click="back">‹</button
        ><text class="nav-title">配送地址</text><text /></view></AppNavBar
    ><view class="page-heading"
      ><text class="display-title">选择收货地址</text
      ><text class="subtitle">修改地址簿不会改变已下单的收货地址。</text></view
    ><text v-if="error" class="inline-error">{{ error }}</text
    ><button class="secondary-button" :disabled="busy" @click="load">
      {{ busy ? "正在处理…" : "刷新地址" }}</button
    ><view v-for="a in addresses" :key="a.id" class="card address-card"
      ><text class="section-title">{{ a.name }} {{ a.phone }}</text
      ><text>{{ a.region }} {{ a.detail }}</text
      ><text v-if="a.isDefault" class="subtitle">当前选用地址</text
      ><button class="primary-button" :disabled="busy" @click="select(a)">
        选择这个地址</button
      ><button class="secondary-button" :disabled="busy" @click="edit(a)">
        编辑
      </button></view
    ><text v-if="!busy && !addresses.length" class="safe-note"
      >还没有收货地址</text
    ><button class="primary-button" :disabled="busy" @click="edit()">
      新增收货地址</button
    ><view v-if="form" class="card address-card"
      ><input
        class="field-input"
        v-model="form.name"
        placeholder="收件人"
        maxlength="50"
        :disabled="busy"
      /><input
        class="field-input"
        v-model="form.phone"
        placeholder="手机号"
        type="number"
        maxlength="11"
        :disabled="busy"
      /><picker mode="multiSelector" :range="regionOptions" :value="indices" :disabled="busy || !regions.length" @columnchange="columnChange" @change="chooseRegion" @cancel="resetRegion"><view class="field-input">{{ form.region || '选择省、市、区' }}</view></picker><text class="subtitle">配送范围以结算时的服务端校验为准。</text>
      <input
        class="field-input"
        v-model="form.detail"
        placeholder="街道、门牌等详细地址"
        maxlength="200"
        :disabled="busy"
      /><button class="primary-button" :disabled="busy" @click="save">
        保存并使用</button
      ><button class="secondary-button" :disabled="busy" @click="form = null">
        取消编辑
      </button></view
    ></view
  >
</template>
<style scoped>
.address-card {
  padding: 28rpx;
  margin: 24rpx 0;
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}
</style>
