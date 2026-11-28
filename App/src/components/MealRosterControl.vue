<script setup>
import {ref,computed} from 'vue'
import {request} from '../services/request.js'
import {storageContext} from '../services/storage.js'
import {newHealthRequestId} from '../services/health-request-id.js'
const props=defineProps({plan:Object,familyId:String,members:{type:Array,default:()=>[]},busy:Boolean,entryOnly:Boolean,overlayOnly:Boolean})
const emit=defineEmits(['updated','open','close'])
const opened=ref(false),scope=ref('all'),selected=ref([]),saving=ref(false),error=ref(''),baseVersion=ref(null)
const mealTypes=['breakfast','lunch','dinner'],labels={breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}
const state=computed(()=>props.plan?.roster||{})
const summary=computed(()=>{
 const groups=(props.plan?.meals||[]).map(m=>(m.members||[]).map(p=>p.name).join('、'))
 return groups.length&&groups.every(x=>x===groups[0])?groups[0]:'各餐成员不同'
})
const targets=computed(()=>(scope.value==='all'?mealTypes:[scope.value]).filter(m=>props.plan?.meals.some(item=>item.meal_type===m)&&!state.value[m]?.execution_locked))
const validSelected=computed(()=>selected.value.filter(id=>props.members.some(person=>person.id===id)))
function choose(value){if(value!=='all'&&(state.value[value]?.execution_locked||!props.plan?.meals.some(m=>m.meal_type===value)))return;scope.value=value;const m=props.plan?.meals.find(m=>value==='all'?!state.value[m.meal_type]?.execution_locked:m.meal_type===value);selected.value=(m?.members||[]).map(p=>p.id).filter(id=>props.members.some(person=>person.id===id))}
function open(){if(props.busy||saving.value||!props.plan)return;if(props.entryOnly){emit('open');return}error.value='';baseVersion.value=props.plan.version;choose('all');opened.value=true}
function close(){if(saving.value)return;opened.value=false;emit('close')}
function toggle(id){selected.value=selected.value.includes(id)?selected.value.filter(v=>v!==id):[...selected.value,id]}
async function confirm(){
 if(saving.value||!targets.value.length||!validSelected.value.length)return
 const owner=storageContext();saving.value=true;error.value=''
 try{
  await request({path:`/api/family/${encodeURIComponent(props.familyId)}/daily-meal-plans/${props.plan.date}/members`,method:'POST',
   data:{client_request_id:newHealthRequestId(),version:baseVersion.value,meal_types:targets.value,member_ids:validSelected.value,consumed:false}})
  if(owner!==storageContext())return
  opened.value=false;emit('close');emit('updated')
 }catch(e){if(owner===storageContext())error.value=e.message||'暂未完成，请刷新核对后重试'}finally{saving.value=false}
}
if(props.overlayOnly)open()
</script>
<template>
 <view v-if="plan&&familyId" class="roster-control">
  <button v-if="!overlayOnly" class="roster-entry" :disabled="busy||saving" :aria-label="'调整就餐成员，原餐单成员'+summary" aria-haspopup="dialog" :aria-expanded="opened" @click.stop="open"><text>就餐成员</text><text aria-hidden="true">⌄</text></button>
  <view v-if="opened" class="roster-mask" @click.self="close" @touchmove.stop.prevent>
   <view class="roster-panel" role="dialog" aria-modal="true" aria-label="调整就餐成员" @click.stop>
    <view class="roster-title"><text>谁一起吃饭？</text><button :disabled="saving" aria-label="关闭成员选择" @click="close">×</button></view>
    <view class="roster-scopes">
     <button :disabled="saving" :class="{chosen:scope==='all'}" @click="choose('all')">今天三餐</button>
     <button v-for="m in mealTypes" :key="m" :disabled="saving||!!state[m]?.execution_locked||!plan.meals.some(item=>item.meal_type===m)" :class="{chosen:scope===m}" @click="choose(m)"><text>{{labels[m]}}</text><text v-if="state[m]?.execution_locked" class="roster-scope-state">已有记录</text></button>
    </view>
    <scroll-view scroll-y :show-scrollbar="false" class="roster-list" :style="{height:Math.min(members.length,5)*58+'px'}" @touchmove.stop>
     <button v-for="person in members" :key="person.id" role="checkbox" :aria-checked="selected.includes(person.id)" :disabled="saving" @click="toggle(person.id)"><text class="roster-name">{{person.name}}</text><text class="roster-check" aria-hidden="true">{{selected.includes(person.id)?'✓':'○'}}</text></button>
    </scroll-view>
    <view class="roster-footer">
     <text v-if="error" class="roster-error" role="alert">{{error}}</text>
     <button class="roster-confirm" :disabled="saving||!validSelected.length||!targets.length" @click="confirm">{{saving?'正在保存…':'确认更新 · '+validSelected.length+'人'}}</button>
    </view>
   </view>
  </view>
 </view>
</template>
<style scoped>
.roster-control{flex:none;min-width:0}
.roster-entry{display:flex;align-items:center;justify-content:center;gap:3px;width:auto;min-height:44px;box-sizing:border-box;margin:0;padding:0 3px;border-radius:8px;background:transparent;color:#655778;font-size:12px;line-height:18px;white-space:nowrap;text-align:center}
.roster-entry[disabled],.roster-panel button[disabled]{opacity:.5}
.roster-entry:after,.roster-panel button:after{border:0}
.roster-mask{position:fixed;inset:0;z-index:210;display:flex;align-items:flex-end;background:rgba(40,37,64,.3)}
.roster-panel{display:flex;flex-direction:column;width:100%;max-height:80vh;box-sizing:border-box;padding:16px 20px calc(18px + env(safe-area-inset-bottom));border:1px solid rgba(255,255,255,.86);border-bottom:0;border-radius:26px 26px 0 0;background-color:#fafafc;background-image:radial-gradient(ellipse at 0% 0%,rgba(159,192,249,.32),transparent 72%),radial-gradient(ellipse at 100% 0%,rgba(205,186,237,.3),transparent 75%);background-size:100% 200px;background-repeat:no-repeat;color:#514961;box-shadow:inset 0 1px 0 rgba(255,255,255,.9),0 -8px 32px rgba(61,49,97,.08)}
.roster-title{display:flex;flex:none;align-items:center;justify-content:space-between;min-height:44px;font-size:18px;font-weight:600}
.roster-title button{flex:none;width:44px;height:44px;margin:0;padding:0;background:transparent;color:#7b6d91;font-size:26px}
.roster-scopes{display:flex;flex:none;gap:8px;margin:10px 0 12px}
.roster-scopes button{display:flex;flex:1;flex-direction:column;align-items:center;justify-content:center;min-width:0;min-height:34px;box-sizing:border-box;margin:0;padding:8px 4px;border:1px solid transparent;border-radius:12px;background:rgba(255,255,255,.55);color:#7c718a;font-size:12px;line-height:18px;white-space:nowrap}
.roster-scopes .chosen{border-color:rgba(255,255,255,.65);background:linear-gradient(145deg,#e2dcf6,#d7ccec);color:#62517e}
.roster-scope-state{font-size:10px;line-height:14px}
.roster-list{flex:0 1 auto;min-height:0;max-height:35vh}
.roster-list button{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;min-width:0;height:48px;box-sizing:border-box;margin:0 0 10px;padding:10px 14px;border:1px solid rgba(255,255,255,.85);border-radius:13px;background:linear-gradient(145deg,rgba(255,255,255,.98),rgba(248,247,253,.97));color:#5f526f;font-size:14px;line-height:22px;box-shadow:0 3px 10px rgba(77,66,111,.025),inset 0 1px 0 #fff}
.roster-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left}
.roster-check{flex:none}
.roster-footer{flex:none;min-width:0}
.roster-confirm{width:100%;min-height:46px;box-sizing:border-box;margin:2px 0 0;padding:10px 14px;border:1px solid rgba(255,255,255,.7);border-radius:14px;background:linear-gradient(115deg,#e1d7f3,#d1c3e9);color:#5b4779;font-size:14px;line-height:24px;box-shadow:inset 0 1px 0 rgba(255,255,255,.65)}
.roster-error{display:block;margin:0 0 8px;color:#964f55;font-size:12px;line-height:1.7;overflow-wrap:anywhere}
</style>
