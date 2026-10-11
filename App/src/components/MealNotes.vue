<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({ plan: Object })
const selectedMemberId = ref(null)
const detailsOpen = ref(false)
const members = computed(() => props.plan.members || [])
watch(() => members.value.map(member => member.id), ids => {
  if (!ids.includes(selectedMemberId.value)) selectedMemberId.value = ids[0] ?? null
}, { immediate: true })
const selectedMember = computed(() => members.value.find(member => member.id === selectedMemberId.value))
const selectedNotes = computed(() => (props.plan.memberNotes || []).find(member => member.id === selectedMemberId.value))
const dishes = computed(() => [...(props.plan.dishes || [])].sort((a, b) =>
  Number(/饭|粥|面|主食/.test(b.name)) - Number(/饭|粥|面|主食/.test(a.name))))
const nutritionLines = computed(() => [
  [['kcal', '热量', ' kcal'], ['protein', '蛋白质', 'g'], ['fat', '脂肪', 'g']],
  [['carbs', '碳水', 'g'], ['sugars', '糖类', 'g']],
].map(line => line.map(([key, label, unit]) => {
  const value = props.plan.nutrition?.[key]
  return `${label} ${Number.isFinite(value) ? value + unit : '暂无法估算'}`
}).join(' · ')))
</script>

<template>
  <view class="meal-notes">
    <view class="nutrition-section">
      <text class="note-title">本餐总体营养 · {{ members.length }} 人合计</text>
      <view v-if="plan.nutrition" class="nutrition-lines">
        <text v-for="(line, index) in nutritionLines" :key="index">{{ line }}</text>
      </view>
      <text v-else class="nutrition-unavailable">该菜谱暂无可用营养数据</text>
      <text v-if="plan.nutrition" class="estimate">固定示例估算</text>
    </view>

    <view class="portion-section">
      <view class="portion-heading">
        <text class="note-title">建议份量</text>
        <view class="member-tabs">
          <button v-for="member in members" :key="member.id" class="member-tab"
            :class="{ active: selectedMemberId === member.id }"
            :aria-label="member.name + '的建议份量'"
            @click="selectedMemberId = member.id">{{ member.name }}</button>
        </view>
      </view>
      <view v-if="selectedMember" class="portion-panel">
        <view class="portion-dishes">
          <text v-for="(dish, index) in dishes" :key="dish.name">{{ index ? ' · ' : '' }}{{ dish.name }} XXg</text>
        </view>
        <text class="cooked-weight">（均为熟重 · 份量待计算）</text>
        <text class="portion-reminder">提醒：{{ selectedNotes?.portion || '按实际食量分餐' }}</text>
      </view>
      <text v-else class="cooked-weight">请先选择本餐就餐者</text>
    </view>

    <view v-if="plan.blocked?.length || plan.safeSuggestions?.length" class="safety-alert">
      <text class="safety">{{ plan.safetyText }}</text>
      <text v-for="issue in plan.blocked" :key="issue">{{ issue }}</text>
      <template v-if="plan.safeSuggestions?.length">
        <text>新的安全吃法建议（演示）：{{ plan.safeSuggestions.join('、') }}</text>
        <text>仅调整吃法建议，不修改已支付订单、商品、金额或配送。不提供增购流程。</text>
      </template>
    </view>
    <button class="details-toggle" @click="detailsOpen = !detailsOpen">
      <text>营养依据与安全提醒</text><text>{{ detailsOpen ? '收起 −' : '展开 +' }}</text>
    </button>
    <view v-if="detailsOpen" class="note-details">
      <text class="estimate">{{ plan.nutrition ? '整餐营养为固定示例估算，不是实际营养检测结果' : '该菜谱暂无可用营养数据' }}</text>
      <text class="safety">{{ plan.safetyText }}</text>
      <text v-for="note in selectedNotes?.notes || []" :key="note">{{ note }}</text>
      <text>烹饪注意：生熟分开、彻底加热，调味料另放。</text>
    </view>
  </view>
</template>

<style scoped>
.meal-notes{font-size:24rpx;line-height:1.8;color:#fff}
.nutrition-section,.portion-section{border-top:1rpx solid rgba(255,255,255,.22);margin-top:26rpx;padding-top:24rpx}
.note-title{font-size:26rpx;font-weight:800;line-height:1.6}
.nutrition-lines{display:flex;flex-direction:column;gap:8rpx;margin-top:10rpx;color:#e7f2eb}
.nutrition-lines text{overflow-wrap:anywhere}
.nutrition-unavailable{display:block;margin-top:10rpx;color:#e7f2eb}
.estimate,.cooked-weight{display:block;font-size:21rpx;color:#c5ddcf;margin-top:6rpx}
.portion-heading{display:flex;align-items:center;flex-wrap:wrap;gap:14rpx 20rpx}
.member-tabs{display:flex;flex-wrap:wrap;gap:8rpx;min-width:0;max-width:100%}
.member-tab{margin:0;padding:8rpx 16rpx;min-height:60rpx;line-height:1.6;font-size:24rpx;border:0;border-radius:16rpx;background:transparent;color:#e7f2eb;max-width:100%;overflow-wrap:anywhere}
.member-tab::after,.details-toggle::after{border:0}
.member-tab.active{background:#d6f095;color:#184b3a;font-weight:800}
.portion-panel{margin-top:18rpx}
.portion-dishes{display:flex;flex-wrap:wrap;line-height:1.9}
.portion-reminder{display:block;margin-top:12rpx}
.details-toggle{display:flex;align-items:center;justify-content:space-between;gap:16rpx;width:100%;margin:20rpx 0 0;padding:8rpx 0;background:transparent;color:#d5e8dc;font-size:21rpx;line-height:1.6;text-align:left}
.details-toggle text:last-child{white-space:nowrap;flex-shrink:0}
.note-details,.safety-alert{display:flex;flex-direction:column;gap:10rpx;margin-top:12rpx;font-size:22rpx}
.safety-alert{padding:16rpx;border-radius:16rpx;background:rgba(255,255,255,.1)}
.safety{font-weight:700}
</style>
