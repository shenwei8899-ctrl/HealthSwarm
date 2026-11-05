<script setup>
import { ref,onUnmounted } from 'vue'
import ReferenceMealPlanCard from './ReferenceMealPlanCard.vue'
import { request } from '../services/request.js'
import { scopedStorage,storageContext } from '../services/storage.js'
import { newHealthRequestId } from '../services/health-task-flow.js'
const props=defineProps({result:Object,memberId:String,detailMode:Boolean})
const emit=defineEmits(['detail'])
const busy=ref(false),error=ref(''),saved=ref(null)
const sourceDetails=ref({})
const names={breakfast:'早餐',lunch:'午餐',dinner:'晚餐',snack:'加餐'}
function toggleSourceDetails(id){sourceDetails.value={...sourceDetails.value,[id]:!sourceDetails.value[id]}}
let alive=true;const scope=storageContext();onUnmounted(()=>alive=false)
async function save(){if(props.result.kind!=='meal_plan_preview'||busy.value||!props.result.data?.preview_id||scope!==storageContext())return;busy.value=true;error.value='';const key='chat-plan-save:'+props.result.data.preview_id;try{let pending=scopedStorage.getStorageSync(key);if(!pending){const id=newHealthRequestId();pending={path:'/api/health/v1/members/'+props.memberId+'/meal-plans',method:'POST',headers:{'Idempotency-Key':id},data:{client_request_id:id,preview_id:props.result.data.preview_id}};scopedStorage.setStorageSync(key,pending)}const {data}=await request(pending);if(!alive||scope!==storageContext())return;if(data.member_id!==props.memberId||!data.plan_id)throw new Error('餐单保存回执待核对，请用原请求重试');saved.value=data;scopedStorage.setStorageSync(key,null)}catch(e){if(alive&&scope===storageContext()){error.value=e.message;if([400,403,404,409,422].includes(Number(e.code)))scopedStorage.setStorageSync(key,null)}}finally{if(alive)busy.value=false}}
function inspect(){if(props.result.kind==='meal_plan_candidates')return;const id=saved.value?.plan_id||props.result.data?.plan_id;uni.navigateTo({url:'/pages/health/plans?memberId='+encodeURIComponent(props.memberId)+(id?'&planId='+encodeURIComponent(id):'')})}
</script>
<template>
 <view v-if="result.kind==='meal_plan_candidates'" class="business-card candidate-card">
  <text class="section-title">{{result.data.plan_date}} · 待核对候选</text>
  <text class="candidate-notice">{{result.data.notice}}</text>
  <text class="safe-note">以下为依据来源整理的做法，非逐字原文。个人适用性尚未确认，未保存为每日餐单，暂不提供采购。</text>
  <view v-if="result.data.restriction_verification" class="candidate-materials"><text>{{result.data.restriction_verification.notice||'保留的限制尚未核对适用性'}}</text><text v-for="(item,index) in result.data.restriction_verification.restrictions" :key="index" selectable>{{item.text}}</text></view>
  <view class="candidate-materials"><text>仍需核对</text><text v-for="item in result.data.unresolved_materials" :key="item" selectable>{{item}}</text></view>
  <view v-for="meal in result.data.meals" :key="meal.meal_type" class="candidate-meal">
   <text class="candidate-meal-title">{{names[meal.meal_type]}}</text>
   <view v-for="dish in meal.dishes" :key="dish.id" class="candidate-dish">
    <text class="candidate-dish-title" selectable>{{dish.name}}</text>
    <text class="candidate-label">食材</text><text v-for="(ingredient,index) in dish.ingredients" :key="'ingredient-'+index" selectable>{{ingredient}}</text>
    <text class="candidate-label">完整做法</text><text v-for="(step,index) in dish.steps" :key="'step-'+index" selectable>{{index+1}}. {{step}}</text>
    <text class="candidate-label">来源整理稿</text><text selectable>{{dish.source.title}}</text><text class="candidate-source" selectable>{{dish.source.url}}</text>
    <button v-if="dish.source.notes" class="candidate-source-toggle" :aria-expanded="!!sourceDetails[dish.id]" @click="toggleSourceDetails(dish.id)">{{sourceDetails[dish.id]?'收起来源详情':'来源详情'}}</button>
    <text v-if="dish.source.notes&&sourceDetails[dish.id]" class="safe-note" selectable>{{dish.source.notes}}</text>
   </view>
  </view>
 </view>
 <ReferenceMealPlanCard v-else-if="result.data?.scope==='daily_reference'" :plan="result.data" :detail-mode="detailMode" @detail="emit('detail',$event)"/>
 <view v-else class="business-card"><template v-if="result.kind==='meal_plan_preview'"><text class="section-title">{{result.data.plan_date||'本次'}}餐单预览</text><view v-for="meal in result.data.meals||[]" :key="meal.meal_type"><text>{{names[meal.meal_type]}}</text><text v-for="(dish,i) in meal.dishes||[]" :key="i">{{dish.name}} · {{dish.planned_grams??'份量未知'}}{{dish.planned_grams?' g':''}}</text></view><text class="safe-note">{{saved?'已保存餐单草稿':'预览尚未保存'}}，未自动替换今日安排或记为已吃。</text><button v-if="result.data.preview_id&&!saved" class="secondary-button" :disabled="busy" @click="save">{{busy?'正在核对保存…':'保存这份餐单'}}</button><button v-if="saved||result.data.plan_id" class="secondary-button" @click="inspect">查看已保存餐单 ›</button></template><template v-else-if="result.kind==='diet_analysis'"><text class="section-title">已记录饮食的回顾</text><text v-for="finding in result.data.findings||[]" :key="finding">{{finding}}</text><text class="safe-note">仅依据已确认记录，未记录与缺失数值保持未知。</text></template><template v-else><text class="section-title">{{result.kind==='quality_check'?'餐单核对结果':'食材需求结果'}}</text><text>请结合当前保存的餐单核对本次结果。</text><button class="secondary-button" @click="inspect">查看相关餐单 ›</button></template><text v-if="error" class="inline-error">{{error}}</text></view>
</template>
<style scoped>
.business-card{display:flex;flex-direction:column;gap:14px;padding:18px;margin:18px 0 4px;background:#f7f7f7;border:0;border-radius:12px;color:#282828;font-size:15px;line-height:1.8}.business-card>view{display:flex;flex-direction:column;gap:8px;padding:0 0 12px;border-bottom:1px solid #e8e8e8;background:transparent;border-radius:0}.business-card>view:last-of-type{border:0}.business-card .section-title{font-size:18px;font-weight:600;line-height:1.5;color:#181818}.business-card .safe-note{font-size:12px;line-height:1.7;color:#858585;text-align:left;margin:0}.business-card button{display:flex;align-items:center;justify-content:center;align-self:flex-start;min-height:44px;padding:9px 16px;border-radius:8px;background:#111;color:#fff;border:0;font-size:15px;line-height:1.6}.business-card button:after{border:0}.business-card button[disabled]{opacity:.45}.inline-error{font-size:13px;line-height:1.7;color:#8d4c40}
.candidate-card{background:var(--ui-surface,#f7f7f7)}.candidate-notice{color:var(--ui-text,#35343f)}.candidate-meal-title,.candidate-dish-title{font-weight:600}.candidate-dish{display:flex;flex-direction:column;gap:6px;margin-top:8px}.candidate-label{margin-top:8px;font-size:13px;color:var(--ui-muted,#686868)}.candidate-source{overflow-wrap:anywhere;word-break:break-all;font-size:12px;color:var(--ui-muted,#686868)}
.candidate-card .candidate-source-toggle{min-height:44px;padding:4px 0;background:transparent;color:var(--ui-muted,#686868);font-size:12px}
</style>
