<script setup>
import { computed } from 'vue'
import { referenceNutritionItems } from '../utils/reference-serving.js'
const props = defineProps({ dish: { type: Object, required: true } })
const items = computed(() => referenceNutritionItems(props.dish))
const available = computed(() => items.value.some(item => item.available))
</script>

<template>
  <view class="reference-nutrition">
    <text class="nutrition-basis">整道菜合计 · 按原食谱用量</text>
    <view class="nutrition-values"><view v-for="item in items" :key="item.key"><text>{{ item.label }}</text><text>{{ item.text }}{{ item.available ? ' ' + item.unit : '' }}</text></view></view>
    <text class="nutrition-note">{{ available ? '依据原食谱食材用量与已发布食品数据计算，数值为营养估算。' : '缺少可核对的原食谱用量或营养资料，暂未核算。' }}</text>
  </view>
</template>

<style scoped>
.reference-nutrition{padding:12px 0}
.nutrition-basis,.nutrition-note{display:block;margin:14px 0;color:var(--ui-muted);font-size:12px;line-height:1.7}.nutrition-values{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.nutrition-values>view>text{display:block;font-size:12px;color:var(--ui-muted)}.nutrition-values>view>text+text{margin-top:5px;font-size:15px;color:var(--ui-text);overflow-wrap:anywhere}.nutrition-note{font-size:11px}
</style>
