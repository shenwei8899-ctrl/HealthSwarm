<script setup>
import { computed, ref } from 'vue'

const props = defineProps({ portions: { type: Array, required: true } })
const expanded = ref(false)
const visible = computed(() => expanded.value ? props.portions : props.portions.slice(0, 4))
</script>

<template>
  <view class="dish-portions">
    <view v-if="visible.length" class="portion-list">
      <view v-for="person in visible" :key="person.memberId" class="portion">
        <text>{{ person.name }}</text><text class="grams">{{ person.grams }} 克</text>
      </view>
    </view>
    <text v-else>个人份量待确定</text>
    <button v-if="portions.length > 4" class="portion-toggle" :aria-expanded="expanded" @click="expanded = !expanded">
      {{ expanded ? '收起成员' : '展开全部成员' }}
    </button>
  </view>
</template>

<style scoped>
.dish-portions { color: var(--ui-muted, #65728c); font-size: 13px; line-height: 1.6; }
.portion-list { display: flex; flex-wrap: wrap; gap: 5px 14px; }
.portion { display: flex; flex-wrap: wrap; gap: 0 6px; }
.grams { color: var(--ui-text, #1f242b); font-weight: 500; white-space: nowrap; }
.portion-toggle { margin: 0; min-height: 44px; padding: 0 4px; color: var(--ui-accent, #0674ed); font-size: inherit; }
</style>
