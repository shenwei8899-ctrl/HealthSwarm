<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import { request } from '../services/request.js'
import { getSession } from '../services/session.js'
import { storageContext } from '../services/storage.js'
import { validateDailyArrangement } from '../services/daily-arrangement-client.js'
import { localDate } from '../utils/meal-state.js'

const arrangement = ref(null), busy = ref(false), error = ref(''), notice = ref('')
const names = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }
let generation = 0, active = true
async function load() {
  const mine = ++generation, scope = storageContext(), family = getSession()?.householdId, day = localDate()
  busy.value = true; error.value = ''; notice.value = ''; arrangement.value = null
  try {
    if (!family) { notice.value = '请先选择家庭并完成饮食建档。'; return }
    const { data } = await request({path: '/api/family/' + encodeURIComponent(family) + '/daily-arrangements/' + day})
    if (!active || mine !== generation || scope !== storageContext()) return
    if (data.status !== 'ready') {
      notice.value = data.status === 'absent' ? '今日安排尚未生成，可以前往营养师安排三餐。'
        : data.status === 'generating' ? '营养师正在安排三餐，保存完成后即可查看采购清单。'
        : '今日安排尚未完成，可以前往营养师重试恢复。'
      return
    }
    arrangement.value = validateDailyArrangement(data, day)
  } catch (cause) {
    if (active && mine === generation && scope === storageContext()) error.value = cause.message || '暂时无法读取采购清单，请重试。'
  } finally { if (active && mine === generation) busy.value = false }
}
function invalidate() { generation++; arrangement.value = null; busy.value = false; error.value = ''; notice.value = '' }
function purchase(meal) {
  const saved = arrangement.value
  if (!saved || busy.value) return
  uni.navigateTo({url: '/pages/shop/index?purchase=1&arrangement=' + encodeURIComponent(saved.id)
    + '&meal=' + meal.type + '&date=' + saved.date + '&version=' + saved.version})
}
watch(() => storageContext(), () => { invalidate(); void load() })
onMounted(load)
onShow(load)
onHide(invalidate)
onUnmounted(() => { active = false; invalidate() })
</script>

<template>
  <view class="screen daily-purchase">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack()">‹</button><text class="nav-title">今日采购清单</text><button class="text-button" :disabled="busy" @click="load">刷新</button></view></AppNavBar>
    <view class="page-heading"><text class="display-title">三餐食材，按需准备</text><text class="helper">根据今日已保存安排查看食材，购买前会再次核对库存与价格。</text></view>
    <text v-if="busy" class="helper" aria-live="polite">正在读取已保存的采购清单…</text>
    <view v-if="error || notice" class="card status" role="status"><text>{{ error || notice }}</text><button v-if="error" class="secondary-button" :disabled="busy" @click="load">重试读取</button></view>
    <template v-if="arrangement">
      <text class="date-label">{{ arrangement.date }}</text>
      <view v-for="meal in arrangement.meals" :key="meal.type" class="card meal">
        <text class="section-title">{{ names[meal.type] }}</text><text class="helper">{{ meal.members.map(person => person.name).join('、') }}</text>
        <text class="dishes">{{ meal.dishes.map(dish => dish.name).join(' · ') }}</text>
        <button class="primary-button" :disabled="busy" @click="purchase(meal)">查看本餐采购清单</button>
      </view>
    </template>
    <button class="secondary-button" @click="uni.navigateTo({url:'/pages/chat/index'})">{{ arrangement ? '查看或调整今日安排' : '前往家庭营养师' }}</button>
    <button class="text-button" @click="uni.navigateTo({url:'/pages/purchase/index?source=adopted'})">查看其他已采用餐单采购</button>
  </view>
</template>

<style scoped>
.daily-purchase{background:#fafafa;padding-bottom:44rpx}.page-heading{padding:32rpx 0}.helper{display:block;font-size:25rpx;line-height:1.8;color:#777;margin:16rpx 0}.meal,.status{padding:28rpx;margin:24rpx 0}.date-label{display:block;font-size:25rpx;color:#777;margin:24rpx 0}.section-title,.dishes{display:block}.dishes{font-size:28rpx;line-height:1.8;margin:20rpx 0 28rpx}.text-button{font-size:25rpx;padding:20rpx;color:#555}.daily-purchase :deep(.secondary-button){color:#555;border-color:#ddd}
</style>
