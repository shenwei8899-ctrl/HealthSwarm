<script setup>
import { reactive, ref, computed, watch } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import ArchiveField from '../../components/ArchiveField.vue'
import { request } from '../../services/request.js'
import { getSession, sessionRevision } from '../../services/session.js'
import { archiveState, createFamilyArchivesClient } from '../../services/family-archives-client.js'
import { profileFields, recordGroups, objectGroups, metricKinds, profileDraft, profileChanges, measurementTimestamp } from '../../services/family-archive-fields.js'
const state = reactive(archiveState())
const client = createFamilyArchivesClient({ send: request, session: { read: getSession, revision: sessionRevision }, state })
const draft = ref({}), editing = ref(false), name = ref(''), relationship = ref(''), metric = ref(null), metricError = ref('')
const unavailable = computed(() => state.busy || state.blocked)
const editable = key => state.member?.editable_fields?.includes(key) === true
watch(() => state.member, member => { editing.value = false; metric.value = null; draft.value = profileDraft(member?.profile); name.value = member?.name || ''; relationship.value = member?.relationship || '' })
function discard() { client.discard(); draft.value = {}; metric.value = null; editing.value = false; name.value = ''; relationship.value = ''; metricError.value = '' }
onShow(() => client.refresh()); onHide(discard); onUnload(discard)
function saveProfile() {
  try {
    const changes = profileChanges(draft.value, state.member)
    if (!Object.keys(changes).length) { editing.value = false; return }
    return client.saveProfile(changes)
  } catch (error) { state.error = error.message }
}
function toggleEditing() {
  draft.value = profileDraft(state.member?.profile)
  editing.value = !editing.value
}
function addRecord(group) { draft.value[group.key].push(Object.fromEntries(group.fields.map(f => [f.key, f.type==='select'?f.options[0][0]:'']))) }
function newMetric(kind, record = null) {
  const local = new Date(record?.measured_at || Date.now()); local.setMinutes(local.getMinutes() - local.getTimezoneOffset())
  metric.value = { kind, record, values: { ...(record?.values || {}) }, time: local.toISOString().slice(0,16), condition: record?.condition || (kind==='blood_glucose'?'fasting':''), note: '', source: record?.source || 'manual' }; metricError.value = ''
}
const selectedMetric = computed(() => metricKinds.find(row => row.key === metric.value?.kind))
function uuid() { return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const r=Math.random()*16|0;return(c==='x'?r:(r&3|8)).toString(16)}) }
async function saveMetric() {
  try {
    const form = metric.value, values = Object.fromEntries(selectedMetric.value.fields.map(([key]) => [key, Number(form.values[key])]))
    if (Object.values(values).some(n => !Number.isFinite(n) || n <= 0)) throw new Error('请填写完整的实测正数，缺失值不能填零。')
    const measured_at = measurementTimestamp(form.time)
    if (form.record && !form.note.trim()) throw new Error('更正记录需要填写原因')
    const data = { values, measured_at, source: form.source, condition: form.condition, note: form.note }
    if (!form.record) Object.assign(data, { id: uuid(), kind: form.kind })
    await client.saveMeasurement(data, form.record)
  } catch (error) { metricError.value = error.message }
}
function voidRecord(row) {
  uni.showModal({ title: '作废实测记录', editable: true, placeholderText: '请填写作废原因', success: result => {
    if (result.confirm && result.content?.trim()) client.voidMeasurement(row, result.content.trim())
  } })
}
const metricLabel = row => metricKinds.find(kind => kind.key===row.kind)?.label || row.kind
function back() { uni.navigateBack({ fail: () => uni.reLaunch({url:'/pages/account/index'}) }) }
</script>
<template><view class="screen shared-page">
  <AppNavBar><view class="nav-row"><button class="icon-button" @click="back">‹</button><text class="nav-title">家庭共享档案</text></view></AppNavBar>
  <text class="helper">同家庭有效成员可共同查看和维护档案。AI、报告原图和订单仍需各自授权；编辑不代表本人已确认。</text>
  <text v-if="state.error" class="error" role="alert">{{state.error}}</text><text v-if="state.notice" class="notice">{{state.notice}}</text>
  <button class="secondary-button" :disabled="state.busy" @click="client.refresh(state.family?.id,state.member?.id)">{{state.busy?'正在读取…':'重新读取家庭档案'}}</button>
  <view class="choices"><button v-for="family in state.families" :key="family.id" :disabled="state.busy" :class="{selected:family.id===state.family?.id}" @click="client.refresh(family.id)">{{family.name}}</button></view>
  <text v-if="!state.families.length&&!state.busy" class="helper">没有可访问的家庭，请返回账号与家庭页面加入或创建。</text>
  <view v-if="state.family" class="choices"><button v-for="member in state.family.members.filter(m=>m.is_active)" :key="member.id" :disabled="state.busy" :class="{selected:member.id===state.member?.id}" @click="client.refresh(state.family.id,member.id)">{{member.name}}{{member.is_self?' · 本人':''}}{{!member.claimed?' · 未认领':''}}</button></view>
  <template v-if="state.member">
    <view class="card section"><text class="section-title">{{state.member.name}}的档案</text><text class="helper">版本 {{state.member.version}} · {{state.member.confirmed?'当前版本已确认':'当前版本待本人或合法监护人确认'}}</text>
      <ArchiveField v-model="name" :field="{label:'姓名或称呼'}" :disabled="unavailable"/><ArchiveField v-model="relationship" :field="{label:'关系'}" :disabled="unavailable"/>
      <button class="secondary-button" :disabled="unavailable||!name.trim()||!relationship.trim()" @click="client.saveIdentity(name.trim(),relationship.trim())">保存姓名与关系</button>
    </view>
    <view class="card section"><view class="section-head"><text class="section-title">健康与饮食资料</text><button :disabled="unavailable" @click="toggleEditing">{{editing?'取消编辑':'编辑资料'}}</button></view>
      <ArchiveField v-for="field in profileFields.filter(f=>state.member.allowed_fields.includes(f.key))" :key="field.key" v-model="draft[field.key]" :field="field" :disabled="!editing||unavailable||!editable(field.key)"/>
      <view v-for="group in recordGroups.filter(g=>state.member.allowed_fields.includes(g.key))" :key="group.key" class="group"><text class="section-title">{{group.label}}</text>
        <text v-if="!draft[group.key]?.length" class="helper">尚未填写</text>
        <view v-for="(row,i) in draft[group.key]" :key="i" class="record"><ArchiveField v-for="field in group.fields" :key="field.key" v-model="row[field.key]" :field="field" :disabled="!editing||unavailable||!editable(group.key)"/><button v-if="editing&&editable(group.key)" :disabled="unavailable" @click="draft[group.key].splice(i,1)">移除此项</button></view>
        <button v-if="editing&&editable(group.key)" class="secondary-button" :disabled="unavailable" @click="addRecord(group)">添加{{group.label}}</button>
      </view>
      <view v-for="group in objectGroups.filter(g=>state.member.allowed_fields.includes(g.key))" :key="group.key" class="group"><text class="section-title">{{group.label}}</text><ArchiveField v-for="field in group.fields" :key="field.key" v-model="draft[group.key][field.key]" :field="field" :disabled="!editing||unavailable||!editable(group.key)"/></view>
      <button v-if="editing" class="primary-button" :disabled="unavailable" @click="saveProfile">保存档案资料</button>
    </view>
    <view class="card section"><text class="section-title">实测记录</text><text class="helper">近366天，显示{{state.measurements.length}}/{{state.measurementTotal}}条（最多100条）。仅记录实际测量，不作医学判断。</text>
      <view class="choices"><button v-for="kind in metricKinds.filter(k=>editable(k.key))" :key="kind.key" :disabled="unavailable" @click="newMetric(kind.key)">记录{{kind.label}}</button></view>
      <view v-if="metric" class="record"><text class="section-title">{{metric.record?'更正':'添加'}}{{selectedMetric.label}}</text>
        <ArchiveField v-for="[key,label] in selectedMetric.fields" :key="key" v-model="metric.values[key]" :field="{label:label+'（'+selectedMetric.unit+'）',type:'number'}" :disabled="unavailable"/>
        <ArchiveField v-model="metric.time" :field="{label:'测量时间（本地时间 YYYY-MM-DDTHH:mm）'}" :disabled="unavailable"/>
        <ArchiveField v-if="metric.kind==='blood_glucose'" v-model="metric.condition" :field="{label:'测量条件',type:'select',options:[['fasting','空腹'],['after_meal_2h','餐后2小时'],['random','随机']]}" :disabled="unavailable"/>
        <ArchiveField v-model="metric.source" :field="{label:'测量来源'}" :disabled="unavailable"/><ArchiveField v-model="metric.note" :field="{label:metric.record?'更正原因':'备注'}" :disabled="unavailable"/>
        <text v-if="metricError" class="error">{{metricError}}</text><button class="primary-button" :disabled="unavailable" @click="saveMetric">保存实测记录</button><button :disabled="state.busy" @click="metric=null">取消</button>
      </view>
      <view v-for="row in state.measurements" :key="row.id" class="record"><text>{{metricLabel(row)}} · {{Object.values(row.values).join(' / ')}} {{row.unit}}</text><text class="helper">{{row.measured_at}} · {{row.created_by}} · 版本{{row.version}}{{row.voided_at?' · 已作废':''}}</text><text v-if="row.note">备注：{{row.note}}</text><text v-if="row.previous?.length" class="helper">已保留{{row.previous.length}}次旧版本</text><view v-if="!row.voided_at&&editable(row.kind)" class="choices"><button :disabled="unavailable" @click="newMetric(row.kind,row)">更正</button><button :disabled="unavailable" @click="voidRecord(row)">作废</button></view></view>
    </view>
    <view class="card section"><text class="section-title">修改历史</text><text class="helper">显示最近{{state.history.length}}/{{state.historyTotal}}个版本（最多20条）。</text><view v-for="row in state.history" :key="row.version" class="record"><text>版本{{row.version}} · {{row.actor}}</text><text class="helper">{{row.created_at}}</text></view></view>
  </template>
</view></template>
<style scoped>.shared-page{padding-bottom:80rpx}.helper{display:block;font-size:25rpx;color:#69776f;line-height:1.7;margin:16rpx 0}.error,.notice{display:block;padding:20rpx;margin:18rpx 0;font-size:27rpx;line-height:1.6}.error{color:#9a342d;background:#fff0ee}.notice{color:#225b3c;background:#edf6ee}.section{padding:28rpx;margin:24rpx 0}.choices{display:flex;flex-wrap:wrap;gap:12rpx;margin:20rpx 0}.choices button,.section-head button{font-size:25rpx;padding:12rpx 20rpx;margin:0;background:#f0f3f1;border-radius:14rpx}.choices .selected{background:#246b50;color:#fff}.section-head{display:flex;justify-content:space-between;align-items:center}.group{margin-top:34rpx;border-top:1px solid #e1e7e2;padding-top:24rpx}.record{display:flex;flex-direction:column;gap:8rpx;border-top:1px solid #e1e7e2;padding:22rpx 0;font-size:27rpx}</style>
