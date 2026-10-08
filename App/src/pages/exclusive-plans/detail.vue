<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { computed, ref } from 'vue'
import { onLoad,onShow } from '@dcloudio/uni-app'
import { getProfile,backHome } from '../../utils/profile.js'
import { getExclusivePlan,adaptExclusivePlan } from '../../utils/exclusive-plans.js'
const id=ref('balanced'),profile=ref(getProfile()),showAll=ref(false)
const plan=computed(()=>adaptExclusivePlan(getExclusivePlan(id.value),profile.value))
const firstBatchTotal=computed(()=>(plan.value.estimateCents/100).toFixed(2)),total=computed(()=>(plan.value.totalEstimateCents/100).toFixed(2))
const displayDays=computed(()=>Array.from({length:showAll.value?21:2},(_,i)=>({...plan.value.days[i%plan.value.days.length],day:'第 '+(i+1)+' 天',version:'演示图文菜谱 v2'})))
onLoad(o=>id.value=o.id||'balanced')
onShow(()=>profile.value=getProfile())
function buy(){if(plan.value.blocked.length)return;uni.navigateTo({url:'/pages/exclusive-plans/schedule?id='+plan.value.id})}
</script>

<template>
  <view class="screen detail-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">计划详情</text><text class="pill">21 天</text></view></AppNavBar>
    <view class="detail-head"><text class="eyebrow">AI专属计划 · 测试数据</text><text class="display-title">{{ plan.name }}</text><text>{{ plan.subtitle }}</text></view>
    <view class="section-head"><view><text class="section-title">21 天三餐菜谱</text><text>每天早餐／午餐／晚餐 · 测试菜谱版本</text></view><button @click="showAll=!showAll">{{showAll?'收起':'查看全部21天'}} ›</button></view>
    <scroll-view class="days-scroll" scroll-x :show-scrollbar="false">
      <view class="days-row">
        <view v-for="day in displayDays" :key="day.day" class="day-card card">
          <text class="day-title">{{ day.day }}</text>
          <text class="demo-label">{{day.version}}</text>
          <view v-for="meal in day.meals" :key="meal.type" class="meal-block">
            <text class="meal-type">{{ meal.type }}</text>
            <view><image :src="meal.image" mode="aspectFill" /><view><text>{{ meal.name }}</text><text>{{ meal.minutes }} 分钟</text></view></view>
          </view>
        </view>
      </view>
    </scroll-view>
    <view class="section-head products-head"><view><text class="section-title">配套食材选购</text><text>首批所需食材已准备好</text></view></view>
    <view class="plan-products">
      <view v-for="item in plan.products" :key="item.name" class="plan-product">
        <image :src="item.image" mode="aspectFill" /><view><text>{{ item.name }}</text><text>× {{ item.count }}</text></view><text>¥{{ (item.cents / 100).toFixed(2) }}</text>
      </view>
    </view>
    <view class="price-summary card"><view><text>首批三餐食材预估价</text><text>¥{{firstBatchTotal}}</text></view><view><text>21天计划预计总价</text><text>¥{{total}}</text></view><text>测试金额 · 结算前必须按 21 批实际 SKU、库存和费用重新报价。</text></view>
    <view class="bottom-bar"><view><text>21天总价预估</text><text>¥{{ total }}</text></view><button @click="buy" :disabled="plan.blocked.length>0">下一步</button></view>

    <view class="check-status card"><text class="section-title">饮食安全检查 · 演示</text><text>{{plan.blocked.length?plan.blocked.join('；'):'已避开已知冲突'}}</text><text>{{plan.fixturePlans.some(day=>day.some(p=>p.general))?'资料尚未完整填写，当前仅提供通用建议，不代表完成个体化适配。':'已结合成员档案调整菜谱及关联食材。'}}</text><button v-if="plan.blocked.length" class="secondary-button" @click="uni.navigateTo({url:'/pages/profile/index'})">补充档案</button></view>
  </view>
</template>

<style scoped>
.check-status{display:flex;flex-direction:column;gap:16rpx;padding:26rpx;margin-top:24rpx;font-size:23rpx;line-height:1.7}.bottom-bar button[disabled]{opacity:.4}
.detail-screen { padding-bottom: calc(env(safe-area-inset-bottom) + 170rpx); overflow: visible; }.detail-head { margin-top: 46rpx; }.detail-head .display-title { display: block; font-size: 50rpx; }.detail-head > text:last-child { display: block; margin-top: 16rpx; color: #687a72; font-size: 23rpx; line-height: 1.65; }.section-head { display: flex; align-items: flex-end; justify-content: space-between; margin: 46rpx 0 20rpx; }.section-head > view { display: flex; flex-direction: column; gap: 8rpx; }.section-head > view > text:last-child { color: #75867e; font-size: 20rpx; }.section-head > button { color: #246b50; font-size: 22rpx; }.days-scroll { width: calc(100% + 30rpx); white-space: nowrap; }.days-row { display: inline-flex; gap: 18rpx; padding-right: 30rpx; }.day-card { width: 430rpx; display: inline-flex; flex-direction: column; padding: 24rpx; white-space: normal; }.day-title { padding-bottom: 18rpx; color: #1d1d1f; font-family:inherit; font-size: 31rpx; font-weight: 800; border-bottom: 1rpx solid rgba(24,54,46,.1); }.meal-block { margin-top: 18rpx; }.meal-type { display: block; margin-bottom: 10rpx; color: #315549; font-size: 21rpx; font-weight: 700; }.meal-block > view { display: flex; align-items: center; gap: 14rpx; }.meal-block image { width: 104rpx; height: 86rpx; flex: 0 0 auto; border-radius: 18rpx; }.meal-block > view > view { display: flex; flex-direction: column; gap: 8rpx; }.meal-block > view > view text:first-child { color: #233f35; font-size: 22rpx; font-weight: 700; line-height: 1.4; }.meal-block > view > view text:last-child { color: #849088; font-size: 19rpx; }.products-head { margin-top: 54rpx; }.plan-products { display: flex; flex-direction: column; gap: 10rpx; }.plan-product { display: flex; align-items: center; gap: 18rpx; padding: 16rpx 0; border-bottom: 1rpx solid rgba(24,54,46,.08); }.plan-product image { width: 116rpx; height: 98rpx; flex: 0 0 auto; border-radius: 20rpx; }.plan-product > view { flex: 1; display: flex; flex-direction: column; gap: 8rpx; }.plan-product > view text:first-child { color: #223f35; font-size: 24rpx; font-weight: 700; }.plan-product > view text:last-child { color: #7d8c85; font-size: 20rpx; }.plan-product > text { color: #9c4e38; font-size: 27rpx; font-weight: 800; }
.bottom-bar { position: fixed; z-index: 10; left: 0; right: 0; bottom: 0; display: flex; align-items: center; gap: 24rpx; padding: 22rpx 30rpx calc(env(safe-area-inset-bottom) + 22rpx); background: rgba(255,253,247,.97); border-top: 1rpx solid rgba(24,54,46,.08); }.bottom-bar > view { width: 190rpx; display: flex; flex-direction: column; gap: 6rpx; color: #71827a; font-size: 18rpx; }.bottom-bar > view text:last-child { color: #1d1d1f; font-size: 32rpx; font-weight: 800; }.bottom-bar > button { flex: 1; min-height: 86rpx; border-radius: 26rpx; background: #246b50; color: white; font-size: 28rpx; font-weight: 700; }
.price-summary{margin-top:22rpx;padding:22rpx}.price-summary>view{display:flex;justify-content:space-between;padding:12rpx 0;border-bottom:1rpx solid rgba(24,54,46,.08);font-size:20rpx}.price-summary>view text:last-child{color:#a34c37;font-size:27rpx;font-weight:900}.price-summary>text{display:block;margin-top:13rpx;color:#7c655a;font-size:17rpx;line-height:1.5}.conflict-box,.resolved-box{display:flex;flex-direction:column;gap:8rpx;margin-top:16rpx;padding:17rpx;border-radius:17rpx;background:#f1d6cc;color:#824635}.conflict-box>text:first-child,.resolved-box>text:first-child{font-size:20rpx;font-weight:900}.conflict-box>text:not(:first-child),.resolved-box>text:not(:first-child){font-size:18rpx;line-height:1.5}.conflict-box button{min-height:60rpx;margin-top:6rpx;padding:8rpx 12rpx;border:1rpx solid #b36b56;border-radius:15rpx;background:#fff9f5;color:#814432;font-size:17rpx;font-weight:800}.resolved-box{background:#e2edd8;color:#315846}.sheet-actions .primary-button[disabled]{opacity:.45}
.allergy-mask { z-index: 70; align-items: center; padding: 30rpx; }.allergy-sheet { border-radius: 34rpx; }.allergy-sheet > .section-title { display: block; text-align: center; }.warning { display: flex; gap: 15rpx; margin-top: 26rpx; padding: 20rpx; border-radius: 18rpx; background: #fae5df; color: #a64a38; font-size: 21rpx; line-height: 1.55; }.warning text:first-child { width: 34rpx; height: 34rpx; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; border-radius: 50%; background: #d55742; color: white; font-weight: 800; }.profile-allergy { display: flex; align-items: center; justify-content: space-between; margin-top: 18rpx; padding: 18rpx; border-radius: 18rpx; background: #e9f1e4; color: #325749; font-size: 21rpx; }.profile-allergy text:last-child { font-weight: 700; }.allergen-title { display: block; margin: 26rpx 0 14rpx; color: #243e35; font-size: 23rpx; font-weight: 700; }.allergen-list { display: flex; flex-direction: column; gap: 10rpx; }.allergen-list > view { display: flex; gap: 18rpx; padding: 17rpx 20rpx; border-radius: 16rpx; background: #f0f1ec; color: #5e6e67; font-size: 21rpx; }.allergen-list > view text:last-child { padding: 3rpx 8rpx; border: 1rpx solid #aab3ac; background: white; color: #384d44; }.replace-link { width: 100%; min-height: 68rpx; margin-top: 18rpx !important; color: #61776d; font-size: 22rpx; }.sheet-actions { display: grid; grid-template-columns: 1fr 1.4fr; gap: 14rpx; margin-top: 4rpx; }.sheet-actions .primary-button,.sheet-actions .secondary-button { min-height: 84rpx; margin: 0; font-size: 23rpx; }
</style>
