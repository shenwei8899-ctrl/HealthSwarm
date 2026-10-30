<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({ plan: Object, cardMode: Boolean, hideDetails: Boolean })
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
const nutritionItems = computed(() => [
 ['kcal','热量','kcal'],['protein','蛋白质','g'],['fat','脂肪','g'],
 ['carbs','碳水','g'],['fiber','膳食纤维','g'],['sodium','钠','mg'],
].map(([key,label,unit]) => ({key,label,unit,value:props.plan.nutrition?.[key]})))
const nutritionLines = computed(() => [
  [['kcal', '热量', ' kcal'], ['protein', '蛋白质', 'g'], ['fat', '脂肪', 'g']],
  [['carbs', '碳水', 'g'], ['fiber', '膳食纤维', 'g'], ['sodium', '钠', 'mg']],
].map(line => line.map(([key, label, unit]) => {
  const value = props.plan.nutrition?.[key]
  return `${label} ${Number.isFinite(value) ? value + unit : '暂无法估算'}`
}).join(' · ')))
</script>

<template>
  <view class="meal-notes" :class="{'is-card-mode':cardMode}">
    <view class="nutrition-section">
      <view class="nutrition-heading"><text class="note-title">{{cardMode?'本餐总体营养':'本餐总体营养 · '+members.length+' 人合计'}}</text><text v-if="cardMode" class="nutrition-count">{{members.length}} 人合计</text></view>
      <view v-if="plan.nutrition&&cardMode" class="nutrition-grid"><view v-for="item in nutritionItems" :key="item.key" class="nutrition-item"><text class="nutrition-label">{{item.label}}</text><view class="nutrition-value" :class="{'is-unknown':!Number.isFinite(item.value)}"><text>{{Number.isFinite(item.value)?item.value:'暂无法估算'}}</text><text v-if="Number.isFinite(item.value)" class="nutrition-unit">{{item.unit}}</text></view></view></view>
      <view v-else-if="plan.nutrition" class="nutrition-lines">
        <text v-for="(line, index) in nutritionLines" :key="index">{{ line }}</text>
      </view>
      <text v-else class="nutrition-unavailable">该菜谱暂无可用营养数据</text>

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
        <view v-if="cardMode" class="portion-list"><template v-if="selectedNotes?.dishes?.length"><view v-for="(portion,index) in selectedNotes.dishes" :key="portion.recipeId||index" class="portion-row"><text class="portion-name">{{portion.name||plan.dishes.find(dish=>dish.recipeId===portion.recipeId)?.name}}</text><text class="portion-value">{{portion.amount!=null&&portion.amount!==''?portion.amount+(portion.unit||''):'份量待确认'}}</text></view></template><text v-else class="portion-missing">份量待确认</text></view>
        <view v-else class="portion-dishes">
          <template v-if="selectedNotes?.dishes?.length"><text v-for="(portion, index) in selectedNotes.dishes" :key="portion.recipeId">{{ index ? ' · ' : '' }}{{ portion.name || plan.dishes.find(dish=>dish.recipeId===portion.recipeId)?.name }} {{ portion.amount }}{{ portion.unit }}</text></template>
          <text v-else>份量待确认</text>
        </view>
        <text class="cooked-weight">{{selectedNotes?.dishes?.length?'熟制后可食重量':'当前没有可用的个人份量数据'}}</text>
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
    <button v-if="!hideDetails" class="details-toggle" @click="detailsOpen = !detailsOpen">
      <text>营养依据与安全提醒</text><text>{{ detailsOpen ? '收起 −' : '展开 +' }}</text>
    </button>
    <view v-if="!hideDetails&&detailsOpen" class="note-details">
      <text v-if="plan.nutrition" class="estimate">{{plan.sourceType==='api'?'按菜谱配方与建议份量估算':'示例估算'}}</text>
      <text class="safety">{{ plan.safetyText }}</text>
      <text v-for="note in selectedNotes?.notes || []" :key="note">{{ note }}</text>
      <text>烹饪注意：生熟分开、彻底加热，调味料另放。</text>
    </view>
  </view>
</template>

<style scoped>
.meal-notes{font-size:25rpx;line-height:1.8;color:#fff}
.nutrition-section,.portion-section{border-top:1rpx solid rgba(255,255,255,.22);margin-top:26rpx;padding-top:24rpx}
.note-title{font-size:26rpx;font-weight:500;line-height:1.6}
.nutrition-lines{display:flex;flex-direction:column;gap:8rpx;margin-top:10rpx;color:#f0f1f4}
.nutrition-lines text{overflow-wrap:anywhere}
.nutrition-unavailable{display:block;margin-top:10rpx;color:#f0f1f4}
.estimate,.cooked-weight{display:block;font-size:25rpx;color:#c5ddcf;margin-top:6rpx}
.portion-heading{display:flex;align-items:center;flex-wrap:wrap;gap:14rpx 20rpx}
.member-tabs{display:flex;flex-wrap:wrap;gap:8rpx;min-width:0;max-width:100%}
.member-tab{margin:0;padding:8rpx 16rpx;min-height:60rpx;line-height:1.6;font-size:25rpx;border:0;border-radius:16rpx;background:transparent;color:#f0f1f4;max-width:100%;overflow-wrap:anywhere}
.member-tab::after,.details-toggle::after{border:0}
.member-tab.active{background:#d6f095;color:#184b3a;font-weight:500}
.portion-panel{margin-top:18rpx}
.portion-dishes{display:flex;flex-wrap:wrap;line-height:1.9}
.portion-reminder{display:block;margin-top:12rpx}
.details-toggle{display:flex;align-items:center;justify-content:space-between;gap:16rpx;width:100%;margin:20rpx 0 0;padding:8rpx 0;background:transparent;color:#d5e8dc;font-size:25rpx;line-height:1.6;text-align:left}
.details-toggle text:last-child{white-space:nowrap;flex-shrink:0}
.note-details,.safety-alert{display:flex;flex-direction:column;gap:10rpx;margin-top:12rpx;font-size:25rpx}
.safety-alert{padding:16rpx;border-radius:16rpx;background:rgba(255,255,255,.1)}
.safety{font-weight:500}
</style>

<style scoped>
.meal-notes.is-card-mode{display:flex;flex-direction:column;gap:14px;color:var(--ui-text);font-size:14px;line-height:1.6;padding-top:16px;padding-bottom:4px}.is-card-mode .nutrition-section,.is-card-mode .portion-section{margin:0;padding:18px;border:1px solid rgba(255,255,255,.9);border-radius:24px;background:var(--ui-bubble);box-shadow:inset 0 1px 0 #fff,0 4px 18px rgba(48,55,75,.025)}.is-card-mode .nutrition-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.is-card-mode .note-title{font-size:16px;font-weight:600;color:var(--ui-text)}.nutrition-count{font-size:12px;color:var(--ui-muted);flex-shrink:0}.nutrition-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px 20px;margin-top:18px}.nutrition-item{min-width:0}.nutrition-label{display:block;font-size:12px;color:var(--ui-muted);line-height:1.5}.nutrition-value{display:flex;align-items:baseline;gap:5px;margin-top:3px;color:var(--ui-text);font-size:19px;font-weight:600;line-height:1.5;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.nutrition-value.is-unknown{font-size:13px;font-weight:400;color:var(--ui-muted)}.nutrition-unit{font-size:12px;font-weight:400;color:var(--ui-muted)}.is-card-mode .nutrition-unavailable{font-size:13px;color:var(--ui-muted);margin-top:14px}.is-card-mode .portion-heading{justify-content:space-between;gap:8px 12px}.is-card-mode .member-tabs{gap:6px}.is-card-mode .member-tab{display:flex;align-items:center;justify-content:center;min-width:44px;min-height:40px;padding:7px 12px;border-radius:99px;font-size:13px;color:var(--ui-muted);background:#f5f6f8}.is-card-mode .member-tab.active{background:var(--ui-accent-soft);color:var(--ui-text);font-weight:500}.is-card-mode .portion-panel{margin-top:14px}.portion-list{display:flex;flex-direction:column;gap:12px}.portion-row{display:flex;justify-content:space-between;align-items:baseline;gap:14px;font-size:15px;line-height:1.65}.portion-name{flex:1;min-width:0;overflow-wrap:anywhere;color:var(--ui-text)}.portion-value{flex-shrink:0;color:var(--ui-text);font-weight:500;font-variant-numeric:tabular-nums}.portion-missing{color:var(--ui-muted);font-size:13px}.is-card-mode .cooked-weight{font-size:12px;color:var(--ui-muted);margin-top:8px}.is-card-mode .portion-reminder{margin-top:10px;font-size:12px;color:var(--ui-muted);line-height:1.7}.is-card-mode .safety-alert{margin-top:0;color:var(--ui-text);font-size:13px}@media(max-width:350px){.is-card-mode .nutrition-section,.is-card-mode .portion-section{padding:16px}.nutrition-grid{column-gap:16px}.portion-row{font-size:14px}}
</style>
