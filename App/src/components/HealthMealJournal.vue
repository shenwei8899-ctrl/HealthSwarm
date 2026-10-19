<script setup>
import { reactive, ref, computed } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import { createDietJournalClient, journalState, mealDate } from '../services/diet-journal-client.js'
import { newHealthRequestId } from '../services/health-task-flow.js'
import { scopedStorage } from '../services/storage.js'
import HealthMealEditor from './HealthMealEditor.vue'

const state = reactive(journalState())
const client = createDietJournalClient({ state })
const mode = ref('list'), query = ref(''), reason = ref(''), accept = ref(false), meal = ref(null)
const people = ref([]), mealType = ref('lunch')
const labels = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' }
const mealOptions = Object.keys(labels)
const selectedPeople = computed(() => people.value.filter(row => row.eaten))
const unsavedPeople = computed(() => selectedPeople.value.filter(row => !state.saved.some(saved => saved.member_id === row.memberId)))
const canSave = computed(() => unsavedPeople.value.length && unsavedPeople.value.every(row => row.items.length && row.items.every(item => Number(item.grams) > 0)))
const totals = computed(() => state.detail?.snapshot?.nutrition?.totals || {})
function discard() { client.discard(); meal.value = null; people.value = []; mode.value = 'list'; reason.value = ''; accept.value = false }
onShow(() => { discard(); void client.open() })
onHide(discard)
onUnload(discard)
function newMeal() {
  mode.value = 'new'; accept.value = false; state.saved = []; state.results = []; state.notice = ''; state.error = ''
  people.value = state.members.map(row => ({ memberId: row.id, name: row.display_name || row.name || row.relationship_label, eaten: row.id === state.memberId, items: [] }))
  void client.searchRecipes('')
}
function addRecipe(person, recipe) {
  if (state.pending || state.busy || person.items.some(row => row.recipe_version_id === recipe.id)) return
  person.items.push({ item_id: newHealthRequestId(), name: recipe.name, recipe_version_id: recipe.id,
    grams: '', share_ratio: 1, portion_source: 'manual' })
}
async function show(record) {
  mode.value = 'detail'; accept.value = false; meal.value = null; reason.value = ''
  await client.detail(record)
  if (state.detail) meal.value = JSON.parse(JSON.stringify(state.detail.snapshot.meal))
}
async function correct() {
  if (!reason.value.trim() || !meal.value) return
  await client.correct(meal.value, reason.value.trim(), accept.value)
  if (!state.pending && !state.error && state.detail) meal.value = JSON.parse(JSON.stringify(state.detail.snapshot.meal))
}
async function save(chat = false) {
  if (!canSave.value && !state.pending) return
  const now = new Date().toISOString()
  await client.save(selectedPeople.value.map(row => ({ memberId: row.memberId, meal: {
    meal_type: mealType.value, eaten_at: now, items: row.items.map(item => ({ ...item, grams: Number(item.grams) })) } })), accept.value)
  if (chat && !state.pending && state.saved.length === 1) chatWithSaved()
}
function chatWithSaved(record = state.saved[0]) {
  const saved = record
  if (!saved || state.pending) return
  const memberId = saved.member_id || state.memberId
  scopedStorage.setStorageSync(`indicator-choice:${memberId}:diet_analysis`, { record_id: saved.id, source_version: saved.source_version })
  uni.navigateTo({ url: `/pages/chat/agent?memberId=${encodeURIComponent(memberId)}&taskType=diet_analysis&indicatorChoice=1`,
    fail() { state.error = '记录已保存，进入咨询失败；请点“继续聊聊”重试，不需要再次记餐。' } })
}
</script>

<template>
  <view class="journal">
    <text class="display-title">实际饮食记录</text>
    <text class="safe-note">按成员授权读取。没有记录表示未知，不记为零摄入。</text>
    <text v-if="state.busy" class="safe-note">正在核对服务端记录…</text>
    <text v-if="state.error" class="inline-error">{{state.error}}</text>
    <text v-if="state.notice" class="safe-note">{{state.notice}}</text>
    <button v-if="!state.members.length" class="secondary-button" :disabled="state.busy" @click="client.open()">重新读取授权成员</button>
    <view v-if="mode==='list'">
      <view class="choices"><button v-for="member in state.members" :key="member.id" :class="{active:state.memberId===member.id}" :disabled="state.busy" @click="client.select(member.id)">{{member.display_name||member.name||member.relationship_label}}</button></view>
      <button v-if="state.memberId" class="primary-button" :disabled="state.busy" @click="newMeal">按菜谱记餐 / 家庭桌菜</button>
      <text v-if="!state.records.length&&!state.busy" class="safe-note">本页没有可展示的已确认记录。</text>
      <button v-for="record in state.records" :key="record.id" class="card record" :disabled="state.busy" @click="show(record)">
        <text>{{labels[record.snapshot.meal.meal_type]}} · {{mealDate(record.snapshot.meal.eaten_at)}} · v{{record.source_version}}</text>
        <text>{{record.snapshot.meal.items.filter(i=>!i.excluded).map(i=>i.name).join('、')}}</text>
        <text>{{record.snapshot.nutrition.totals.energy_kcal ?? '未知'}} kcal ›</text>
      </button>
      <view class="choices"><button :disabled="state.busy||state.offset===0" @click="client.page(Math.max(0,state.offset-20))">上一页</button><button :disabled="state.busy||state.nextOffset===null" @click="client.page(state.nextOffset)">下一页</button><button :disabled="state.busy" @click="client.page()">刷新</button></view>
    </view>
    <view v-if="mode==='detail'&&state.detail&&meal" class="card editor">
      <text class="section-title">更正实际摄入 · v{{state.detail.source_version}}</text>
      <text>当前计算：{{totals.energy_kcal ?? '未知'}} kcal · 蛋白质 {{totals.protein_g ?? '未知'}} g</text>
      <text class="safe-note">未知值保留为空。修改实际克数后，服务端重新计算当前记录。</text>
      <HealthMealEditor :meal="meal" :disabled="state.busy||!!state.pending" :recipes="state.recipes" @search="client.searchRecipes"/>
      <textarea v-model="reason" :disabled="state.busy||!!state.pending" placeholder="填写更正原因" class="text-area"/>
      <label class="consent"><switch :checked="accept" :disabled="state.busy||!!state.pending" @change="accept=$event.detail.value"/>接受营养资料不完整，缺失项保持未知</label>
      <button class="primary-button" :disabled="state.busy||state.conflict||!reason.trim()" @click="correct">{{state.pending?'重试原更正':'保存更正并重新计算'}}</button>
      <button v-if="state.conflict" class="secondary-button" :disabled="state.busy" @click="show(state.detail)">读取当前版本后重新填写</button>
      <button class="secondary-button" :disabled="state.busy||!!state.pending||state.conflict" @click="chatWithSaved(state.detail)">就这条已保存记录聊聊</button>
    </view>
    <view v-if="mode==='new'" class="editor">
      <text class="section-title">每人实际吃了什么</text>
      <text class="safe-note">取消勾选没吃的人。每人选择实际吃的菜与个人可食克数，不平均分配整桌。</text>
      <picker :range="mealOptions.map(k=>labels[k])" :disabled="state.busy||!!state.pending" @change="mealType=mealOptions[$event.detail.value]"><view class="field-input">{{labels[mealType]}} ›</view></picker>
      <input v-model="query" class="field-input" placeholder="搜索已发布菜谱" :disabled="state.busy||!!state.pending"/><button class="secondary-button" :disabled="state.busy||!!state.pending" @click="client.searchRecipes(query)">查找菜谱</button>
      <text v-if="!state.recipes.length&&!state.busy" class="safe-note">暂无匹配的已发布菜谱，请先由负责人准备资料。</text>
      <view v-for="person in people" :key="person.memberId" class="card editor">
        <label><switch :checked="person.eaten" :disabled="state.busy||!!state.pending||state.saved.some(saved=>saved.member_id===person.memberId)" @change="person.eaten=$event.detail.value"/>{{person.name}} · 本次吃了</label>
        <text v-if="state.saved.some(saved=>saved.member_id===person.memberId)" class="safe-note">已保存，本次不再提交</text>
        <template v-if="person.eaten&&!state.saved.some(saved=>saved.member_id===person.memberId)">
          <view class="choices"><button v-for="recipe in state.recipes" :key="recipe.id" :disabled="state.busy||!!state.pending" @click="addRecipe(person,recipe)">＋{{recipe.name}} · {{recipe.dataset_version}}</button></view>
          <view v-for="(item,index) in person.items" :key="item.item_id" class="item"><text>{{item.name}}</text><input v-model="item.grams" type="digit" :disabled="state.busy||!!state.pending" placeholder="实际吃的可食克数"/><text>克</text><button :disabled="state.busy||!!state.pending" @click="person.items.splice(index,1)">移除</button></view>
        </template>
      </view>
      <label class="consent"><switch :checked="accept" :disabled="state.busy||!!state.pending" @change="accept=$event.detail.value"/>接受营养资料不完整，缺失项保持未知</label>
      <view v-for="result in state.results" :key="result.member_id" class="safe-note">{{people.find(p=>p.memberId===result.member_id)?.name}}：{{result.status==='saved'?'已保存':result.message}}</view>
      <button v-if="unsavedPeople.length||state.pending" class="primary-button" :disabled="state.busy||(!canSave&&!state.pending)" @click="save()">{{state.pending?'重试未完成项':'一次保存实际摄入'}}</button>
      <button v-if="state.canEditFailed" class="secondary-button" :disabled="state.busy" @click="client.editFailed()">修改未保存项</button>
      <button v-if="selectedPeople.length===1&&!state.saved.length" class="secondary-button" :disabled="state.busy||!canSave" @click="save(true)">保存并聊聊</button>
      <button v-if="state.saved.length===1&&!state.pending" class="secondary-button" @click="chatWithSaved()">继续聊聊</button>
    </view>
    <button v-if="mode!=='list'" class="secondary-button" :disabled="state.busy||!!state.pending" @click="mode='list';client.page()">返回记录列表</button>
    <text v-if="state.pending" class="safe-note">保存尚未全部确认，请在此页重试原请求。不要重新新建相同餐次。</text>
  </view>
</template>
<style scoped>
.journal,.editor{display:flex;flex-direction:column;gap:20rpx}.journal{padding-top:32rpx}.editor{padding:22rpx}.choices{display:flex;gap:12rpx;flex-wrap:wrap;margin:16rpx 0}.choices button{padding:12rpx;font-size:24rpx;background:#eef0e8;border-radius:12rpx}.choices button.active{background:#246b50;color:white}.record{display:flex;flex-direction:column;align-items:flex-start;gap:12rpx;padding:24rpx;width:100%;margin:16rpx 0;font-size:26rpx}.item{display:flex;align-items:center;gap:12rpx;flex-wrap:wrap}.item input{background:#f1f4ef;border-radius:10rpx;padding:12rpx;width:210rpx}.consent{font-size:24rpx;line-height:1.7}.safe-note{text-align:left}button[disabled]{opacity:.5}
</style>
