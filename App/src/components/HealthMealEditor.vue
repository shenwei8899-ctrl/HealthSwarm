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
  <view class="editor-time"><picker mode="date" :value="localTime().slice(0,10)" :disabled="disabled" @change="changeTime('date',$event.detail.value)"><view class="time-value">{{localTime().slice(0,10)}} <text>⌄</text></view></picker><picker mode="time" :value="localTime().slice(11,16)" :disabled="disabled" @change="changeTime('time',$event.detail.value)"><view class="time-value">{{localTime().slice(11,16)}} <text>⌄</text></view></picker><picker :range="names" :value="types.indexOf(meal.meal_type)" :disabled="disabled" @change="meal.meal_type=types[$event.detail.value]"><view class="time-value">{{names[types.indexOf(meal.meal_type)]}} <text>⌄</text></view></picker></view>
  <view v-for="(item,index) in meal.items" :key="item.item_id" class="meal-item">
   <view class="item-heading"><text>菜品 {{index+1}}</text><label><text>吃过</text><switch :checked="!item.excluded" :disabled="disabled" color="#0674ed" @change="item.excluded=!$event.detail.value"/></label></view>
   <input v-model="item.name" class="field-input dish-name-input" maxlength="120" :disabled="disabled" placeholder="菜品或食物名称" @input="rename(item)"/>
   <view v-if="coarse" class="editor-portions"><button v-for="value in portions" :key="value" :class="{active:portion(item)===value}" :aria-pressed="portion(item)===value" :disabled="disabled" @click="setPortion(item,value)">{{value}}</button></view>
   <view class="editor-row"><label>{{coarse?'实际克数（选填）':'可食克数'}}<input :value="gramsValue(item)" type="digit" class="field-input" :disabled="disabled||!!item.portion_reference_id" placeholder="未知留空" @input="changeGrams(item,$event.detail.value)"/></label><label v-if="!coarse">个人比例（0～1）<input v-model="item.share_ratio" type="digit" class="field-input" :disabled="disabled" placeholder="未知留空"/></label></view>
   <text v-if="item.portion_reference_id" class="editor-note">使用菜谱份量参考；更换菜谱后可填写克数。</text>
   <button class="recipe-link" :disabled="disabled" @click="mapping=mapping===index?-1:index;if(mapping===index)emit('search','')"><text>匹配菜谱</text><text>{{mapping===index?'收起':'选择'}} ›</text></button>
   <view v-if="mapping===index" class="recipe-choice"><view class="recipe-search"><input v-model="query" class="field-input" placeholder="搜索菜谱" :disabled="disabled"/><button :disabled="disabled" @click="emit('search',query)">搜索</button></view><button v-for="recipe in recipes" :key="recipe.id" :disabled="disabled" @click="mapRecipe(recipe)">{{recipe.name}} <text>›</text></button><text v-if="!recipes.length" class="editor-note">暂无匹配菜谱</text></view>
  </view>
  <button class="add-dish" :disabled="disabled||meal.items.length>=30" @click="add">＋ 添加菜品</button>
  <text class="editor-note">缺少的营养数据保持未知</text>
 </view>
</template>
<style scoped>
.meal-editor{display:flex;flex-direction:column;gap:22rpx}.editor-time{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12rpx;padding:8rpx 20rpx;background:#fff;border:1rpx solid #e7ebf2;border-radius:22rpx;font-size:27rpx}.editor-time .time-value{min-height:44px;display:flex;align-items:center;gap:10rpx}.editor-time text{color:#65728c}.meal-item{padding:22rpx;background:#fff;border:1rpx solid #e7ebf2;border-radius:26rpx;display:flex;flex-direction:column;gap:18rpx}.item-heading{display:flex;justify-content:space-between;align-items:center;font-size:28rpx;font-weight:500}.item-heading label{display:flex;align-items:center;gap:14rpx;min-height:44px;font-weight:400;color:#65728c}.meal-editor .field-input{width:100%;box-sizing:border-box;min-height:44px;margin:0;border:1rpx solid #e5eaf1;border-radius:16rpx;background:#fafbfc;font-size:28rpx;padding:16rpx 20rpx}.editor-portions{display:flex;gap:10rpx}.editor-portions button{flex:1;min-height:44px;min-width:0;padding:10rpx 4rpx;border:1rpx solid #e7ebf2;background:#f7f8fa;border-radius:16rpx;font-size:26rpx;color:#65728c}.editor-portions .active{border-color:#74b2ff;color:#0674ed;background:#f2f7ff}.editor-row{display:flex;gap:16rpx}.editor-row>label{flex:1;min-width:0;font-size:26rpx;color:#65728c;line-height:1.6}.editor-row input{margin-top:10rpx!important}.recipe-link{display:flex;justify-content:space-between;align-items:center;min-height:44px;width:100%;font-size:27rpx;color:#65728c}.recipe-link>text:last-child{color:#0674ed}.recipe-choice{display:flex;flex-direction:column;gap:14rpx;border-top:1rpx solid #edf0f5;padding-top:18rpx}.recipe-search{display:flex;align-items:center;gap:18rpx}.recipe-search input{flex:1;min-width:0}.recipe-choice button{display:flex;justify-content:space-between;align-items:center;min-height:44px;text-align:left;font-size:27rpx;color:#0674ed}.add-dish{min-height:44px;border:1rpx solid #c6d9f4;border-radius:999rpx;font-size:28rpx;color:#0674ed;width:100%;background:#fff}.editor-note{display:block;font-size:25rpx;color:#65728c;line-height:1.6;text-align:left}.meal-editor button[disabled]{opacity:.45}
@media(max-width:350px){.editor-time,.editor-row>label,.editor-portions button,.editor-note{font-size:12px}.meal-editor .field-input,.recipe-link,.recipe-choice button{font-size:14px}}
</style>
