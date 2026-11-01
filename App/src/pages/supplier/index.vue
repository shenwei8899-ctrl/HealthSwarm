<script setup>
import { computed, ref, reactive, onMounted } from 'vue'
import { onShow, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import { backHome } from '../../utils/profile.js'
import { commerce } from '../../services/commerce.js'
import { sessionRevision } from '../../services/session.js'
import { newHealthRequestId } from '../../services/health-request-id.js'
import { regionColumns } from '../../services/address-model.js'
import { createPartnerApplication, partnerTypes } from '../../services/partner-application.js'

const draft = createPartnerApplication({ client: commerce, context: sessionRevision, newId: newHealthRequestId, reactive })
const state = draft.state
const directory = ref([]), indices = ref([0, 0, 0]), regionBusy = ref(false), regionError = ref('')
const columns = computed(() => regionColumns(directory.value, indices.value))
const ranges = computed(() => columns.value.map(items => items.map(item => item.name)))
const selectedType = computed(() => partnerTypes.find(item => item.value === state.form.type))
let regionGeneration = 0, alive = true
const owner = sessionRevision()
async function loadRegions() {
  if (regionBusy.value || !draft.checkAccount()) return
  const ticket = ++regionGeneration
  regionBusy.value = true; regionError.value = ''
  try {
    const result = await commerce.areas()
    if (alive && ticket === regionGeneration && owner === sessionRevision()) directory.value = result
  } catch (error) {
    if (alive && ticket === regionGeneration && owner === sessionRevision()) regionError.value = error.message || '地区读取失败，请重试'
  } finally { if (alive && ticket === regionGeneration) regionBusy.value = false }
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
  if (chosen.some(item => !item)) { state.form.areaId = ''; state.form.region = ''; regionError.value = '请选择完整的省、市、区'; return }
  state.form.areaId = String(chosen[2].id)
  state.form.region = chosen.map(item => item.name).join(' ')
  regionError.value = ''
}
onMounted(loadRegions)
onShow(() => { if (!draft.checkAccount()) { regionGeneration++; directory.value = []; regionBusy.value = false } })
onUnload(() => { alive = false; regionGeneration++; directory.value = []; draft.dispose() })
</script>

<template>
  <view class="screen partner-page">
    <AppNavBar centered><view class="nav-row"><button class="icon-button" aria-label="返回" :disabled="state.busy" @click="backHome">‹</button><text class="nav-title">合作申请</text><text/></view></AppNavBar>
    <view v-if="state.saved" class="partner-success" role="status">
      <text class="success-symbol">✓</text><text class="success-title">合作申请已提交</text>
      <text class="success-description">我们会根据合作匹配情况与您联系。</text>
      <button class="partner-submit" @click="backHome">返回</button>
    </view>
    <view v-else-if="state.expired" class="partner-success" role="alert"><text>{{state.error}}</text><button class="partner-submit" @click="backHome">返回</button></view>
    <template v-else>
      <view class="partner-heading"><text class="partner-title">一起服务更多家庭</text><text class="partner-caption">欢迎企业、个体工商户和个人留下合作意向。</text></view>
      <view class="partner-card">
        <view class="type-heading"><text class="field-title">合作类型 <text class="required">*</text></text><text class="optional">请选择一项</text></view>
        <view class="partner-types" role="radiogroup" aria-label="合作类型">
          <button v-for="item in partnerTypes" :key="item.value" role="radio" :aria-checked="state.form.type===item.value" :class="{selected:state.form.type===item.value}" :disabled="state.busy" @click="state.form.type=item.value">{{item.label}}</button>
        </view>
        <view class="partner-field"><text class="field-title">公司／门店名称或个人姓名 <text class="required">*</text></text><input v-model="state.form.company" maxlength="200" :disabled="state.busy" aria-label="公司／门店名称或个人姓名" placeholder="企业填写名称，个人填写姓名" placeholder-class="partner-placeholder"/></view>
        <view class="partner-field"><text class="field-title">所在地区 <text class="required">*</text></text><picker mode="multiSelector" :range="ranges" :value="indices" :disabled="state.busy||regionBusy||!directory.length" @columnchange="columnChange" @change="chooseRegion"><view class="region-value" :class="{placeholder:!state.form.region}"><text>{{state.form.region||(regionBusy?'正在读取地区…':'请选择省、市、区')}}</text><text>›</text></view></picker><view v-if="regionError" class="region-error" role="alert"><text>{{regionError}}</text><button :disabled="regionBusy||state.busy" @click="loadRegions">重新读取</button></view></view>
        <view class="partner-contact-row">
          <view class="partner-field"><text class="field-title">联系人 <text class="required">*</text></text><input v-model="state.form.name" maxlength="100" :disabled="state.busy" aria-label="联系人" placeholder="方便联系的姓名" placeholder-class="partner-placeholder"/></view>
          <view class="partner-field"><text class="field-title">联系电话 <text class="required">*</text></text><input v-model="state.form.phone" type="number" maxlength="11" :disabled="state.busy" aria-label="联系电话" placeholder="11位手机号" placeholder-class="partner-placeholder"/></view>
        </view>
        <view class="partner-field"><text class="field-title">微信号 <text class="optional">选填</text></text><input v-model="state.form.wechat" maxlength="64" :disabled="state.busy" aria-label="微信号" placeholder="方便进一步沟通" placeholder-class="partner-placeholder"/></view>
      </view>
      <view class="partner-card introduction"><text class="field-title">合作介绍 <text class="required">*</text></text><view class="introduction-input"><textarea v-model="state.form.note" maxlength="500" :disabled="state.busy" :placeholder="selectedType?.hint||'请先选择合作类型，再简单介绍您的资源与合作期待'" placeholder-class="partner-placeholder" aria-label="合作介绍"/><text class="word-count">{{Array.from(state.form.note).length}} / 500</text></view></view>
      <view class="partner-consent"><checkbox-group @change="state.form.consent=$event.detail.value.includes('contact')"><label><checkbox value="contact" :checked="state.form.consent" :disabled="state.busy" color="#9784ed"/><text>我同意工作人员使用上述信息，就本次合作申请与我联系。</text></label></checkbox-group><text class="contact-note">信息仅用于合作沟通与审核。相关资质在初步沟通后按合作类型补充。</text></view>
      <text v-if="state.error" class="partner-error" role="alert">{{state.error}}</text>
      <button class="partner-submit" :disabled="state.busy" :loading="state.busy" @click="draft.submit">{{state.busy?'正在提交…':'提交合作申请'}}</button>
    </template>
  </view>
</template>

<style scoped>
.partner-page{padding:0 32rpx calc(env(safe-area-inset-bottom) + 30px);color:var(--ui-text);background-color:var(--ui-canvas);background-image:radial-gradient(ellipse at 0% 0%,rgba(125,174,255,.44),transparent 70%),radial-gradient(ellipse at 100% 0%,rgba(206,178,245,.38),transparent 76%),var(--ui-canvas-gradient);background-size:100% 410rpx,100% 410rpx,100% 100%;background-repeat:no-repeat}
.partner-heading{padding:22px 4px 24px}.partner-title{display:block;font-size:24px;line-height:1.5;font-weight:600;letter-spacing:.2px}.partner-caption{display:block;margin-top:8px;font-size:13px;line-height:1.8;color:var(--ui-muted)}
.partner-card{margin-bottom:16px;padding:22px 20px;border:1px solid rgba(255,255,255,.95);border-radius:24px;background:linear-gradient(180deg,rgba(255,255,255,.55),rgba(255,255,255,.96));box-shadow:inset 0 1px 0 #fff,0 8px 30px rgba(116,109,151,.035)}
.field-title{display:block;font-size:13px;font-weight:500;line-height:1.7;color:#625b70}.required{margin-left:3px;color:#a78fbe;font-size:12px}.optional{font-size:12px;font-weight:400;color:#9995a6;margin-left:7px}.type-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.partner-types{display:flex;gap:10px;margin-top:12px}.partner-types button{display:flex;align-items:center;justify-content:center;flex:1;min-width:0;min-height:46px;padding:10px 6px;border:1px solid #eeebf4;border-radius:13px;font-size:14px;font-weight:500;color:#7a7188;background:#f8f7fb}.partner-types button.selected{color:#754ac2;background:#f0eaff;border-color:#c6afed;box-shadow:inset 0 1px 0 #fff}
.partner-field{min-width:0;margin-top:22px}.partner-field input,.region-value{box-sizing:border-box;width:100%;height:49px;padding:0 13px;margin-top:9px;border:1px solid #edebf4;border-radius:13px;background:#f7f7fb;color:#3e354e;font-size:15px;line-height:1.6}.partner-placeholder,.placeholder{color:#aaa6b7}.region-value{display:flex;align-items:center;justify-content:space-between;gap:10px;height:auto;min-height:49px;padding-top:10px;padding-bottom:10px}.region-value>text:first-child{overflow-wrap:anywhere}.region-value>text:last-child{color:#b0a8c2;font-size:23px;flex:none}.partner-contact-row{display:flex;gap:12px}.partner-contact-row .partner-field{flex:1}
.region-error,.partner-error{font-size:12px;line-height:1.7;color:#a53632;overflow-wrap:anywhere}.region-error{margin-top:8px}.region-error button{font-size:12px;min-height:44px;color:#8266b1;text-align:left}
.introduction-input{position:relative;margin-top:12px;padding:13px 13px 36px;background:rgba(248,248,251,.65);border:1px solid #e9e8ef;border-radius:15px}.introduction textarea{display:block;width:100%;height:116px;font-size:14px;line-height:1.8}.word-count{position:absolute;right:13px;bottom:10px;color:#9995a6;font-size:12px}
.partner-consent{padding:2px 4px 0;font-size:12px;line-height:1.8;color:var(--ui-muted)}.partner-consent label{display:flex;gap:4px;align-items:flex-start}.partner-consent checkbox{transform:scale(.72);transform-origin:left top;flex:none;width:25px;margin-top:2px}.contact-note{display:block;color:#9995a6;margin:8px 0 0 29px;font-size:11px}.partner-error{display:block;margin:12px 4px 0}
.partner-submit{display:flex;align-items:center;justify-content:center;width:100%;min-height:50px;margin-top:22px;padding:12px;border-radius:16px;background:linear-gradient(105deg,#b6a0f4,#9784ed);color:#fff;font-size:16px;font-weight:500;line-height:1.5}.partner-submit[disabled]{opacity:.5;color:#fff;background:#b8aadf}.partner-types button:active,.partner-submit:active{opacity:.75}.icon-button{min-width:44px;min-height:44px}
.partner-success{padding:36px 22px 24px;margin-top:24px;border:1px solid rgba(255,255,255,.95);border-radius:24px;background:rgba(255,255,255,.86);box-shadow:0 8px 30px rgba(116,109,151,.035);text-align:center}.success-symbol{display:flex;align-items:center;justify-content:center;width:52px;height:52px;margin:0 auto 20px;border-radius:50%;background:#f0eaff;color:#9784d7;font-size:28px}.success-title{display:block;font-size:22px;font-weight:600}.success-description{display:block;margin:10px 0 26px;color:var(--ui-muted);font-size:13px;line-height:1.8}
@media(max-width:350px){.partner-card{padding:20px 16px}.partner-title{font-size:22px}.partner-contact-row{gap:9px}.partner-field input{padding-left:10px;padding-right:10px;font-size:14px}.partner-types{gap:8px}}
</style>
