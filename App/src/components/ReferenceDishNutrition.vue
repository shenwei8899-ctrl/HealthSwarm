<script setup>
import { computed, ref, watch } from 'vue'
import { referenceNutritionOptions, referenceNutritionItems } from '../utils/reference-serving.js'
const props = defineProps({ dish: { type: Object, required: true } })
const selected = ref('per100')
const options = computed(() => referenceNutritionOptions(props.dish))
const current = computed(() => options.value.find(option => option.key === selected.value) || options.value[0])
const items = computed(() => referenceNutritionItems(current.value))
const available = computed(() => items.value.some(item => item.available))
watch(() => props.dish, () => { selected.value = 'per100' })
</script>

<template>
  <view class="reference-nutrition">
    <scroll-view scroll-x class="nutrition-options"><view><button v-for="option in options" :key="option.key" :aria-pressed="current.key === option.key" :class="{ selected: current.key === option.key }" @click="selected = option.key">{{ option.label }}</button></view></scroll-view>
    <text class="nutrition-basis">{{ current.key === 'per100' ? '每100克计划成品' : current.key === 'whole' ? '本次整道菜合计' : current.label + '的计划份量' }} · {{ available ? '营养估算' : '暂未核算' }}</text>
    <view class="nutrition-values"><view v-for="item in items" :key="item.key"><text>{{ item.label }}</text><text>{{ item.text }}{{ item.available ? ' ' + item.unit : '' }}</text></view></view>
    <text class="nutrition-note">{{ available ? '依据已发布食品数据计算；成品份量为建议估算，实际摄入随分餐变化。' : '缺少可核对的配方、食材用量或营养资料，未用零值代替。' }}</text>
  </view>
</template>

<style scoped>
.reference-nutrition{padding:12px 0}.nutrition-options>view{display:flex;gap:8px}.nutrition-options button{flex:none;margin:0;padding:6px 14px;min-height:36px;font-size:13px;line-height:24px;border-radius:18px;background:var(--ui-accent-soft);color:var(--ui-muted)}.nutrition-options button.selected{background:var(--ui-accent);color:#fff}.nutrition-options button:after{border:0}
.nutrition-basis,.nutrition-note{display:block;margin:14px 0;color:var(--ui-muted);font-size:12px;line-height:1.7}.nutrition-values{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.nutrition-values>view>text{display:block;font-size:12px;color:var(--ui-muted)}.nutrition-values>view>text+text{margin-top:5px;font-size:15px;color:var(--ui-text);overflow-wrap:anywhere}.nutrition-note{font-size:11px}
</style>
