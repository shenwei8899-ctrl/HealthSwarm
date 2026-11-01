<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
import AppIcon from './AppIcon.vue'
import { computed,ref } from 'vue'
import { onShow,onHide,onUnload } from '@dcloudio/uni-app'
import { request } from '../services/request.js'
import { sessionRevision } from '../services/session.js'
import { scopedStorage } from '../services/storage.js'
import { newHealthRequestId } from '../services/health-task-flow.js'
import { mealDay,mealLabels,readDietRecord,feedbackUrl,portionNote } from '../services/cloud-meals.js'
import { mealInput } from '../services/health-meal-input.js'
import HealthMealEditor from './HealthMealEditor.vue'
const props=defineProps({detailId:String,memberId:String})
const members=ref([]),records=ref([]),scope=ref('all'),date=ref(mealDay(new Date().toISOString())),busy=ref(false),error=ref(''),detail=ref(null),editing=ref(false),meal=ref(null),reason=ref(''),next=ref({}),pending=ref(null),recipes=ref([])
const visible=computed(()=>records.value.filter(r=>mealDay(r.snapshot.meal.eaten_at)===date.value&&(scope.value==='all'||r.member_id===scope.value)))
const recordedMeals=computed(()=>Object.keys(mealLabels).filter(key=>visible.value.some(r=>r.snapshot.meal.meal_type===key)).length)
const today=computed(()=>date.value===mealDay(new Date().toISOString()))
function capture(key){uni.navigateTo({url:'/pages/scan/index'+(key?'?meal='+encodeURIComponent(key):'')})}
let epoch=0
const name=id=>{const m=members.value.find(m=>m.id===id);return m?.display_name||m?.name||m?.relationship_label||'成员'}
function hide(){epoch++;members.value=[];records.value=[];detail.value=null;meal.value=null;editing.value=false;busy.value=false;error.value='';pending.value=null;next.value={};recipes.value=[];scope.value='all'}
function failure(e,mine,rev){if(mine!==epoch)return;if(rev!==sessionRevision()||[401,403,404,410].includes(Number(e.code))||e.code==='SESSION_CHANGED'){hide();error.value='当前成员授权或记录来源已变化，请重新读取。'}else error.value=e.message}
async function load(more=false){if(busy.value)return;const mine=++epoch,rev=sessionRevision(),current=()=>mine===epoch&&rev===sessionRevision();busy.value=true;error.value='';try{
 if(!members.value.length){const {data}=await request({path:'/api/health/v1/members'});if(!current())return;members.value=data.filter(m=>m.scopes?.includes('diet_edit'));if(props.memberId&&!members.value.some(m=>m.id===props.memberId))throw new Error('该成员当前未授权读取饮食记录');if(props.memberId)scope.value=props.memberId}
 if(!more){records.value=[];next.value={};recipes.value=[]}
 const selected=scope.value==='all'?members.value:members.value.filter(m=>m.id===scope.value)
 for(const m of selected){const offset=more?next.value[m.id]:0;if(offset==null&&more)continue;const {data}=await request({path:`/api/health/v1/members/${m.id}/diet-logs/page?limit=50&offset=${offset}`});if(!current())return;if(!Array.isArray(data.records))throw new Error('饮食记录返回不完整');records.value=[...records.value.filter(r=>!data.records.some(n=>n.id===r.id)),...data.records.map(r=>({...r,member_id:m.id}))];next.value={...next.value,[m.id]:data.next_offset}}
 if(detail.value||props.detailId){const member=detail.value?.member_id||props.memberId,id=detail.value?.id||props.detailId;if(!member)throw new Error('此旧链接缺少成员信息，请从饮食记录列表重新打开');const fresh=await readDietRecord(member,id);if(!current())return;detail.value=fresh;date.value=mealDay(fresh.snapshot.meal.eaten_at);editing.value=false}
 }catch(e){failure(e,mine,rev)}finally{if(mine===epoch)busy.value=false}}
function select(id){if(busy.value)return;scope.value=id;void load()}
async function show(row){if(busy.value)return;const mine=++epoch,rev=sessionRevision();busy.value=true;error.value='';detail.value=null;editing.value=false;try{const data=await readDietRecord(row.member_id,row.id);if(mine===epoch&&rev===sessionRevision()){detail.value=data;pending.value=scopedStorage.getStorageSync('meal-correction:'+row.id)||null}}catch(e){failure(e,mine,rev)}finally{if(mine===epoch)busy.value=false}}
function edit(){meal.value=JSON.parse(JSON.stringify(detail.value.snapshot.meal));reason.value='';editing.value=true}
async function save(){if(busy.value||(!pending.value&&!reason.value.trim()))return;const mine=++epoch,rev=sessionRevision();busy.value=true;error.value='';const source=detail.value;try{if(!pending.value){const id=newHealthRequestId();pending.value={path:'/api/health/v1/diet-logs/'+source.id,method:'PATCH',headers:{'Idempotency-Key':id,'If-Match':'"'+source.source_version+'"'},data:{expected_version:source.source_version,client_request_id:id,meal:mealInput(meal.value),reason:reason.value.trim(),accept_incomplete:true}};scopedStorage.setStorageSync('meal-correction:'+source.id,pending.value)}await request(pending.value);if(mine!==epoch||rev!==sessionRevision())return;pending.value=null;scopedStorage.setStorageSync('meal-correction:'+source.id,null);const fresh=await readDietRecord(source.member_id,source.id);if(mine!==epoch||rev!==sessionRevision())return;detail.value=fresh;editing.value=false;records.value=records.value.map(r=>r.id===source.id?detail.value:r)}catch(e){if(mine===epoch){if(rev!==sessionRevision()||[401,403,404,410].includes(Number(e.code))||e.code==='SESSION_CHANGED'){failure(e,mine,rev);return}error.value=e.message;if([400,404,409,422].includes(Number(e.code))){pending.value=null;scopedStorage.setStorageSync('meal-correction:'+source.id,null)}if(Number(e.code)===409){try{const fresh=await readDietRecord(source.member_id,source.id);if(mine!==epoch||rev!==sessionRevision())return;detail.value=fresh;editing.value=false;error.value='记录已变化，已读取当前版本；请重新核对后再修改。'}catch(readError){if(mine===epoch&&rev===sessionRevision()){detail.value=null;error.value=readError.message}}}}}finally{if(mine===epoch)busy.value=false}}
async function searchRecipes(query=''){if(busy.value)return;const mine=++epoch,rev=sessionRevision();busy.value=true;error.value='';try{const {data}=await request({path:'/api/health/v1/recipes?q='+encodeURIComponent(query)});if(mine===epoch&&rev===sessionRevision())recipes.value=data}catch(e){failure(e,mine,rev)}finally{if(mine===epoch)busy.value=false}}
function chat(row=detail.value){uni.navigateTo({url:feedbackUrl(row.member_id,row)})}
onShow(()=>load());onHide(hide);onUnload(hide)

const eatenWeight=item=>item.grams==null||item.share_ratio==null?'重量未知':Number((Number(item.grams)*Number(item.share_ratio)).toFixed(1))+' g'
const dayLabel=value=>{const match=/^\d{4}-(\d{2})-(\d{2})$/.exec(value||'');return match?Number(match[1])+'月'+Number(match[2])+'日':value}
</script>
<template>

 <view class="dj0" :class="{'dj1':editing}">
  <view class="dj2"><text class="dj3">{{editing?'调整这一餐':detail?'这一餐，已记下':'每一餐，都好好记下'}}</text><text v-if="!detail" class="dj4">把吃过的日常，留给更懂你的营养师</text></view>
  <text v-if="busy" class="dj5">正在读取…</text><view v-if="error" class="dj6" role="alert"><text>{{error}}</text><button :disabled="busy" @click="load()">重新读取</button></view>
  <template v-if="!detail">
   <view class="dj7">
    <view class="dj8"><picker mode="date" :value="date" @change="date=$event.detail.value"><view class="dj9"><view class="dj10"><AppIcon name="calendar" :size="34"/></view><view class="dj11"><view class="dj12"><text>{{dayLabel(date)}}</text><text class="dj13">⌄</text></view><text class="dj14">{{today?'今天的饮食':'这一天的饮食'}}</text></view></view></picker><button class="dj15" @click="capture()"><text>记一餐</text><text class="dj-next">→</text></button></view>
    <scroll-view scroll-x class="dj16" :show-scrollbar="false"><view class="dj17"><button :class="{'dj18':scope==='all'}" :disabled="busy" @click="select('all')">全家</button><button v-for="m in members" :key="m.id" :class="{'dj18':scope===m.id}" :disabled="busy" @click="select(m.id)"><text>{{name(m.id)}}</text></button></view></scroll-view>
   </view>
   <view class="dj19"><text>一日三餐与加餐</text><text>{{busy?'正在读取…':error?'暂时无法读取':'已记录 '+recordedMeals+' 个餐次'}}</text></view>
   <view class="meal-list"><view v-for="(label,key) in mealLabels" :key="key" class="dj20" :class="'dj-meal-'+key">
    <view class="dj21"><view class="dj22"><image class="dj-food" :src="'/static/journal/'+key+'.png'" mode="aspectFit" aria-hidden="true"/><view class="dj23"><text>{{label}}</text><text class="dj24">{{busy?'读取中':error?'等待重新读取':visible.some(r=>r.snapshot.meal.meal_type===key)?'已记录':'还没有记录'}}</text></view></view><button class="dj25" :aria-label="'记录'+label" @click="capture(key)"><text>记录</text><text class="dj26">＋</text></button></view>
    <button v-for="r in visible.filter(r=>r.snapshot.meal.meal_type===key)" :key="r.id" class="dj37" :disabled="busy" @click="show(r)"><FoodImageSlot class="dj38"/><view class="dj39"><text>{{r.snapshot.meal.items.filter(i=>!i.excluded).map(i=>i.name).join(' · ')||'查看这一餐'}}</text><text>{{name(r.member_id)}} · {{portionNote(r.snapshot.meal.items[0]||{})}}</text></view><text class="dj40">›</text></button>
   </view></view><button v-if="Object.values(next).some(n=>n!==null)" class="dj41" :disabled="busy" @click="load(true)">加载更早记录</button>
   <view class="dj35"><view class="dj36"/><text>记下真实吃过的，慢慢了解自己的饮食</text></view>
  </template>
  <template v-else><view class="dj42"><text>{{name(detail.member_id)}} · {{mealLabels[detail.snapshot.meal.meal_type]}}</text><text>{{dayLabel(mealDay(detail.snapshot.meal.eaten_at))}}</text></view>
   <template v-if="editing"><HealthMealEditor :meal="meal" :coarse="true" :disabled="busy||!!pending" :recipes="recipes" @search="searchRecipes"/><view class="dj48"><text>更正原因</text><textarea v-model="reason" :disabled="busy||!!pending" class="text-area" placeholder="例如：调整了实际吃过的份量"/></view><view class="dj49"><button class="dj50" :disabled="busy||!!pending" @click="editing=false">取消</button><button class="dj51" :disabled="busy||(!pending&&!reason.trim())" @click="save">{{busy?'正在保存…':pending?'恢复原保存请求':'确认更正并保存'}}</button></view></template>
   <template v-else><view class="dj43"><view v-for="item in detail.snapshot.meal.items.filter(i=>!i.excluded)" :key="item.item_id" class="dj44"><FoodImageSlot class="dj38"/><view><text>{{item.name}}</text><text>{{portionNote(item)}} · {{eatenWeight(item)}}</text></view></view></view><view class="dj45"><text>热量</text><text>{{detail.snapshot.nutrition?.totals?.energy_kcal??'未知'}}<text v-if="detail.snapshot.nutrition?.totals?.energy_kcal!=null"> kcal</text></text></view><view class="dj46"><button class="primary-button" :disabled="busy||!!pending" @click="chat()">聊聊这一餐</button><button v-if="pending" class="dj47" :disabled="busy" @click="save">恢复上次更正请求</button><button v-else class="dj47" :disabled="busy" @click="edit">更正这条记录</button><button class="dj41" :disabled="busy||!!pending" @click="detail=null;editing=false">返回记录列表</button></view></template>
  </template>
 </view>
</template>
<style>

.dj0{padding-bottom:4rpx;color:#35343f}.dj0.dj1{padding-bottom:calc(env(safe-area-inset-bottom) + 180rpx)}
.dj2{padding:22rpx 4rpx 26rpx}.dj3{display:block;font-size:44rpx;font-weight:500;line-height:1.45;letter-spacing:1rpx}.dj4{display:block;margin-top:12rpx;font-size:25rpx;color:#74717f;line-height:1.6}
.dj5{display:none}.dj6{padding:24rpx;margin:0 0 24rpx;background:#fff4ef;border-radius:24rpx;font-size:26rpx;line-height:1.6;color:#a34b39}.dj6 button{color:#514568;min-height:44px}
.dj7{padding:28rpx 28rpx 0;border:1px solid rgba(255,255,255,.9);border-radius:36rpx;background:linear-gradient(180deg,rgba(255,255,255,.4),rgba(255,255,255,.95));box-shadow:inset 0 1px 0 #fff}
.dj8{display:flex;justify-content:space-between;align-items:center;gap:16rpx;padding-bottom:24rpx}.dj8 picker{min-width:0;flex:1}.dj9{display:flex;align-items:center;gap:18rpx;min-height:88rpx}.dj10{display:flex;align-items:center;justify-content:center;flex:none;width:76rpx;height:80rpx;background:rgba(239,236,247,.8);border-radius:24rpx;color:#7e708e}.dj11{min-width:0}.dj12{display:flex;align-items:center;gap:14rpx;font-size:34rpx;font-weight:500;white-space:nowrap;line-height:1.4}.dj13{color:#8e879a;font-size:26rpx}.dj14{display:block;margin-top:6rpx;font-size:23rpx;color:#74717f}
.dj15{display:flex;align-items:center;justify-content:space-between;gap:22rpx;flex:none;min-width:198rpx;min-height:88rpx;padding:0 24rpx;border-radius:24rpx;background:linear-gradient(105deg,#ddecff,#bbcff3);box-shadow:inset 0 1px 2px rgba(255,255,255,.8),0 4rpx 14rpx rgba(131,165,211,.12);color:#365e94;font-size:27rpx}.dj-next{font-size:33rpx;line-height:1}
.dj16{width:100%;white-space:nowrap;border-top:1px solid rgba(226,222,237,.55)}.dj17{display:inline-flex;align-items:center;gap:12rpx;min-width:100%;padding:16rpx 0}.dj17 button{display:flex;align-items:center;justify-content:center;flex:none;max-width:240rpx;min-width:94rpx;min-height:80rpx;padding:12rpx 24rpx;border:1px solid transparent;border-radius:22rpx;font-size:25rpx;color:#74717f}.dj17 button text{display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dj17 .dj18{color:#514568;background:#eeeaf7;border-color:rgba(255,255,255,.8);font-weight:500}
.dj19{display:flex;align-items:center;justify-content:space-between;gap:16rpx;margin:36rpx 4rpx 20rpx;font-size:27rpx;font-weight:500}.dj19>text:last-child{font-size:23rpx;font-weight:400;color:#74717f}
.dj20{padding:28rpx 30rpx;margin:0 -10rpx 18rpx;border:1px solid rgba(255,255,255,.92);border-radius:32rpx;background:linear-gradient(180deg,rgba(255,255,255,.6),rgba(255,255,255,.97));box-shadow:inset 0 1px 0 #fff}.dj21{display:flex;justify-content:space-between;gap:16rpx;align-items:center;min-height:124rpx}.dj22{display:flex;align-items:center;gap:22rpx;min-width:0}.dj23>text{display:block;font-size:30rpx;font-weight:500;line-height:1.5}.dj23>.dj24{font-size:23rpx;font-weight:400;color:#898392;margin-top:3rpx}.dj25{display:flex;align-items:center;justify-content:center;gap:8rpx;flex:none;min-width:112rpx;min-height:88rpx;color:#7b6b91;font-size:25rpx}.dj26{font-size:30rpx;line-height:1}.dj-food{display:block;flex:none;width:100rpx;height:100rpx}
.dj35{display:flex;align-items:center;justify-content:center;gap:10rpx;padding:10rpx 0 0;color:#898392;font-size:22rpx;line-height:1.6}.dj36{width:7rpx;height:7rpx;background:#bab2c8;border-radius:50%;flex:none}
.dj37{display:flex;align-items:center;gap:20rpx;padding-top:22rpx;width:100%;text-align:left}.dj38{width:112rpx;height:112rpx;border-radius:18rpx}.dj39{flex:1;min-width:0}.dj39>text{display:block;font-size:29rpx;line-height:1.6;overflow-wrap:anywhere}.dj39>text+text{font-size:26rpx;color:#74717f;margin-top:8rpx}.dj40{color:#74717f;font-size:34rpx}.dj41{width:100%;min-height:44px;font-size:27rpx;color:#7b6b91;margin-top:16rpx}.dj42{display:flex;justify-content:space-between;gap:20rpx;font-size:28rpx;color:#74717f;padding:4rpx 4rpx 28rpx}.dj43{background:#fff;border:1rpx solid #e7ebf2;border-radius:26rpx;padding:0 24rpx}.dj44{display:flex;gap:22rpx;align-items:center;padding:24rpx 0;border-bottom:1rpx solid #edf0f5}.dj44:last-child{border:0}.dj44>view:last-child{flex:1;min-width:0}.dj44 text{display:block;line-height:1.6;font-size:30rpx;overflow-wrap:anywhere}.dj44 text+text{font-size:26rpx;color:#74717f;margin-top:8rpx}.dj45{display:flex;justify-content:space-between;padding:28rpx 6rpx;font-size:28rpx}.dj45>text:last-child{color:#74717f}.dj46{display:flex;flex-direction:column;gap:18rpx;margin-top:14rpx}.dj46 .dj47{border-radius:999rpx}.dj48{margin-top:26rpx}.dj48>text{font-size:29rpx;font-weight:500}.dj48 textarea{height:180rpx;min-height:90px;margin-bottom:0;background:#fff;font-size:28rpx}.dj49{position:fixed;z-index:30;bottom:0;left:0;right:0;display:flex;gap:16rpx;background:#fff;border-top:1rpx solid #edf0f5;padding:18rpx 32rpx calc(env(safe-area-inset-bottom) + 18rpx)}.dj49 button{min-height:48px;border-radius:999rpx;font-size:28rpx;display:flex;align-items:center;justify-content:center}.dj50{flex:.7;border:1rpx solid #cbd3e1}.dj51{flex:1.5;background:#35343f;color:#fff}.dj0 button[disabled]{opacity:.45}
@media(max-width:350px){.dj17 button,.dj21>text:last-child,.dj39>text+text,.dj44 text+text,.dj42,.dj8>button{font-size:13px}.dj39>text,.dj21,.dj44 text{font-size:14px}.dj49 button{font-size:14px}}
/* #ifdef H5 */
.dj49{max-width:480px;margin:0 auto}
/* #endif */
</style>
