<script setup>
import { computed,ref } from 'vue'
import { onShow,onHide,onUnload } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import { request } from '../services/request.js'
import { storageContext } from '../services/storage.js'
import { mealDay,mealLabels,feedbackUrl } from '../services/cloud-meals.js'
const members=ref([]),scope=ref('all'),view=ref('当餐'),date=ref(mealDay(new Date().toISOString())),days=ref(7),meal=ref('dinner'),records=ref([]),analyses=ref([]),periods=ref([]),busy=ref(false),error=ref('')
const current=computed(()=>records.value.filter(r=>mealDay(r.snapshot.meal.eaten_at)===date.value&&r.snapshot.meal.meal_type===meal.value&&(scope.value==='all'||scope.value===r.member_id)))
const name=id=>{const m=members.value.find(m=>m.id===id);return m?.display_name||m?.name||m?.relationship_label||'成员'}
let epoch=0
async function load(){if(busy.value)return;const mine=++epoch,context=storageContext(),valid=()=>mine===epoch&&context===storageContext();busy.value=true;error.value='';records.value=[];analyses.value=[];periods.value=[];try{
 if(!members.value.length){const {data}=await request({path:'/api/health/v1/members'});if(!valid())return;members.value=data.filter(m=>m.scopes?.includes('diet_edit'))}
 for(const m of members.value.filter(m=>scope.value==='all'||m.id===scope.value)){
  if(view.value==='当餐'){
   const rows=[],seen=new Set();let offset=0
   while(true){
    const {data}=await request({path:`/api/health/v1/members/${m.id}/diet-logs/page?limit=50&offset=${offset}`})
    if(!valid())return
    if(!Array.isArray(data.records))throw new Error('饮食记录返回不完整，请重新读取')
    for(const r of data.records){
     if(!seen.has(r.id)&&mealDay(r.snapshot.meal.eaten_at)===date.value&&r.snapshot.meal.meal_type===meal.value){rows.push(r);seen.add(r.id)}
    }
    if(data.next_offset===null)break
    if(!Number.isInteger(data.next_offset)||data.next_offset<=offset)throw new Error('记录分页未推进，请重新读取')
    offset=data.next_offset
   }
   records.value.push(...rows.map(r=>({...r,member_id:m.id})))
   for(const r of rows){const value=(await request({path:`/api/health/v1/members/${m.id}/diet-analysis`,method:'POST',data:{record_id:r.id,source_version:r.source_version}})).data;if(!valid())return;analyses.value.push(value)}
  }
  else{const {data}=await request({path:`/api/health/v1/members/${m.id}/diet-period-analysis`,method:'POST',data:{period_days:view.value==='当日'?1:days.value,end_date:date.value}});if(!valid())return;periods.value.push(data)}
 }
 }catch(e){if(mine===epoch){if(context!==storageContext()||[401,403,404,410].includes(Number(e.code))){hide();error.value='当前授权或来源已变化，请重新读取。'}else error.value=e.message}}finally{if(mine===epoch)busy.value=false}}
function change(key,value){if(busy.value)return;if(key==='scope')scope.value=value;else if(key==='view')view.value=value;else if(key==='date')date.value=value;else if(key==='days')days.value=value;else meal.value=value;void load()}
function hide(){epoch++;members.value=[];records.value=[];analyses.value=[];periods.value=[];busy.value=false;error.value=''}
onShow(load);onHide(hide);onUnload(hide)
</script>
<template><view class="screen feedback-screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack()">‹</button><text class="nav-title">反馈</text><button class="link" @click="uni.navigateTo({url:'/pages/records/index'})">看记录</button></view></AppNavBar><view class="hero"><text class="eyebrow">让每次记录，都有回应</text><text class="display-title">从记下的餐食，了解日常饮食</text><text>选择成员，回顾已确认的真实餐次。</text></view><scroll-view scroll-x class="scope-tabs"><view class="scope-row"><button :class="{active:scope==='all'}" :disabled="busy" @click="change('scope','all')">全家</button><button v-for="m in members" :key="m.id" :class="{active:scope===m.id}" :disabled="busy" @click="change('scope',m.id)">{{name(m.id)}}</button></view></scroll-view><view class="card date-row"><picker mode="date" :value="date" :disabled="busy" @change="change('date',$event.detail.value)">{{date}} ›</picker><text>选择查看日期</text></view><view class="view-tabs"><button v-for="v in ['当餐','当日','近期趋势']" :key="v" :class="{active:view===v}" :disabled="busy" @click="change('view',v)">{{v}}</button></view><text v-if="busy" class="safe-note">正在核对已保存记录…</text><text v-if="error" class="inline-error">{{error}}</text><button v-if="error" class="secondary-button" :disabled="busy" @click="load">重新读取</button><template v-if="view==='当餐'"><view class="meal-tabs"><button v-for="(label,key) in mealLabels" :key="key" :class="{active:meal===key}" :disabled="busy" @click="change('meal',key)">{{label}}</button></view><view v-for="r in current" :key="r.id" class="card feedback-card"><text class="section-title">{{name(r.member_id)}} · {{mealLabels[r.snapshot.meal.meal_type]}}</text><text>{{r.snapshot.meal.items.filter(i=>!i.excluded).map(i=>i.name).join('、')}}</text><text v-for="finding in analyses.find(a=>a.source?.record_id===r.id)?.findings||[]" :key="finding">{{finding}}</text><text class="basis">依据：这条已确认记录 v{{r.source_version}}</text><button class="secondary-button" @click="uni.navigateTo({url:feedbackUrl(r.member_id,r)})">聊聊这一餐</button></view><view v-if="!busy&&!error&&!current.length" class="card feedback-card"><text class="section-title">这餐还没有记录</text><text>未记录不代表没有进食，不生成这餐评价。</text></view></template><template v-else><view v-if="view==='近期趋势'" class="range-tabs"><button v-for="n in [7,30]" :key="n" :class="{active:days===n}" :disabled="busy" @click="change('days',n)">近{{n}}天</button></view><view v-for="period in periods" :key="period.member_id" class="card feedback-card"><text class="section-title">{{name(period.member_id)}} · 已记录{{period.records.length}}餐</text><text>{{period.window.start_date}} — {{period.window.end_date}}</text><view v-for="day in period.days" :key="day.date"><text>{{day.date}} · {{day.record_count?day.record_count+'餐':'未记录'}}</text><text>{{day.nutrition.energy_kcal.recorded_total??'未知'}} kcal</text></view><text v-for="finding in period.findings" :key="finding" class="basis">{{finding}}</text><text v-if="period.trend" class="basis">{{period.trend.reason}}</text></view></template></view></template>
<style scoped>.hero{display:flex;flex-direction:column;gap:14rpx;margin:40rpx 0 24rpx}.display-title{font-size:43rpx}.hero>text:last-child{font-size:26rpx;color:#6d7d76}.scope-row,.meal-tabs,.range-tabs{display:flex;gap:12rpx}.scope-tabs{white-space:nowrap}.scope-row{display:inline-flex}.scope-row button,.view-tabs button,.meal-tabs button,.range-tabs button{padding:16rpx 24rpx;border-radius:16rpx;background:#eef0e8;font-size:25rpx;flex-shrink:0}.scope-row .active,.view-tabs .active,.meal-tabs .active,.range-tabs .active{background:#246b50;color:#fff}.view-tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:10rpx;margin:20rpx 0}.feedback-card{display:flex;flex-direction:column;gap:18rpx;padding:28rpx;margin:24rpx 0;font-size:27rpx;line-height:1.7}.feedback-card>view{display:flex;justify-content:space-between;gap:20rpx;border-bottom:1px solid #ebebef;padding:14rpx 0}.date-row{display:flex;justify-content:space-between;padding:24rpx;margin-top:20rpx;font-size:26rpx}.date-row>text,.basis{color:#767680;font-size:24rpx}.link{font-size:25rpx;color:#246b50}</style>
