<script setup>
import { ref } from 'vue'
import { newHealthRequestId } from '../services/health-task-flow.js'
const props = defineProps({ meal: { type: Object, required: true }, disabled: Boolean, coarse: Boolean, recipes: { type: Array, default: () => [] } })
const emit = defineEmits(['search'])
const query = ref(''), mapping = ref(-1)
const portions=['少量','一般','较多','不确定']
function portion(item){return (item.uncertainties||[]).find(x=>x.startsWith('本人粗略份量：'))?.slice(7)||'不确定'}
function setPortion(item,value){item.uncertainties=[...(item.uncertainties||[]).filter(x=>!x.startsWith('本人粗略份量：')),'本人粗略份量：'+value]}
function rename(item){item.food_id=null;item.recipe_version_id=null;item.portion_reference_id=null;item.portion_count=null}
function gramsValue(item) {
  if (!props.coarse) return item.grams
  if (item.grams == null || item.grams === '' || item.share_ratio == null) return ''
  return Number(item.grams) * Number(item.share_ratio)
}
function changeGrams(item, value) {
  if (props.disabled || item.portion_reference_id) return
  item.grams = value
  item.portion_source = 'manual'
  if (props.coarse) {
    item.share_ratio = value === '' ? null : 1
    if (value === '') item.portion_source = 'unknown'
  }
}
const types = ['breakfast', 'lunch', 'dinner', 'snack'], names = ['早餐', '午餐', '晚餐', '加餐']
function localTime() {
  const time = Date.parse(props.meal.eaten_at)
  return Number.isFinite(time) ? new Date(time + 8 * 3600000).toISOString().slice(0, 16) : ''
}
function changeTime(part, value) {
  const current = localTime()
  if (!current || props.disabled) return
  props.meal.eaten_at = (part === 'date' ? value + current.slice(10) : current.slice(0, 11) + value) + ':00+08:00'
}
function add() {
  if (!props.disabled) props.meal.items.push({ item_id: newHealthRequestId(), name: '待核对食物', grams: null, share_ratio: 1, portion_source: 'manual', locations: [], excluded: false })
}
function mapRecipe(recipe) {
  if (props.disabled || !props.meal.items[mapping.value]) return
  Object.assign(props.meal.items[mapping.value], { name: recipe.name, food_id: null, recipe_version_id: recipe.id,
    portion_reference_id: null, portion_count: null, portion_source: 'manual' })
  mapping.value = -1
}
</script>
<template>
  <view class="meal-editor">
    <text class="form-label">实际进食时间（北京时间）</text>
    <view class="editor-row"><picker mode="date" :value="localTime().slice(0,10)" :disabled="disabled" @change="changeTime('date',$event.detail.value)"><view class="field-input">{{localTime().slice(0,10)}} ›</view></picker><picker mode="time" :value="localTime().slice(11,16)" :disabled="disabled" @change="changeTime('time',$event.detail.value)"><view class="field-input">{{localTime().slice(11,16)}} ›</view></picker></view>
    <picker :range="names" :value="types.indexOf(meal.meal_type)" :disabled="disabled" @change="meal.meal_type=types[$event.detail.value]"><view class="field-input">{{names[types.indexOf(meal.meal_type)]}} ›</view></picker>
    <view v-for="(item,index) in meal.items" :key="item.item_id" class="meal-item">
      <input v-model="item.name" class="field-input" maxlength="120" :disabled="disabled" placeholder="菜品或食物名称" @input="rename(item)"/>
      <picker v-if="coarse" :range="portions" :disabled="disabled" @change="setPortion(item,portions[$event.detail.value])"><view class="field-input">粗略份量：{{portion(item)}} ›</view></picker>
      <view class="editor-row"><label>{{coarse?'实际克数（选填）':'可食克数'}}<input :value="gramsValue(item)" type="digit" class="field-input" :disabled="disabled||!!item.portion_reference_id" placeholder="未知留空" @input="changeGrams(item,$event.detail.value)"/></label><label v-if="!coarse">个人比例（0～1）<input v-model="item.share_ratio" type="digit" class="field-input" :disabled="disabled" placeholder="未知留空"/></label></view>
      <text v-if="item.portion_reference_id" class="safe-note">当前使用已发布份量参考，可更换菜谱后填写实际克数。</text>
      <label><switch :checked="!item.excluded" :disabled="disabled" @change="item.excluded=!$event.detail.value"/>本次实际吃了这一项</label>
      <button class="secondary-button" :disabled="disabled" @click="mapping=index;emit('search','')">选择 / 更换已发布菜谱</button>
      <view v-if="mapping===index" class="recipe-choice"><input v-model="query" class="field-input" placeholder="搜索菜谱" :disabled="disabled"/><button :disabled="disabled" @click="emit('search',query)">查询</button><button v-for="recipe in recipes" :key="recipe.id" :disabled="disabled" @click="mapRecipe(recipe)">{{recipe.name}} · {{recipe.dataset_version}}</button></view>
      <text v-if="item.locations?.length" class="safe-note">原照片位置证据保留；名称与份量由你核对。</text>
    </view>
    <button class="secondary-button" :disabled="disabled||meal.items.length>=30" @click="add">添加实际吃过的项目</button>
    <text class="safe-note">营养由服务端重新计算；没有可靠数据的项目保持未知。</text>
  </view>
</template>
<style scoped>.meal-editor,.meal-item,.recipe-choice{display:flex;flex-direction:column;gap:18rpx}.meal-item{padding:22rpx;border:1rpx solid #e0e7e1;border-radius:18rpx}.editor-row{display:flex;gap:16rpx}.editor-row>picker,.editor-row>label{flex:1;min-width:0}.meal-item label{font-size:25rpx}.recipe-choice button{font-size:24rpx;text-align:left}.safe-note{text-align:left}</style>
