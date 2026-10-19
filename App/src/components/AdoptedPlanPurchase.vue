<script setup>
import { computed, ref, watch } from 'vue'
import { onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import CommerceAccess from './CommerceAccess.vue'
import { commerce, commerceContext } from '../services/commerce.js'
import { request } from '../services/request.js'
import { createMealPurchaseFlow } from '../services/meal-purchase-flow.js'

const state = ref({ members: [], missing: [] }), inventoryConfirmed = ref(false), pantry = ref({})
const flow = createMealPurchaseFlow({ send: request, commerce, context: commerceContext, onChange: value => { state.value = value } })
const configurationNotice = computed(() => state.value.missing.some(key => key !== 'HEALTH_COMMERCE_INGREDIENT_MAP')
  ? '采购服务连接尚未配置完整，当前不能生成商品采购清单。'
  : '食品与商品映射、采购重量换算依据尚未配置，当前不能生成商品采购清单。')
function load() {
  inventoryConfirmed.value = false; pantry.value = {};
  const now = new Date(Date.now() + 8 * 3600000)
  flow.open(now.toISOString().slice(0, 10))
}
function choose(memberId, date) { inventoryConfirmed.value = false; pantry.value = {}; flow.choose(memberId, date) }
function prepare() {
  const inventory = (state.value.requirements?.items || []).filter(item => pantry.value[item.food_id + ":" + item.cooking_state] !== '' && pantry.value[item.food_id + ":" + item.cooking_state] != null)
    .map(item => ({ food_id: item.food_id, cooking_state: item.cooking_state, edible_grams: String(pantry.value[item.food_id + ":" + item.cooking_state]) }))
  flow.prepare(inventory)
}
watch(() => commerceContext(), () => { flow.reset(); inventoryConfirmed.value = false; pantry.value = {} })
onHide(() => flow.reset())
onUnload(() => flow.reset())
</script>

<template>
  <CommerceAccess @ready="load">
    <view class="screen purchase-page">
      <AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack()">‹</button><text class="nav-title">餐单采购</text><button class="text-button" :disabled="state.busy" @click="load">刷新</button></view></AppNavBar>
      <view class="page-heading"><text class="display-title">从餐单到食材</text><text class="subtitle">只读取服务器已批准并采用的餐单。演示数据不会用于真实采购。</text></view>
      <view v-if="state.missing.length" class="card"><text class="section-title">采购服务未就绪</text><text class="helper">{{ configurationNotice }}</text></view>
      <view class="card">
        <text class="section-title">选择健康成员与餐单日期</text>
        <picker v-if="state.members.length" :range="state.members" range-key="name" :disabled="state.busy" @change="choose(state.members[Number($event.detail.value)].id, state.date)"><view class="field-input">{{ state.members.find(row => row.id === state.memberId)?.name || '选择健康成员' }} ›</view></picker>
        <picker mode="date" :value="state.date" :disabled="state.busy" @change="choose(state.memberId, $event.detail.value)"><view class="field-input">{{ state.date || '选择日期' }} ›</view></picker>
        <text v-if="state.notice" class="helper">{{ state.notice }}</text>
      </view>
      <view v-if="state.plan" class="card">
        <text class="section-title">已采用餐单 · v{{ state.plan.plan_version }}</text>
        <text class="helper">采用编号：{{ state.plan.adoption_id }}</text>
        <view v-for="item in state.requirements?.items || []" :key="item.food_id + item.cooking_state" class="ingredient">
          <text>{{ item.name }} · {{ item.cooking_state }}</text><text class="helper">餐单需要 {{ item.required_grams }} 克（可食量）</text>
          <input v-model="pantry[item.food_id + ':' + item.cooking_state]" type="digit" class="field-input" :disabled="state.busy || !!state.package" placeholder="同状态可食库存（克），留空表示无库存" />
        </view>
        <label class="confirm-row"><checkbox :checked="inventoryConfirmed" :disabled="state.busy || !!state.package" @click="inventoryConfirmed = !inventoryConfirmed" /><text>我已核对库存；留空的食材按无库存采购</text></label>
        <button class="primary-button" :disabled="state.busy || !inventoryConfirmed || !!state.package || state.missing.length > 0" @click="prepare">生成商品采购预览</button>
      </view>
      <view v-if="state.package" class="card">
        <text class="section-title">商品采购预览</text>
        <view v-for="item in state.package.items" :key="item.id || item.sku_id" class="ingredient"><text>{{ item.product_snapshot?.title || item.product_snapshot?.name || '商品 ' + item.sku_id }} × {{ item.quantity }}</text></view>
        <text class="helper">预估 ¥{{ (state.package.total_amount_cent / 100).toFixed(2) }}，最终金额由购物车结算重新核价。</text>
        <button v-if="!state.list" class="primary-button" :disabled="state.busy" @click="flow.confirm">确认并生成采购清单</button>
      </view>
      <view v-if="state.list" class="card">
        <text class="section-title">采购清单已保存</text><text class="helper">{{ state.list.purchase_list_sn }} · v{{ state.list.version }}</text>
        <button class="primary-button" :disabled="state.busy || state.cartAdded" @click="flow.add">{{ state.cartAdded ? '已加入购物车' : '加入购物车' }}</button>
        <button v-if="state.cartAdded" class="secondary-button" @click="uni.navigateTo({ url: '/pages/shop/index?commerce=1' })">核对购物车、地址并下单</button>
      </view>
      <text v-if="state.error" class="error-text" role="alert">{{ state.error }}</text>
      <button class="secondary-button" @click="uni.navigateTo({ url: '/pages/orders/index' })">查看订单与支付状态</button>
    </view>
  </CommerceAccess>
</template>

<style scoped>
.purchase-page{padding-bottom:36px}.card{margin-bottom:16px}.section-title,.helper{display:block}.helper{margin:10px 0;line-height:1.6;overflow-wrap:anywhere}.ingredient{padding:12px 0;border-bottom:1px solid #e5e5eb}.confirm-row{display:flex;align-items:center;margin:18px 0;line-height:1.5}.error-text{display:block;margin:16px;color:#a33}.field-input{margin-top:12px}
</style>
