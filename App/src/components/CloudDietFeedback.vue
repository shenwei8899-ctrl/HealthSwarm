<script setup>
import { computed,ref } from 'vue'
import { onShow,onHide,onUnload } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'
import { request } from '../services/request.js'
import { storageContext } from '../services/storage.js'
import { mealDay,mealLabels,feedbackUrl } from '../services/cloud-meals.js'
const members=ref([]),scope=ref('all'),view=ref('当餐'),date=ref(mealDay(new Date().toISOString())),days=ref(7),meal=ref('dinner'),records=ref([]),analyses=ref([]),periods=ref([]),busy=ref(false),error=ref('')
const current=computed(()=>records.value.filter(r=>mealDay(r.snapshot.meal.eaten_at)===date.value&&r.snapshot.meal.meal_type===meal.value&&(scope.value==='all'||scope.value===r.member_id)))
const name=id=>{const m=members.value.find(m=>m.id===id);const label=m?.display_name||m?.name||'';return label&&!/^微信用户[_-]/.test(label)?label:(m?.relationship_label==='本人'||m?.is_owner?'我':m?.relationship_label||'家庭成员')}
const dayLabel=computed(()=>{const match=/^\d{4}-(\d{2})-(\d{2})$/.exec(date.value);return match?Number(match[1])+'月'+Number(match[2])+'日':date.value})
const isToday=computed(()=>date.value===mealDay(new Date().toISOString()))
const periodEmpty=computed(()=>!periods.value.some(p=>p.records?.length))
function capture(){uni.navigateTo({url:'/pages/scan/index'+(view.value==='当餐'?'?meal='+encodeURIComponent(meal.value):'')})}
const findingsFor=r=>analyses.value.find(a=>a.source?.record_id===r.id)?.findings||[]
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
<template>
 <view class="screen df40">
  <AppNavBar title="饮食反馈"><template #left><button class="icon-button" aria-label="返回" @click="uni.navigateBack()">‹</button></template></AppNavBar>
  <view class="df39"><text class="df34">每一餐，都有回应</text><text class="df15">从真实记录里，发现饮食的小变化</text></view>
  <view class="df24">
   <view class="df13"><picker mode="date" :value="date" :disabled="busy" @change="change('date',$event.detail.value)"><view class="df37"><view class="df12"><AppIcon name="calendar" :size="34"/></view><view><view class="df7"><text>{{dayLabel}}</text><text class="df17">⌄</text></view><text class="df10">{{isToday?'今天的饮食反馈':'这一天的饮食反馈'}}</text></view></view></picker></view>
   <scroll-view scroll-x class="df19" :show-scrollbar="false"><view class="df9"><button :class="{chosen:scope==='all'}" :aria-pressed="scope==='all'" :disabled="busy" @click="change('scope','all')">全家</button><button v-for="m in members" :key="m.id" :class="{chosen:scope===m.id}" :aria-pressed="scope===m.id" :disabled="busy" @click="change('scope',m.id)"><text>{{name(m.id)}}</text></button></view></scroll-view>
  </view>
  <view class="df35"><button v-for="v in ['当餐','当日','近期趋势']" :key="v" :class="{chosen:view===v}" :aria-pressed="view===v" :disabled="busy" @click="change('view',v)">{{v}}</button></view>
  <view v-if="view==='当餐'" class="df31"><button v-for="(label,key) in mealLabels" :key="key" :class="{chosen:meal===key}" :aria-pressed="meal===key" :disabled="busy" @click="change('meal',key)">{{label}}</button></view>
  <view v-if="view==='近期趋势'" class="df26"><text>回顾一段时间的饮食</text><view><button v-for="n in [7,30]" :key="n" :class="{chosen:days===n}"  :disabled="busy" @click="change('days',n)">近{{n}}天</button></view></view>
  <view v-if="busy" class="df33" role="status"><view class="df18"/><text class="df5">正在整理饮食记录…</text><text class="df16">稍等一下，一起看看吃得怎么样</text></view>
  <view v-else-if="error" class="df33" role="alert"><text class="df5">暂时没能读到反馈</text><text class="df16">{{error}}</text><button class="df20" @click="load">重新读取 <text>↻</text></button></view>
  <template v-else>
   <template v-if="view==='当餐'">
    <view v-for="r in current" :key="r.id" class="df36">
     <view class="df1"><view class="df11"><image :src="'/static/journal/'+r.snapshot.meal.meal_type+'.png'" mode="aspectFit" aria-hidden="true"/></view><view><text class="df6">{{name(r.member_id)}}的{{mealLabels[r.snapshot.meal.meal_type]}}</text><text class="df16">已确认的饮食记录</text></view></view>
     <text class="df22">{{r.snapshot.meal.items.filter(i=>!i.excluded).map(i=>i.name).join('、')}}</text>
     <view v-if="findingsFor(r).length" class="df14"><text class="df30">这一餐的小反馈</text><text v-for="finding in findingsFor(r)" :key="finding">{{finding}}</text></view>
     <view class="df4"><text>依据已确认记录 · v{{r.source_version}}</text><button @click="uni.navigateTo({url:feedbackUrl(r.member_id,r)})">聊聊这一餐 <text>→</text></button></view>
    </view>
   </template>
   <template v-else-if="!periodEmpty">
    <view v-for="period in periods" :key="period.member_id" class="df36">
     <view class="df0"><text class="df6">{{name(period.member_id)}}的饮食回顾</text><text class="df28">已记录 {{period.records.length}} 餐</text></view>
     <text class="df16 df27">{{period.window.start_date}} — {{period.window.end_date}}</text>
     <view class="df38"><view v-for="day in period.days" :key="day.date" class="df42"><view><text>{{day.date}}</text><text class="df16">{{day.record_count?day.record_count+'餐已记录':'未记录'}}</text></view><text class="df23">{{day.nutrition.energy_kcal.recorded_total??'未知'}}<text v-if="day.nutrition.energy_kcal.recorded_total!=null"> kcal</text></text></view></view>
     <view v-if="period.findings?.length||period.trend?.reason" class="df14"><text class="df30">{{view==='当日'?'今天的小反馈':'这段时间的小发现'}}</text><text v-for="finding in period.findings" :key="finding">{{finding}}</text><text v-if="period.trend">{{period.trend.reason}}</text></view>
    </view>
   </template>
   <view v-if="view==='当餐'?!current.length:periodEmpty" class="df33 df29">
    <view class="df3"><image :src="'/static/journal/'+(view==='当餐'?meal:'lunch')+'.png'" mode="aspectFit" aria-hidden="true"/></view>
    <text class="df5">{{view==='当餐'?'这顿'+mealLabels[meal]+'，还没记下':view==='当日'?'这一天，还没有饮食记录':'这段时间，还没有饮食记录'}}</text>
    <text class="df16">记下吃过的食物，再一起看看搭配</text>
    <button class="df20" @click="capture">去记一餐 <text>→</text></button>
    <text class="df8">未记录不代表没有进食，不生成饮食评价</text>
   </view>
  </template>

 </view>
</template>
<style>
.df40{background-color:#f5f6fa;background-image:radial-gradient(ellipse at 0% 0%,rgba(125,174,255,.44),transparent 70%),radial-gradient(ellipse at 100% 0%,rgba(206,178,245,.38),transparent 76%);background-size:100% 490rpx;background-repeat:no-repeat;color:#35343f;font-family:"PingFang SC","Microsoft YaHei",sans-serif}
.df39{padding:28rpx 4rpx 30rpx}.df34{font-size:44rpx;line-height:1.45;letter-spacing:1rpx}.df15{margin-top:12rpx;font-size:25rpx;color:#74717f;line-height:1.6}
.df24{padding:24rpx 26rpx 0;border:1px solid rgba(255,255,255,.9);border-radius:32rpx;background:linear-gradient(180deg,rgba(255,255,255,.45),rgba(255,255,255,.96));}.df13{display:flex;justify-content:space-between;gap:12rpx;padding-bottom:22rpx}.df13 picker{flex:1;min-width:0}.df37{display:flex;gap:18rpx;min-height:86rpx}.df12{display:flex;width:74rpx;height:78rpx;background:#eeeaf7;border-radius:22rpx;color:#7e708e}.df7{display:flex;gap:14rpx;font-size:34rpx;white-space:nowrap;line-height:1.4}.df17{font-size:26rpx;color:#8e879a}.df10{margin-top:6rpx;font-size:23rpx;color:#74717f}
.df19{width:100%;white-space:nowrap;border-top:1px solid rgba(226,222,237,.55)}.df9{display:inline-flex;min-width:100%;gap:12rpx;padding:14rpx 0}.df9 button{display:flex;min-height:80rpx;min-width:94rpx;max-width:240rpx;padding:12rpx 24rpx;border-radius:22rpx;color:#74717f;font-size:25rpx}.df9 button text{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.df9 .chosen{background:#eeeaf7;color:#514568}
.df35{display:flex;gap:40rpx;border-bottom:1px solid #e8e6ef;margin:22rpx 4rpx 22rpx}.df35 button{position:relative;min-height:96rpx;padding:18rpx 2rpx 22rpx;color:#827c8e;font-size:29rpx}.df35 .chosen{color:#35343f}.df35 .chosen:after{position:absolute;inset:auto auto -1px 50%;width:36rpx;height:5rpx;transform:translateX(-50%);background:#8d99c8}
.df31{display:flex;gap:14rpx;margin-bottom:24rpx}.df31 button{flex:1;display:flex;min-height:80rpx;border:1px solid transparent;border-radius:22rpx;font-size:26rpx;color:#827c8e}.df31 .chosen{background:#fff;border-color:#e6e3f0;color:#64577d;}
.df33,.df36{border:1px solid rgba(255,255,255,.92);border-radius:32rpx;background:linear-gradient(180deg,rgba(255,255,255,.66),#fff);}.df33{display:flex;flex-direction:column;padding:48rpx 24rpx 34rpx;text-align:center;gap:14rpx;}.df5{font-size:32rpx}.df16{font-size:24rpx;color:#827c8e;line-height:1.65}.df3{position:relative;display:flex;width:168rpx;height:156rpx;margin-bottom:8rpx}.df3 image{width:132rpx;height:132rpx}.df20{display:flex;justify-content:space-between;gap:40rpx;padding:18rpx 30rpx;margin-top:18rpx;border-radius:24rpx;background:linear-gradient(105deg,#ddecff,#bbcff3);font-size:27rpx;color:#365e94}.df8{font-size:21rpx;line-height:1.6;color:#96909e;margin-top:14rpx}.df18{width:52rpx;height:52rpx;border:3rpx solid #e8e6f2;border-top-color:#9caed4;border-radius:50%;margin-bottom:18rpx;animation:df41 1s linear infinite}@keyframes df41{to{transform:rotate(360deg)}}
.df36{padding:28rpx;margin-bottom:22rpx}.df1{display:flex;gap:18rpx}.df6{font-size:30rpx}.df11{width:76rpx;height:76rpx;background:#f4f2f8;border-radius:22rpx;display:flex}.df11 image{width:66rpx;height:66rpx}.df22{padding:24rpx 0;font-size:28rpx;line-height:1.75}.df14{display:flex;flex-direction:column;gap:12rpx;padding:22rpx 24rpx;background:#f6f5fa;border-radius:22rpx;font-size:26rpx;line-height:1.75}.df30{font-size:23rpx;color:#8c829d}.df4{display:flex;justify-content:space-between;gap:12rpx;margin-top:20rpx;padding-top:10rpx;border-top:1px solid #eeecf3}.df4>text{font-size:21rpx;color:#96909e}.df4 button{display:flex;gap:10rpx;color:#6283b9;font-size:25rpx}.df26{display:flex;justify-content:space-between;gap:12rpx;margin-bottom:22rpx}.df26>text{font-size:23rpx;color:#827c8e}.df26>view{display:flex;gap:8rpx}.df26 button{min-height:80rpx;padding:16rpx 22rpx;border-radius:22rpx;font-size:25rpx;color:#827c8e}.df26 .chosen{background:#eeeaf7;color:#514568}.df0{display:flex;justify-content:space-between;gap:12rpx;flex-wrap:wrap}.df28{font-size:23rpx;color:#827c8e}.df27{margin-top:10rpx}.df38{margin:22rpx 0}.df42{display:flex;justify-content:space-between;gap:12rpx;border-top:1px solid #eeecf3;padding:18rpx 0;font-size:26rpx}.df23{white-space:nowrap;font-size:28rpx;color:#64577d;}.df23>text{font-size:21rpx;color:#96909e}

@media(prefers-reduced-motion:reduce){.df18{animation:none}}
.df34,.df15,.df10,.df9 button text,.df5,.df16,.df6,.df22,.df42>view>text{display:block}.df12,.df9 button,.df11,.df4 button{flex:none}.df34,.df7,.df9 .chosen,.df35 .chosen,.df5,.df6{font-weight:500}.df16,.df6,.df22,.df14{overflow-wrap:anywhere}.df5,.df6{line-height:1.5}.df20,.df4 button{min-height:88rpx}.df13,.df37,.df12,.df7,.df9 button,.df31 button,.df33,.df3,.df20,.df1,.df11,.df4,.df4 button,.df26,.df0,.df42{align-items:center}.df12,.df9 button,.df31 button,.df33,.df3,.df11{justify-content:center}</style>
