<script setup>
import { computed } from 'vue'

const props = defineProps({
  dish: { type: Object, required: true },
  recipes: { type: Array, default: () => [] },
  portions: { type: Array, default: () => [] },
  portionLoading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['change'])
const modes = [{ value: 'unknown', label: '份量尚未确定' }, { value: 'grams', label: '填写计划克数' }, { value: 'reference', label: '使用菜谱份量参考' }]
const recipe = computed(() => props.recipes.find(row => row.id === props.dish.recipe_version_id))
const portion = computed(() => props.portions.find(row => row.id === props.dish.portion_reference_id))
function chooseRecipe(event) {
  const row = props.recipes[Number(event.detail.value)]
  if (row && !props.disabled) emit('change', { recipe_version_id: row.id })
}
function chooseMode(event) {
  const mode = modes[Number(event.detail.value)]
  if (mode && !props.disabled) emit('change', { portion_mode: mode.value })
}
function choosePortion(event) {
  const row = props.portions[Number(event.detail.value)]
  if (row && !props.disabled) emit('change', { portion_reference_id: row.id })
}
</script>

<template>
  <view class="dish-editor">
    <text class="field-label">已发布菜谱</text>
    <picker :range="recipes" range-key="name" :value="Math.max(0, recipes.findIndex(row => row.id === dish.recipe_version_id))" :disabled="disabled || !recipes.length" @change="chooseRecipe"><view class="select-field">{{ recipe?.name || (dish.recipe_version_id ? '已选版本不在当前搜索结果' : '请选择已发布菜谱') }}<text>选择</text></view></picker>
    <text v-if="recipe" class="small-copy">{{ recipe.source }} · {{ recipe.dataset_version }}</text>
    <text v-else-if="dish.recipe_version_id" class="small-copy">已保留所选版本，可重新搜索核对菜名；预览将读取服务端菜谱。</text>
    <text class="field-label">计划份量</text>
    <picker :range="modes" range-key="label" :value="Math.max(0, modes.findIndex(row => row.value === dish.portion_mode))" :disabled="disabled" @change="chooseMode"><view class="select-field">{{ modes.find(row => row.value === dish.portion_mode)?.label || modes[0].label }}<text>选择</text></view></picker>
    <input v-if="dish.portion_mode === 'grams'" class="field-input" type="digit" :value="dish.grams" :disabled="disabled" placeholder="填写你计划使用的克数（g）" :maxlength="20" @input="emit('change', { grams: $event.detail.value })" />
    <template v-if="dish.portion_mode === 'reference'">
      <text v-if="portionLoading" class="small-copy">正在读取此菜谱的份量参考…</text>
      <text v-else-if="!portions.length" class="small-copy">此菜谱没有已发布份量参考，请填写克数或保留未知份量。</text>
      <picker v-else :range="portions" range-key="unit_label" :value="Math.max(0, portions.findIndex(row => row.id === dish.portion_reference_id))" :disabled="disabled || portionLoading" @change="choosePortion"><view class="select-field">{{ portion ? portion.unit_label + ' · ' + portion.grams_per_unit + ' g/份' : '请选择此菜谱的份量参考' }}<text>选择</text></view></picker>
      <input class="field-input" type="digit" :value="dish.portion_count" :disabled="disabled || !portion" placeholder="填写你计划使用的份数" :maxlength="20" @input="emit('change', { portion_count: $event.detail.value })" />
    </template>
    <text v-if="dish.portion_mode === 'unknown'" class="small-copy">份量保留未知，相关营养也可能未确定；系统不会替你推算个人份量。</text>
  </view>
</template>

<style scoped>
.field-label{margin-top:18rpx}
.select-field{min-height:90rpx;padding:20rpx 22rpx;border:2rpx solid #dedee3;border-radius:18rpx;background:#fff;display:flex;justify-content:space-between;gap:16rpx;font-size:26rpx;line-height:1.5;margin-top:12rpx}
.select-field>text{flex:none;color:#246b50;font-size:24rpx}
.small-copy{display:block;font-size:23rpx;color:#63636b;line-height:1.6;margin:10rpx 0}
.dish-editor .field-input{margin:14rpx 0;box-sizing:border-box;min-height:88rpx;padding:20rpx 22rpx;border:2rpx solid #dedee3;border-radius:18rpx;font-size:26rpx}
</style>
