<script setup>
import { computed, ref } from 'vue'
import { onLoad, onShow, onHide, onUnload } from '@dcloudio/uni-app'
import { client } from '../../services/runtime.js'
import { createMealPlanController } from '../../ui/meal-plan-controller.js'
import MealPlanSnapshot from '../../components/MealPlanSnapshot.vue'
import MealDishEditor from '../../components/MealDishEditor.vue'

const state = ref({ plans: [], history: [], recipes: [], portions: {}, portionLoading: {} })
let routeMemberId = ''
const controller = createMealPlanController({ client, onChange: value => { state.value = value },
  onUnauthorized: () => uni.reLaunch({ url: '/pages/login/index' }) })
const mealNames = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }
const locked = computed(() => state.value.loading || state.value.busy || state.value.blocked
  || state.value.writeUnknown || state.value.readBackPending || state.value.needsReload)
const shownSnapshot = computed(() => state.value.historyVersion === null ? state.value.currentPlan : state.value.historySnapshot)
const canSwap = computed(() => state.value.currentPlan?.editable && state.value.historyVersion === null && !locked.value)
const searching = ref('')

function editDish(mealType, index, patch) { controller.setDish(mealType, index, patch) }
function editSwap(patch) { controller.setSwap({ replacement: patch }) }
function retryWrite() {
  if (state.value.writeOperation === 'save') controller.save(true)
  else if (state.value.writeOperation === 'swap') controller.confirmSwap(true)
}
function goBack() { uni.navigateBack({ fail: () => uni.reLaunch({ url: '/pages/members/index' }) }) }
onLoad(options => { routeMemberId = typeof options.member_id === 'string' ? options.member_id : '' })
onShow(() => { searching.value = ''; controller.show(routeMemberId) })
onHide(() => { searching.value = ''; controller.hide() })
onUnload(() => { searching.value = ''; controller.dispose() })
</script>

<template>
  <view class="screen access-screen meal-plan-screen">
    <AppNavBar><view class="nav-row"><button class="text-button" @click="goBack">返回</button><text class="nav-title">本人餐单草稿</text><AppIcon name="calendar" :size="30" /></view></AppNavBar>
    <view class="page-heading"><text class="display-title">把三餐安排清楚</text><text class="subtitle">选择已发布菜谱，核对计划份量与营养，明确保存后保留版本历史。</text></view>
    <text v-if="state.loading" class="status-loading">正在核对本人关联与餐单权限…</text>
    <view v-if="state.member" class="notice"><text>{{ state.member.display_name }} · 本人餐单</text><text>这是计划草稿；完整专业档案、适用性审核及正式采用需在各自流程中完成。</text></view>
    <view v-if="state.error" class="error-box" role="alert"><text>{{ state.error }}</text></view>
    <text v-if="state.notice" class="success-note" role="status">{{ state.notice }}</text>
    <view v-if="state.writeUnknown" class="notice"><text>保存结果尚未确认，原内容和请求已保留。请恢复原请求，避免重复创建版本。</text><button class="primary-button" :disabled="state.busy" @click="retryWrite">恢复原{{ state.writeOperation === 'swap' ? '换菜' : '保存' }}请求</button></view>
    <view v-if="state.readBackPending" class="notice"><text>写入已得到服务端确认，详情回读暂未完成。</text><button class="secondary-button" :disabled="state.busy || state.detailLoading" @click="controller.retryReadBack">重新读取已保存餐单</button></view>
    <button class="secondary-button" :disabled="state.busy || state.writeUnknown || state.readBackPending" @click="controller.reload">{{ state.loading || state.listLoading ? '正在重新读取…' : '重新核对本人身份与餐单' }}</button>

    <template v-if="state.member && !state.loading && !state.blocked">
      <view class="card access-card">
        <text class="section-title">已保存的餐单</text>
        <text v-if="state.listLoading" class="status-loading">正在读取本人餐单…</text>
        <text v-else-if="!state.plans.length" class="body-copy">当前没有已保存餐单。可以在下方选择真实已发布菜谱，预览后明确保存。</text>
        <view class="choice-list"><button v-for="plan in state.plans" :key="plan.plan_id" class="choice-button" :class="{ selected: state.selectedPlanId === plan.plan_id }" :disabled="locked" @click="controller.selectPlan(plan.plan_id)"><view class="choice-indicator" /><view class="choice-copy"><text>{{ plan.plan_date }} · 版本 {{ plan.version }}</text><text class="choice-detail">{{ !plan.supported ? '家庭餐单，请在后台查看' : plan.personalized ? '已保存个体化餐单，仅查看' : '本人普通草稿' }}</text></view></button></view>
        <text v-if="state.truncated" class="small-copy">这里只展示服务端返回的最近餐单，列表已截断；其他餐单请到后台查看。</text>
      </view>

      <view v-if="state.detailLoading" class="card access-card"><text class="status-loading">正在读取所选餐单及历史…</text></view>
      <view v-if="state.currentPlan && !state.detailLoading" class="card access-card">
        <text class="section-title">{{ state.historyVersion === null ? '当前餐单' : '历史快照' }} · 版本 {{ state.historyVersion === null ? state.currentPlan.version : state.historyVersion }}</text>
        <view class="history-list"><button class="text-button" :disabled="locked" @click="controller.showHistory(null)">查看当前版本 {{ state.currentPlan.version }}</button><button v-for="revision in state.history" :key="revision.version" class="text-button" :disabled="locked" @click="controller.showHistory(revision.version)">历史版本 {{ revision.version }} · {{ revision.reason }}</button></view>
        <text v-if="state.historyVersion !== null" class="notice">历史只用于核对。换菜操作需要回到当前版本。</text>
        <MealPlanSnapshot v-if="shownSnapshot" :snapshot="shownSnapshot" />
        <template v-if="canSwap"><text class="field-label">明确选择要更换的菜品</text><view v-for="meal in state.currentPlan.meals" :key="meal.meal_type" class="swap-choices"><button v-for="dish in meal.dishes" :key="dish.dish_index" class="text-button" @click="controller.startSwap(meal.meal_type, dish.dish_index)">更换{{ mealNames[meal.meal_type] }} · {{ dish.name }}</button></view></template>
        <text v-if="state.currentPlan.personalized" class="small-copy">此餐单的个体化调整请使用后台安全改餐，普通草稿换菜入口未开放。</text>
      </view>

      <view class="card access-card">
        <text class="section-title">已发布菜谱目录</text>
        <text class="body-copy">目录为空时请先在后台审核发布菜谱；页面不会用演示内容代替菜谱。</text>
        <input v-model="searching" class="field-input" :disabled="locked || state.catalogLoading" :maxlength="120" placeholder="按菜名搜索" @confirm="controller.searchRecipes(searching)" />
        <button class="secondary-button" :disabled="locked || state.catalogLoading" @click="controller.searchRecipes(searching)">{{ state.catalogLoading ? '正在读取菜谱…' : '搜索已发布菜谱' }}</button>
        <text v-if="!state.catalogLoading && !state.recipes.length" class="small-copy">当前搜索没有可选的已发布菜谱，可以换一个关键词。</text>
      </view>

      <view v-if="state.swap" class="card access-card">
        <text class="section-title">确认更换{{ mealNames[state.swap.meal_type] }}的一道菜</text>
        <text class="body-copy">保存时由服务端重新计算三餐营养，原版本保留。该操作不表示专业审核通过。</text>
        <MealDishEditor :dish="state.swap.replacement" :recipes="state.recipes" :portions="state.portions[state.swap.replacement.recipe_version_id] || []" :portion-loading="state.portionLoading[state.swap.replacement.recipe_version_id] || false" :disabled="locked" @change="editSwap" />
        <input class="field-input" :value="state.swap.reason" :disabled="locked" :maxlength="500" placeholder="填写这次换菜原因" @input="controller.setSwap({ reason: $event.detail.value })" />
        <button class="primary-button" :disabled="locked || !state.swap.replacement.recipe_version_id" @click="controller.confirmSwap()">确认换菜并保存新版本</button>
        <button class="text-button" :disabled="locked" @click="controller.cancelSwap">取消这次换菜选择</button>
      </view>

      <view v-if="state.draft" class="card access-card">
        <text class="section-title">新建三餐草稿</text>
        <text class="field-label">计划日期</text>
        <picker mode="date" :value="state.draft.plan_date" :disabled="locked" @change="controller.setDate($event.detail.value)"><view class="select-field">{{ state.draft.plan_date || '请选择计划日期' }}<text>选择</text></view></picker>
        <view v-for="meal in state.draft.meals" :key="meal.meal_type" class="draft-meal">
          <text class="section-title">{{ mealNames[meal.meal_type] }}</text>
          <view v-for="(dish, index) in meal.dishes" :key="index" class="draft-dish">
            <text class="small-copy">第 {{ index + 1 }} 道菜</text>
            <MealDishEditor :dish="dish" :recipes="state.recipes" :portions="state.portions[dish.recipe_version_id] || []" :portion-loading="state.portionLoading[dish.recipe_version_id] || false" :disabled="locked" @change="editDish(meal.meal_type, index, $event)" />
            <button v-if="meal.dishes.length > 1" class="text-button" :disabled="locked" @click="controller.removeDish(meal.meal_type, index)">移除这道菜</button>
          </view>
          <button class="text-button" :disabled="locked || meal.dishes.length >= 10" @click="controller.addDish(meal.meal_type)">添加一道{{ mealNames[meal.meal_type] }}菜品</button>
        </view>
        <button class="primary-button" :disabled="locked || !state.recipes.length || !state.draft.plan_date" @click="controller.preview()">计算三餐草稿预览</button>
      </view>

      <view v-if="state.preview" class="card access-card">
        <text class="section-title">尚未保存的三餐预览</text>
        <MealPlanSnapshot :snapshot="state.preview" />
        <text class="notice">请核对菜谱、计划份量及未确定项，再明确保存为普通草稿。</text>
        <button class="primary-button" :disabled="locked" @click="controller.save()">确认保存这份普通草稿</button>
      </view>
      <text class="safe-note">计划量与实际摄入分别保存。普通草稿没有评估个人适用性，本页不办理专业审核、正式采用、采购或实际记餐。</text>
    </template>
  </view>
</template>

<style scoped>
.meal-plan-screen .field-input{box-sizing:border-box;min-height:92rpx;padding:20rpx 22rpx;border:2rpx solid #dedee3;border-radius:18rpx;font-size:26rpx;margin:16rpx 0}
.select-field{min-height:90rpx;padding:20rpx 22rpx;border:2rpx solid #dedee3;border-radius:18rpx;display:flex;justify-content:space-between;gap:16rpx;font-size:26rpx;margin:16rpx 0}
.select-field>text{flex:none;color:#246b50}
.small-copy{display:block;font-size:23rpx;color:#63636b;line-height:1.65;margin:12rpx 0}
.history-list,.swap-choices{display:flex;flex-wrap:wrap;gap:8rpx 14rpx;margin:20rpx 0}
.history-list .text-button{border:1rpx solid #dedee3;border-radius:16rpx;font-size:23rpx!important;min-height:68rpx}
.draft-meal{border-top:1rpx solid #e5eae6;margin-top:30rpx;padding-top:26rpx}
.draft-dish{border-bottom:1rpx solid #edf0ed;padding:12rpx 0 20rpx}
.meal-plan-screen .safe-note{line-height:1.65}
</style>
