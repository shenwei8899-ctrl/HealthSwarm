<script setup>
import CloudDietFeedback from '../../components/CloudDietFeedback.vue'
import { isMockMode } from '../../services/config.js'
import AppNavBar from '../../components/AppNavBar.vue'
import { computed,ref,watch } from 'vue'
import { nutritionFeedback } from '../../services/nutrition-feedback.js'
import { onShow,onUnload } from '@dcloudio/uni-app'
import { backHome,getProfile,getRecords } from '../../utils/profile.js'
import { confirmedFor,recordsOn,vegetableTrend } from '../../utils/feedback.js'
import { localDate } from '../../utils/meal-state.js'
const advice=ref(null),adviceError=ref(''),adviceBusy=ref(false)
let feedbackVersion=0,disposed=false
onUnload(()=>{disposed=true;feedbackVersion++})
const profile=ref(getProfile()),records=ref(getRecords()),scope=ref('all'),view=ref('当餐'),date=ref(localDate()),days=ref(7),meal=ref('晚餐')
onShow(()=>{if(!isMockMode)return;profile.value=getProfile();records.value=getRecords()})
const scoped=computed(()=>confirmedFor(records.value,scope.value))
const daily=computed(()=>recordsOn(scoped.value,date.value))
const current=computed(()=>daily.value.filter(r=>r.meal===meal.value))
const recordedMeals=computed(()=>new Set(daily.value.map(r=>r.meal)).size)
const missing=computed(()=>['早餐','午餐','晚餐'].filter(m=>!daily.value.some(r=>r.meal===m)))
const trend=computed(()=>vegetableTrend(scoped.value,days.value,new Date(date.value+'T12:00:00+08:00')))
async function refreshAdvice(){
 if(!isMockMode)return;const version=++feedbackVersion;advice.value=null;adviceError.value='';adviceBusy.value=true
 try{const result=await nutritionFeedback(profile.value,records.value,{scope:scope.value,date:date.value,meal:meal.value});if(!disposed&&version===feedbackVersion)advice.value=result}
 catch(e){if(!disposed&&version===feedbackVersion)adviceError.value=e.message||'反馈生成失败，请重试'}
 finally{if(version===feedbackVersion)adviceBusy.value=false}
}
watch([scope,date,meal,records],refreshAdvice,{immediate:true})
function goRecords(){uni.navigateTo({url:'/pages/records/index'})}
</script>
<template>
  <CloudDietFeedback v-if="!isMockMode"/><view v-else class="screen feedback-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">反馈</text><button class="link" @click="goRecords">看记录</button></view></AppNavBar>
    <view class="hero"><text class="eyebrow">让每次记录，都有回应</text><text class="display-title">从记下的餐食，了解日常饮食</text><text>选择成员，查看本人已确认吃过的菜品。</text></view>
    <scroll-view class="scope-tabs" scroll-x><view class="scope-row"><button :class="{active:scope==='all'}" @click="scope='all'">全家</button><button v-for="m in profile.members" :key="m.id" :class="{active:scope===m.id}" @click="scope=m.id">{{m.name}}</button></view></scroll-view>
    <view class="date-row card"><picker mode="date" :value="date" @change="date=$event.detail.value"><text>{{date}} ›</text></picker><text>选择查看日期</text></view>
    <view class="view-tabs"><button v-for="v in ['当餐','当日','近期趋势']" :key="v" :class="{active:view===v}" @click="view=v">{{v}}</button></view>
    <view v-if="view==='当餐'" class="feedback-card card">
      <view class="meal-tabs"><button v-for="m in ['早餐','午餐','晚餐']" :key="m" :class="{active:meal===m}" @click="meal=m">{{m}}</button></view>
      <template v-if="current.length"><text v-if="adviceBusy" class="safe-note">正在分析已确认的饮食记录…</text><view v-if="adviceError"><text class="inline-error">{{adviceError}}</text><button @click="refreshAdvice">重试反馈</button></view><view v-if="advice"><text>{{advice.text}}</text><text class="basis">依据：{{advice.recordIds.length}} 条已保存记录</text></view><text class="section-title">{{meal}}的记录反馈</text><view><text>已确认菜品</text><text>{{current.flatMap(r=>r.dishes||[]).join('、')||'尚未确认具体菜品'}}</text></view><view><text>亮点</text><text>这餐有了可追溯的记录，之后可以一起回顾。</text></view><view><text>可改进处</text><text>照片不能确定隐形用油和准确重量，暂不提供精确营养结论。</text></view><view><text>下一步</text><text>补充真实份量，继续记录下一餐。个体化营养建议待服务接入。</text></view><text class="basis">依据：{{current.length}}条已保存记录 · 示例反馈文案</text></template>
      <template v-else><text class="section-title">这餐还没有记录</text><text class="demo-label">未记录不代表没有进食，不会生成这餐的评价。</text><button class="secondary-button" @click="goRecords">查看饮食记录</button></template>
    </view>
    <view v-else-if="view==='当日'" class="feedback-card card"><text class="section-title">已记录 {{recordedMeals}} 餐</text><view v-for="m in ['早餐','午餐','晚餐']" :key="m"><text>{{m}}</text><text>{{daily.some(r=>r.meal===m)?'已记录，可回顾':'未记录'}}</text></view><text class="basis">缺失：{{missing.join('、')||'无'}}。仅依据当天已记录餐次，不评价全天摄入量。</text></view>
    <view v-else class="feedback-card card"><view class="range-tabs"><button v-for="n in [7,30]" :key="n" :class="{active:days===n}" @click="days=n">近{{n}}天</button></view><text class="section-title">已记录餐次的蔬菜搭配</text><text class="demo-label">截至 {{date}} · 下方数据来自本机已保存记录</text><scroll-view scroll-x><view class="trend-columns"><view v-for="day in trend" :key="day.date" class="trend-day"><text>{{day.ratio===null?'—':Math.round(day.ratio*100)+'%'}}</text><view class="bar-track"><view v-if="day.ratio!==null" class="bar" :style="{height:Math.max(2,day.ratio*100)+'%'}"></view><text v-else class="no-data">无记录</text></view><text>{{day.date.slice(5)}}</text></view></view></scroll-view><text class="basis">比例＝有蔬菜搭配的已记录餐次／当天已记录餐次。无记录日留空，不按 0 统计。菜名匹配仅演示图表，并非专业营养判断。</text></view>
  </view>
</template>
<style scoped>.link{width:75rpx;color:#292a2e;font-size:25rpx;font-weight:500}.hero{display:flex;flex-direction:column;gap:12rpx;margin:42rpx 0 23rpx}.hero .display-title{font-size:43rpx}.hero>text:last-child{color:#6e6e78;font-size:25rpx}.scope-tabs{white-space:nowrap}.scope-tabs .scope-row{display:inline-flex;gap:9rpx}.scope-tabs button,.view-tabs button{padding:13rpx 21rpx;border-radius:16rpx;background:#f0f1f4;color:#6e6e78;font-size:25rpx}.scope-tabs button.active,.view-tabs button.active{background:#292a2e;color:#fff}.view-tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:9rpx;margin:18rpx 0}.empty,.feedback-card{padding:27rpx}.empty{display:flex;flex-direction:column;gap:12rpx;text-align:center}.empty text:first-child{font-size:26rpx;font-weight:500}.empty text:nth-child(2){color:#73837c;font-size:25rpx;line-height:1.6}.empty button{color:#292a2e;font-weight:500}.feedback-card{display:flex;flex-direction:column;gap:17rpx}.feedback-card>view:not(.trend){display:flex;flex-direction:column;gap:6rpx;padding:16rpx;border-radius:18rpx;background:#f1f2e9}.feedback-card>view text:first-child{font-size:25rpx;font-weight:500}.feedback-card>view text:last-child{color:#66776f;font-size:25rpx;line-height:1.55}.basis{padding:17rpx;border-radius:17rpx;background:#f2dfd3;color:#745246;font-size:25rpx;line-height:1.55}.trend{height:180rpx;display:flex;align-items:flex-end;justify-content:space-around;border-bottom:2rpx solid #b9c7bc}.trend view{width:42rpx;border-radius:10rpx 10rpx 0 0;background:#292a2e}.trend view.empty-day{height:10rpx;background:#d6ddd5}.date-row{display:flex;justify-content:space-between;align-items:center;margin-top:20rpx;padding:24rpx;font-size:26rpx}.date-row>text{font-size:25rpx;color:#767680}.meal-tabs,.range-tabs{display:flex;gap:12rpx}.meal-tabs button,.range-tabs button{padding:16rpx 24rpx;background:#f5f5f7;border-radius:16rpx;font-size:25rpx}.meal-tabs .active,.range-tabs .active{background:#292a2e;color:#fff}.feedback-card>view.meal-tabs,.feedback-card>view.range-tabs{flex-direction:row;background:transparent;padding:0}.trend-columns{display:inline-flex;gap:14rpx;padding-bottom:12rpx}.trend-day{width:65rpx;flex-shrink:0;display:flex;flex-direction:column;align-items:center;gap:12rpx;font-size:25rpx;color:#767680}.bar-track{height:160rpx;width:32rpx;display:flex;align-items:flex-end;position:relative;background:#f5f5f7;border-radius:8rpx}.bar{width:100%;background:#292a2e;border-radius:8rpx}.no-data{font-size:16rpx;position:absolute;bottom:0;writing-mode:vertical-rl}.feedback-card .basis{background:#f5f5f7;color:#63636b;font-size:25rpx}.feedback-card>view text:last-child{font-size:25rpx}.feedback-screen .hero>text:last-child{font-size:26rpx}.feedback-screen .scope-tabs button,.feedback-screen .view-tabs button{font-size:25rpx;min-height:76rpx}.feedback-screen .link{font-size:25rpx;width:90rpx}</style>
