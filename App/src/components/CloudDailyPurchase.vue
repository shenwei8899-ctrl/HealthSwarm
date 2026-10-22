<script setup>
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
    const { data } = await request({ path: '/api/family/' + encodeURIComponent(getSession().householdId) + '/daily-arrangements/' + r.date })
    if (!alive || ticket !== epoch || scope !== storageContext()) return
    if (data.status !== 'ready' || data.id !== r.arrangement || data.version !== Number(r.version)) throw new Error('今日安排已更新，请返回今日安排重新读取。')
    arrangement.value = data
  } catch (e) { if (alive && ticket === epoch && scope === storageContext()) error.value = e.message }
}
onMounted(load)
onShow(load)
onUnmounted(() => { alive = false; epoch++ })
</script>
<template>
  <view class="screen summary-screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack()">‹</button><text class="nav-title">{{route.date}} · 汇总采购</text><view /></view></AppNavBar>
    <text class="safe-note">选择要采购的餐次，同一种食材合并需求后计算包装数量。</text>
    <view v-if="error" class="card status"><text>{{error}}</text><button @click="load">重新读取今日安排</button><button @click="uni.redirectTo({url:'/pages/chat/index'})">返回今日安排</button></view>
    <template v-if="arrangement"><button v-for="meal in arrangement.meals" :key="meal.type" class="card meal-choice" @click="toggle(meal.type)"><text>{{included.includes(meal.type) ? '✓' : '○'}} {{names[meal.type]}}</text><text>{{meal.dishes.map(dish => dish.name).join(' · ')}}</text></button>
      <CloudMealPurchase v-if="included.length" :key="included.join(',')" :meal="{members}" :route="route" />
      <text v-else class="safe-note">请选择至少一个餐次。</text>
    </template>
  </view>
</template>
<style scoped>
.summary-screen{padding-bottom:calc(env(safe-area-inset-bottom) + 180rpx)}.meal-choice{display:flex;flex-direction:column;gap:16rpx;width:100%;padding:28rpx;margin-top:20rpx;text-align:left;font-size:28rpx}.meal-choice>text+text{font-size:24rpx;color:#777}.status{padding:28rpx;line-height:1.7}
</style>
