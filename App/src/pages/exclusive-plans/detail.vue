<script setup>
import { computed, ref } from 'vue'
import { onLoad, onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import AppIcon from '../../components/AppIcon.vue'
import CookingGuide from '../../components/CookingGuide.vue'
import FoodImageSlot from '../../components/FoodImageSlot.vue'
import CloudMealPurchase from '../../components/CloudMealPurchase.vue'
import { request } from '../../services/request.js'
import { getSession, sessionRevision } from '../../services/session.js'
import { commerce } from '../../services/commerce.js'
import { useCommercePage } from '../../services/commerce-page.js'
import { selectedDay, dayMeals, validPlanRoute } from '../../services/plan-presentation.js'
import { recipeCover } from '../../utils/recipe-cover.js'
import { planTiers, readExclusivePreview, exclusiveImages } from '../../services/exclusive-planning.js'
import { createExclusiveImageFlow } from '../../services/exclusive-image-flow.js'
import { ingredientCopy } from '../../utils/dish-commerce-presentation.js'
const route = ref(null), plan = ref(null), dayNo = ref(1), mealType = ref('breakfast')
const purchasing = ref(false), purchaseData = ref(null)
const panel = ref(''), selectedDishId = ref('')
const visible = ref(false)
const imageFlow = createExclusiveImageFlow({send:exclusiveImages,
  scope:()=>String(sessionRevision())+':'+getSession()?.householdId,
  status:()=>{},
  apply:images=>{
    if(!visible.value)return
    const found=new Map(images.map(image=>[image.file_id,image]))
    for(const item of day.value?.meals||[]){
      const image=found.get(item.source?.file_id)
      if(image?.image_url)item.recipe_snapshot={...item.recipe_snapshot,...image}
    }
  },
})
const { busy, error, run } = useCommercePage(() => { closePanel(); plan.value = null; purchaseData.value = null; selectDay(1) })
const purchasePath = computed(() => '/api/health/v1/families/' + encodeURIComponent(getSession()?.householdId) + '/exclusive-plans/' + encodeURIComponent(route.value?.groupId) + '/tiers/' + encodeURIComponent(route.value?.tier) + '/purchase')
const purchaseReference = computed(() => purchaseData.value ? {
  previewId: route.value.groupId, gaps: purchaseData.value.gaps,
  items: purchaseData.value.items.map(item=>({sku_id:item.sku_id,product_id:item.sku.product_id,product_name:item.sku.product_name,sku_name:item.sku.sku_name,quantity:item.quantity,image_url:item.sku.image_url,
    price_cent:item.sku.price_cent,available_quantity:item.sku.available_quantity,sale_status:item.sku.sale_status})),
} : null)
const purchaseRoute = computed(() => ({arrangement:route.value.groupId+':'+route.value.tier,version:purchaseData.value.scope_hash,date:'',meal:'daily',meals:['breakfast','lunch','dinner']}))
const day = computed(() => selectedDay(plan.value, dayNo.value))
const meals = computed(() => dayMeals(day.value))
const meal = computed(() => meals.value.find(item => item.type === mealType.value))
const dayLabels = computed(() => (plan.value?.days || []).map(item => '第 ' + item.day_no + ' 天'))
const period = computed(() => plan.value?.days?.length || 0)
const panelRecipe = computed(() => {
  const dish = meal.value?.dishes.find(item => item.id === selectedDishId.value)
  if (!dish) return null
  const cover = recipeCover(dish.recipe_snapshot)
  return { ...dish.recipe_snapshot, ...dish, name: dish.recipe_name, recipe_text_source: 'original',
    image_url: cover?.image_url, image_source: cover?.image_source }
})
const ingredientGroups = computed(() => (meal.value?.dishes || []).map(dish => ({
  id: dish.id, name: dish.recipe_name, items: dishIngredients(dish), note: dish.portion_note,
})))
const mealIcon = type => ({breakfast:'sunrise',lunch:'sun',dinner:'moon-stars'}[type])
const dayNumber = number => String(number).padStart(2, '0')
function dishIngredients(dish) { return (Array.isArray(dish.ingredients) ? dish.ingredients : []).map(ingredientCopy).filter(Boolean) }
function ingredientSummary(dish) { return dishIngredients(dish).slice(0, 2).join(' · ') || '食材信息待补充' }
function closePanel() { panel.value = ''; selectedDishId.value = '' }
function openRecipe(dish) {
  if (busy.value || !visible.value || !meal.value?.dishes.some(item => item.id === dish.id)) return
  selectedDishId.value = dish.id
  panel.value = 'recipe'
}
function openIngredients() { if (!busy.value && visible.value && meal.value?.dishes.length) panel.value = 'ingredients' }
function selectMeal(type) {
  if (!meals.value.some(item => item.type === type)) return
  closePanel()
  mealType.value = type
}
onLoad(options => {
  purchasing.value = options.purchase === '1'
  try {
    if (options.group_id) {
      if (!planTiers.includes(options.tier)) throw new Error('请从专属计划页重新选择方案')
      route.value = {groupId: options.group_id, tier: options.tier}
    } else route.value = validPlanRoute(options)
  } catch (e) { error.value = e.message }
})
onShow(()=>{visible.value=true;load()})
onHide(()=>{visible.value=false;closePanel();imageFlow.stop()})
onUnload(()=>{visible.value=false;closePanel();imageFlow.stop()})
function refreshImages(start=false){
  if(!visible.value||!route.value?.groupId||purchasing.value||!plan.value)return
  void imageFlow.open({groupId:route.value.groupId,tier:route.value.tier,dayNo:dayNo.value},{start})
}
function selectDay(number) {
  if (plan.value && !selectedDay(plan.value, number)) return
  closePanel()
  dayNo.value = Number(number)
  mealType.value = 'breakfast'
  refreshImages()
}
function jumpToDay(event) {
  const selected = plan.value?.days?.[Number(event.detail.value)]
  if (selected) selectDay(selected.day_no)
}
function load() {
  if (!route.value) return
  closePanel()
  imageFlow.stop()
  return run(async active => {
    plan.value = null
    purchaseData.value = null
    const {groupId, tier, sn, version} = route.value
    if (purchasing.value && groupId) {
      const {data} = await request({path:purchasePath.value})
      if (active()) {
        plan.value = {tier_name:data.tier_name,members:data.members}
        purchaseData.value = data
      }
      return
    }
    const result = groupId ? await readExclusivePreview(groupId, tier) : await commerce.servicePlan(sn, version)
    if (active()) {
      plan.value = result
      if (!selectedDay(result, dayNo.value)) dayNo.value = Number(result.days?.[0]?.day_no) || 1
      refreshImages(true)
    }
  })
}
function next() { if (plan.value?.status === 'available') uni.navigateTo({url:'/pages/exclusive-plans/schedule?plan_sn='+encodeURIComponent(route.value.sn)+'&plan_version='+route.value.version}) }
function purchase() {
  if (busy.value || !plan.value) return
  if (!route.value.groupId) { next(); return }
  uni.navigateTo({url:'/pages/exclusive-plans/detail?group_id='+encodeURIComponent(route.value.groupId)+'&tier='+encodeURIComponent(route.value.tier)+'&purchase=1'})
}
const back = () => uni.navigateBack()
</script>
<template>
  <view class="screen exclusive-screen detail-screen" :class="{'plan-preview':!purchasing}">
    <AppNavBar :title="purchasing?'计划采购':'计划详情'"><template #left><button class="icon-button" aria-label="返回" @click="back">‹</button></template></AppNavBar>
    <view v-if="error" class="plan-surface plan-empty"><text class="plan-caption">{{error}}</text><button class="plan-secondary" :disabled="busy" @click="load">重新读取</button><button class="plan-text-link" @click="back">返回选择计划</button></view>
    <text v-else-if="busy && !plan" class="plan-notice">正在读取计划…</text>
    <template v-if="plan && purchasing">
      <view class="plan-heading"><text class="plan-title">{{plan.tier_name}}</text><text class="plan-caption">整份 21 天计划</text></view>
      <template v-if="purchaseData">
        <text class="plan-notice purchase-coverage">{{purchaseData.notice}}</text>
        <text v-if="purchaseData.items.some(item=>item.quantity_confirmed===false)" class="plan-notice quantity-warning">部分商品包装数量待确认，请按家庭实际需要调整，当前数量不能视为足够 21 天。</text>
        <view v-if="purchaseData.gaps?.length" class="plan-surface purchase-coverage-gaps"><text class="plan-notice">以下食材未加入购物车，需自行准备或确认：</text><text v-for="(gap,index) in purchaseData.gaps" :key="index" class="plan-notice">{{gap.label||gap.ingredient}}：{{gap.detail}}</text></view>
        <CloudMealPurchase v-if="purchaseData.available" :key="purchaseData.scope_hash" :meal="{members:plan.members}" :route="purchaseRoute" :reference="purchaseReference" :exclusive="{path:purchasePath,scopeHash:purchaseData.scope_hash,initialPurchase:purchaseData}"/>
        <view v-else class="plan-surface plan-empty"><text class="plan-caption">暂无可购买商品</text><button class="plan-secondary" :disabled="busy" @click="load">重新核对</button></view>
      </template>
    </template>
    <template v-if="plan && !purchasing">
      <view class="preview-heading">
        <view class="preview-identity"><view class="preview-symbol" aria-hidden="true"><AppIcon name="record" :size="36"/></view><text>AI 专属计划</text></view>
        <view class="preview-title-row"><text class="preview-title">{{plan.tier_name}}</text><text v-if="period" class="preview-period">{{period}} 天 · 每日三餐</text></view>
        <text class="preview-caption">把一日三餐，安排得更从容</text>
      </view>
      <view class="menu-controls">
        <view class="section-top">
          <text class="plan-section-title">计划菜谱</text>
          <picker :range="dayLabels" :value="Math.max(0,plan.days.findIndex(item => Number(item.day_no) === dayNo))" @change="jumpToDay"><view class="day-picker"><AppIcon name="calendar" :size="28"/><text>选择日期</text><text aria-hidden="true">›</text></view></picker>
        </view>
        <scroll-view scroll-x class="day-tabs" :scroll-into-view="'plan-day-' + dayNo" :show-scrollbar="false">
          <view class="day-tabs-inner"><button v-for="item in plan.days" :id="'plan-day-' + item.day_no" :key="item.day_no" :class="{chosen:Number(item.day_no)===dayNo}" :aria-label="'第 '+item.day_no+' 天'" :aria-pressed="Number(item.day_no)===dayNo" @click="selectDay(item.day_no)"><text class="day-unit">第</text><text class="day-number">{{dayNumber(item.day_no)}}</text><text class="day-unit">天</text></button></view>
        </scroll-view>
        <view class="meal-tabs" role="group" aria-label="选择餐次">
          <button v-for="item in meals" :id="'plan-meal-' + item.type" :key="item.type" :class="[item.type,{chosen:mealType===item.type}]" :aria-pressed="mealType===item.type" @click="selectMeal(item.type)"><AppIcon :name="mealIcon(item.type)" :size="32"/><text>{{item.name}}</text></button>
        </view>
      </view>
      <view class="meal-list">
        <view class="section-top meal-title"><view class="meal-heading"><view class="meal-dot"/><text class="plan-section-title">第 {{dayNo}} 天 · {{meal.name}}</text></view><text class="dish-count">共 {{meal.dishes.length}} 道餐品</text></view>
        <button v-for="dish in meal.dishes" :key="dish.id" class="recipe-block" :aria-label="'查看'+dish.recipe_name+'菜谱'" @click="openRecipe(dish)">
          <FoodImageSlot class="dish-photo" :src="recipeCover(dish.recipe_snapshot)?.image_url" :label="dish.recipe_name" fallback-icon/>
          <view class="dish-copy"><text class="dish-name">{{dish.recipe_name}}</text><text class="dish-summary">{{ingredientSummary(dish)}}</text></view><text class="dish-arrow" aria-hidden="true">›</text>
        </button>
        <view v-if="!meal.dishes.length" class="plan-empty"><text class="plan-caption">这一餐的菜品暂不可用</text></view>
        <button v-else class="meal-ingredients" @click="openIngredients"><AppIcon name="record" :size="30"/><text>本餐食材</text><text class="ingredient-link">查看清单 ›</text></button>
      </view>
      <view class="plan-fixed"><button class="plan-primary" :disabled="busy || (!route.groupId && plan.status!=='available')" @click="purchase"><text>购买计划</text><text class="purchase-arrow" aria-hidden="true">→</text></button></view>
    </template>
    <view v-if="panel && plan && !purchasing" class="detail-panel-mask">
      <view class="detail-panel-backdrop" @tap="closePanel" @touchmove.stop.prevent @wheel.stop.prevent/>
      <view class="detail-panel" role="dialog" aria-modal="true" :aria-label="panel==='recipe'?'菜谱详情':'本餐食材'" @tap.stop>
        <view class="detail-panel-handle"/>
        <view class="detail-panel-header"><view><text class="detail-panel-title">{{panel==='recipe'?'菜谱详情':'本餐食材'}}</text><text class="detail-panel-subtitle">第 {{dayNo}} 天 · {{meal.name}}</text></view><button class="detail-panel-close" aria-label="关闭详情面板" @tap="closePanel">×</button></view>
        <scroll-view scroll-y class="detail-panel-scroll" :show-scrollbar="false">
          <view class="detail-panel-content">
            <CookingGuide v-if="panel==='recipe' && panelRecipe" :dishes="[panelRecipe]" :selected="panelRecipe.id"/>
            <template v-else-if="panel==='ingredients'">
              <text class="ingredient-note">以下为当前餐次的原菜谱食材与用量，尚未按家庭人数核定。</text>
              <view v-for="group in ingredientGroups" :key="group.id" class="ingredient-group"><text class="ingredient-group-title">{{group.name}}</text><text v-for="(item,index) in group.items" :key="index" class="ingredient-item">{{item}}</text><text v-if="!group.items.length" class="ingredient-item ingredient-unknown">食材信息待补充</text><text v-if="group.note" class="ingredient-note">{{group.note}}</text></view>
            </template>
          </view>
        </scroll-view>
      </view>
    </view>
  </view>
</template>
<style scoped>
.detail-screen{min-height:100vh;box-sizing:border-box;overflow:hidden;padding:0 36rpx calc(160rpx + env(safe-area-inset-bottom));color:#424b60;background-color:#f5f6fa;background-image:radial-gradient(ellipse at 5% 0%,rgba(171,203,250,.38),transparent 72%),linear-gradient(180deg,#eff5ff,rgba(245,246,250,0));background-size:100% 380rpx;background-repeat:no-repeat}
.detail-screen button::after{border:0}.detail-screen button[disabled]{opacity:.5}
.icon-button{min-width:88rpx;min-height:88rpx;margin-left:-14rpx;padding:0 14rpx;background:transparent;color:#59657a;font-size:60rpx;line-height:1.4;text-align:left}
.plan-heading{margin:38rpx 8rpx 32rpx}.plan-title{display:block;font-size:52rpx;font-weight:600;letter-spacing:2rpx;line-height:1.5}
.plan-surface{box-sizing:border-box;background:linear-gradient(135deg,rgba(255,255,255,.84),#fff);border:2rpx solid rgba(255,255,255,.95);border-radius:36rpx;box-shadow:0 10rpx 32rpx rgba(71,99,148,.035)}
.menu-controls{padding:28rpx 24rpx 24rpx}.section-top{display:flex;align-items:center;justify-content:space-between;gap:18rpx}.menu-controls .section-top{padding:0 8rpx 24rpx}
.plan-section-title{font-size:30rpx;font-weight:500;line-height:1.6}.day-picker{display:flex;align-items:center;gap:10rpx;min-height:56rpx;padding:0 4rpx;color:#59657a;font-size:23rpx}.day-picker>text:last-child{font-size:32rpx}
.day-tabs{white-space:nowrap;width:100%}.day-tabs-inner{display:inline-flex;gap:12rpx}.day-tabs button{flex:none;min-width:114rpx;margin:0;padding:18rpx 22rpx;border:2rpx solid transparent;border-radius:24rpx;font-size:25rpx;line-height:1.5;background:#f5f7fb;color:#626d80;box-sizing:border-box}.day-tabs button.chosen{background:#e6eaf1;border-color:#b5becd;color:#424b60;font-weight:600}
.meal-tabs{display:flex;gap:8rpx;margin-top:26rpx;padding:8rpx;border-radius:24rpx;background:#f1f4f9}.meal-tabs button{flex:1;margin:0;padding:16rpx 8rpx;border-radius:18rpx;font-size:27rpx;line-height:1.5;background:transparent;color:#626d80}.meal-tabs button.chosen{background:#fff;color:#424b60;box-shadow:0 4rpx 14rpx rgba(73,105,158,.06);font-weight:500}
.meal-title{margin:34rpx 10rpx 20rpx}.meal-title .plan-section-title{font-size:28rpx;color:#59657a}.meal-list{display:flex;flex-direction:column;gap:20rpx}.recipe-block{display:flex;align-items:center;gap:28rpx;min-height:180rpx;padding:24rpx}.dish-photo{width:132rpx;height:132rpx;border-radius:26rpx;flex-shrink:0}.dish-name{flex:1;min-width:0;font-size:31rpx;font-weight:500;line-height:1.65;overflow-wrap:anywhere}
.plan-caption{font-size:27rpx;color:#626d80;line-height:1.7}.plan-empty{display:flex;align-items:center;flex-direction:column;gap:24rpx;padding:56rpx 32rpx;text-align:center}.plan-notice{display:block;color:#626d80;font-size:25rpx;line-height:1.7;padding:22rpx 8rpx}.plan-secondary{min-height:80rpx;padding:18rpx 30rpx;border-radius:24rpx;background:#e6eaf1;color:#424b60;font-size:27rpx}.plan-text-link{padding:14rpx;background:transparent;color:#59657a;font-size:26rpx}.plan-fixed{position:fixed;z-index:10;left:0;right:0;bottom:0;padding:20rpx 32rpx calc(20rpx + env(safe-area-inset-bottom));background:#ffffffef;border-top:1rpx solid #edf1f8}.plan-primary{width:100%;display:flex;justify-content:center;align-items:center;gap:22rpx;min-height:90rpx;padding:20rpx 28rpx;border-radius:28rpx;background:#424b60;color:#fff;font-size:28rpx;line-height:1.5}
.day-tabs button:focus-visible,.meal-tabs button:focus-visible{outline:2px solid #59657a;outline-offset:2px}
@media(max-width:350px){.detail-screen{padding-left:24rpx;padding-right:24rpx}.menu-controls{padding:24rpx 18rpx 20rpx}.dish-photo{width:120rpx;height:120rpx}.recipe-block{gap:22rpx;padding:22rpx}.dish-name{font-size:30rpx}}
@media(min-width:600px){.detail-screen{max-width:480px;margin:0 auto}.plan-fixed{max-width:480px;margin:0 auto;box-sizing:border-box}}
</style>
<style scoped>
/* The procurement branch deliberately retains its existing layout above. */
.plan-preview.detail-screen{padding:0 20px calc(104px + env(safe-area-inset-bottom));color:#3c354c;background-color:#e9e3f7;background-image:radial-gradient(ellipse at 100% 95%,#e8d9f4 0%,transparent 52%),linear-gradient(180deg,#d3defb 0%,#e0e4fc 34%,#eae6f7 100%);background-size:100% 100%;background-repeat:no-repeat}
.plan-preview .icon-button{color:#685c7d}.preview-heading{padding:17px 1px 0}.preview-identity{display:flex;align-items:center;gap:8px;color:#766789;font-size:12px;line-height:1.5}.preview-symbol{display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:9px;color:#fff;background:linear-gradient(145deg,#be97fb,#8651de);box-shadow:inset 1px 1px 1px #ffffff91,0 3px 7px #8356c42a;transform:rotate(-6deg)}.preview-symbol :deep(.app-icon){width:18px!important;height:18px!important;transform:rotate(6deg)}
.preview-title-row{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:10px}.preview-title{min-width:0;color:#3b324d;font-size:29px;line-height:1.3;font-weight:600;overflow-wrap:anywhere}.preview-period{flex-shrink:0;padding:6px 10px;border:1px solid #fff;border-radius:20px;color:#765d94;background:#ffffff7d;font-size:11px;line-height:1.5;white-space:nowrap}.preview-caption{display:block;margin-top:8px;color:#716581;font-size:12px;line-height:1.6}
.plan-preview .menu-controls{margin-top:23px;padding:0}.plan-preview .section-top{gap:12px}.plan-preview .menu-controls .section-top{padding:0;margin-bottom:13px}.plan-preview .plan-section-title{color:#3c354c;font-size:16px;font-weight:500;line-height:1.5}.plan-preview .day-picker{display:flex;align-items:center;gap:6px;min-height:32px;color:#78678d;font-size:12px;padding:0}.plan-preview .day-picker>text:last-child{font-size:18px}.plan-preview .day-tabs{display:block;width:100%;padding:0}.plan-preview .day-tabs-inner{display:inline-flex;gap:8px;padding:0 2px 7px 0}.plan-preview .day-tabs button{display:flex;align-items:center;justify-content:center;gap:3px;flex:none;width:62px;min-width:62px;height:49px;min-height:49px;padding:0;border:1px solid #ffffffd9;border-radius:13px;background:#ffffff80;color:#7b6d90;line-height:1.4}.plan-preview .day-unit{font-size:10px}.plan-preview .day-number{font-size:19px;font-weight:500}.plan-preview .day-tabs button.chosen{color:#fff;background:#8552ce;border-color:#8552ce;box-shadow:0 4px 9px #8357c523}
.plan-preview .meal-tabs{display:flex;gap:8px;margin:8px 0 15px;padding:0;background:transparent;border-radius:0}.plan-preview .meal-tabs button{display:flex;align-items:center;justify-content:center;gap:7px;min-width:0;min-height:44px;padding:8px 4px;border:1px solid #ffffffb8;border-radius:12px;background:#ffffff68;color:#766980;font-size:14px;line-height:1.5}.plan-preview .meal-tabs .breakfast :deep(.app-icon){color:#bc8352}.plan-preview .meal-tabs .lunch :deep(.app-icon){color:#5b9c88}.plan-preview .meal-tabs .dinner :deep(.app-icon){color:#9368c0}.plan-preview .meal-tabs button.chosen{background:#e1d0fa;border-color:#bb96eb;color:#6738a7;font-weight:500;box-shadow:none}.plan-preview .meal-tabs button.chosen :deep(.app-icon){color:#7c48c2}
.plan-preview .meal-list{display:block;overflow:hidden;padding:0 16px;border:1px solid #fff;border-radius:23px;background:#fff;box-shadow:0 8px 22px #54476e06}.plan-preview .meal-title{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:59px;margin:0;padding:12px 0;border-bottom:1px solid #eae3f2}.meal-heading{display:flex;align-items:center;gap:7px;min-width:0}.meal-heading .plan-section-title{font-size:15px}.meal-dot{flex:none;width:7px;height:7px;border-radius:50%;background:#9865e1}.dish-count{flex-shrink:0;padding:5px 8px;border-radius:7px;color:#795299;background:#f1e9fc;font-size:11px;line-height:1.5;white-space:nowrap}
.plan-preview .recipe-block{display:flex;align-items:center;gap:13px;width:100%;min-height:80px;padding:10px 0;margin:0;border-bottom:1px solid #edeaf2;border-radius:0;background:transparent;text-align:left}.plan-preview .dish-photo{width:62px;height:58px;flex:none;border-radius:13px;background:#f1edf7}.plan-preview .dish-photo :deep(.fallback-plate){border-color:#b29acb;box-shadow:inset 0 0 0 6px #f6f1fb;background:#e4d8f2}.dish-copy{flex:1;min-width:0}.plan-preview .dish-name{display:block;min-width:0;color:#3d354b;font-size:16px;font-weight:400;line-height:1.5;overflow-wrap:anywhere}.dish-summary{display:-webkit-box;margin-top:7px;color:#817489;font-size:12px;line-height:1.6;overflow:hidden;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow-wrap:anywhere}.dish-arrow{flex:none;font-size:22px;color:#a18cb6;line-height:1}.plan-preview .meal-list .plan-empty{padding:36px 8px;border:0;box-shadow:none}.plan-preview .meal-list .plan-caption{color:#817489;font-size:13px}
.plan-preview .meal-ingredients{display:flex;align-items:center;gap:7px;min-height:46px;width:calc(100% + 32px);margin:0 -16px;padding:10px 16px;border-radius:0;background:#f3edfb;color:#8056ad;font-size:13px;line-height:1.5;text-align:left}.ingredient-link{margin-left:auto;font-size:12px;white-space:nowrap}.plan-preview .plan-fixed{padding:13px 20px calc(13px + env(safe-area-inset-bottom));border-top:1px solid #ffffffb0;background:#ffffffc9;backdrop-filter:blur(16px)}.plan-preview .plan-primary{display:flex;align-items:center;justify-content:center;gap:21px;min-height:47px;padding:10px 16px;border-radius:16px;background:#424b60;color:#fff;font-size:15px;font-weight:400;line-height:1.5;box-shadow:0 4px 12px #3a3b5720}.purchase-arrow{font-size:20px;color:#c5c1d3}.plan-preview .day-tabs button:focus-visible,.plan-preview .meal-tabs button:focus-visible,.plan-preview .recipe-block:focus-visible{outline:2px solid #8051bc;outline-offset:-3px}
.detail-panel-mask{position:fixed;inset:0;z-index:90;display:flex;align-items:flex-end;justify-content:center}.detail-panel-backdrop{position:absolute;inset:0;background:#362b4e55}.detail-panel{position:relative;display:flex;flex-direction:column;width:100%;max-width:480px;height:84vh;max-height:calc(100vh - 64px);min-height:0;overflow:hidden;border:1px solid #fff;border-bottom:0;border-radius:27px 27px 0 0;background:linear-gradient(180deg,#e8e3fc,#f5f1fc 45%);box-shadow:0 -8px 35px #46355d15}.detail-panel-handle{flex:none;width:32px;height:4px;margin:9px auto 0;border-radius:5px;background:#bdacd5}.detail-panel-header{display:flex;align-items:center;justify-content:space-between;flex:none;padding:13px 16px 16px 21px;border-bottom:1px solid #ffffffb3}.detail-panel-header>view{flex:1;min-width:0}.detail-panel-title{display:block;color:#463452;font-size:19px;font-weight:500;line-height:1.5}.detail-panel-subtitle{display:block;margin-top:3px;color:#8c729f;font-size:12px;line-height:1.5}.detail-panel-close{display:flex;align-items:center;justify-content:center;width:44px;height:44px;flex:none;border-radius:50%;background:#ffffff8c;color:#8f74a7;font-size:28px;line-height:1}.detail-panel-scroll{display:block;flex:1;height:0;min-height:0;width:100%}.detail-panel-content{padding:18px 20px calc(24px + env(safe-area-inset-bottom))}.ingredient-note{display:block;margin-bottom:16px;color:#877092;font-size:12px;line-height:1.8}.ingredient-group{padding:17px 16px;margin-bottom:12px;border:1px solid #fff;border-radius:18px;background:#ffffffda}.ingredient-group-title{display:block;padding-bottom:11px;margin-bottom:8px;border-bottom:1px solid #eae1f3;color:#4e3b5e;font-size:15px;font-weight:500;line-height:1.5}.ingredient-item{display:block;padding:5px 0;color:#725c81;font-size:14px;line-height:1.7;overflow-wrap:anywhere}.ingredient-unknown{color:#94839f}.ingredient-group .ingredient-note{margin:10px 0 0}
@media(max-width:350px){.plan-preview.detail-screen{padding-left:16px;padding-right:16px}.preview-title{font-size:27px}.preview-period{padding:5px 8px;font-size:10px}.plan-preview .meal-list{padding-left:13px;padding-right:13px}.plan-preview .meal-title{gap:7px}.dish-count{font-size:10px;padding:5px 6px}.plan-preview .dish-photo{width:54px;height:54px}.plan-preview .recipe-block{gap:10px}.plan-preview .dish-name{font-size:15px}.plan-preview .meal-ingredients{width:calc(100% + 26px);margin-left:-13px;margin-right:-13px;padding-left:13px;padding-right:13px}.plan-preview .plan-fixed{padding-left:16px;padding-right:16px}}
</style>
