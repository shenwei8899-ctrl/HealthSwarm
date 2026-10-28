<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import CloudMealPurchase from './CloudMealPurchase.vue'
import { request } from '../services/request.js'
import { getSession } from '../services/session.js'
import { storageContext } from '../services/storage.js'
const props = defineProps({ route: Object })
const arrangement = ref(null), included = ref(['breakfast', 'lunch', 'dinner']), error = ref('')
const names = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }
let alive = true, epoch = 0
const route = computed(() => ({ ...props.route, meal: 'daily', meals: included.value }))
const members = computed(() => [...new Map((arrangement.value?.meals || []).filter(meal => included.value.includes(meal.type)).flatMap(meal => meal.members).map(member => [member.id, member])).values()])
function toggle(type) { included.value = included.value.includes(type) ? included.value.filter(item => item !== type) : ['breakfast', 'lunch', 'dinner'].filter(item => item === type || included.value.includes(item)) }
async function load() {
  const scope = storageContext(), ticket = ++epoch; error.value = ''; arrangement.value = null
  try {
    const r = props.route
    const { data } = await request({ path: '/api/family/' + encodeURIComponent(getSession().householdId) + '/daily-arrangements/' + r.date + (r.daily_plan_version!=null?'?daily_plan_version='+Number(r.daily_plan_version):'') })
    if (!alive || ticket !== epoch || scope !== storageContext()) return
    if (data.status !== 'ready' || data.id !== r.arrangement || data.version !== Number(r.version)) throw new Error('今日安排已更新，请返回今日安排重新读取。')
    arrangement.value = data
  } catch (e) { if (alive && ticket === epoch && scope === storageContext()) error.value = e.message }
}
onMounted(load)
onShow(load)
onUnmounted(() => { alive = false; epoch++ })
const dateLabel=value=>{const match=/^\d{4}-(\d{2})-(\d{2})$/.exec(value||'');return match?Number(match[1])+'月'+Number(match[2])+'日':value}
</script>
<template>
 <view class="screen summary-screen"><AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="uni.navigateBack()">‹</button><text class="nav-title">汇总采购</text><view class="nav-spacer"/></view></AppNavBar>
  <view class="summary-heading"><text>把今天需要的，</text><text>一次备齐。</text></view>
  <view v-if="error" class="card status" role="alert"><text>{{error}}</text><button @click="load">重新读取今日安排</button><button @click="uni.redirectTo({url:'/pages/chat/index'})">返回今日安排</button></view>
  <template v-if="arrangement"><view class="meal-selection"><view class="selection-heading"><text>选择需要采购的餐次</text><text>{{dateLabel(route.date)}}</text></view>
   <button v-for="meal in arrangement.meals" :key="meal.type" class="meal-choice" :aria-pressed="included.includes(meal.type)" @click="toggle(meal.type)"><view class="meal-check" :class="{selected:included.includes(meal.type)}">{{included.includes(meal.type)?'✓':''}}</view><FoodImageSlot :src="meal.image_url" class="choice-image"/><view class="meal-copy"><text class="meal-name">{{names[meal.type]}}</text><text class="meal-dishes">{{meal.dishes.map(d=>d.name).join(' · ')}}</text></view></button>
  </view><CloudMealPurchase v-if="included.length" :key="included.join(',')" :meal="{members}" :route="route"/><text v-else class="safe-note empty-selection">请选择至少一个餐次</text></template>
 </view>
</template>
<style scoped>
.summary-screen{background:#fafbfc;padding-bottom:calc(env(safe-area-inset-bottom) + 180rpx)}.nav-spacer{width:80rpx}.summary-heading{padding:30rpx 8rpx 38rpx}.summary-heading text{display:block;font-size:52rpx;line-height:1.35;font-weight:500;letter-spacing:-1rpx}.meal-selection{border:1rpx solid #e9edf3;background:#fff;border-radius:28rpx;padding:22rpx 18rpx 8rpx}.selection-heading{display:flex;justify-content:space-between;align-items:center;gap:16rpx;padding:0 6rpx 12rpx;font-size:27rpx}.selection-heading text:last-child{color:#65728c;font-size:25rpx;white-space:nowrap}.meal-choice{display:flex;align-items:center;width:100%;gap:20rpx;border-top:1rpx solid #f0f2f6;padding:16rpx 4rpx;text-align:left}.meal-check{width:36rpx;height:36rpx;flex-shrink:0;border:2rpx solid #bcc4d3;border-radius:8rpx;display:flex;align-items:center;justify-content:center;font-size:27rpx;color:#fff}.meal-check.selected{border-color:#0879f9;background:#0879f9}.choice-image{width:128rpx;height:128rpx}.meal-copy{min-width:0;flex:1}.meal-name{display:block;font-size:29rpx;font-weight:500}.meal-dishes{display:block;font-size:25rpx;line-height:1.6;margin-top:6rpx;color:#65728c;overflow-wrap:anywhere}.status{padding:24rpx;line-height:1.7;font-size:27rpx}.status button{margin-top:16rpx;color:#0674ed;min-height:44px}.empty-selection{padding:40rpx 0}
</style>
