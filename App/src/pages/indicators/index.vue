<script setup>
import { ref } from 'vue'
import { onLoad,onShow,onHide,onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import { loadCloudProfile } from '../../services/cloud-profile.js'
import { readMeasurements,summarizeMeasurements } from '../../services/cloud-indicators.js'
import { request } from '../../services/request.js'
import { scopedStorage } from '../../services/storage.js'
import { sessionRevision } from '../../services/session.js'
const members=ref([]),familyId=ref(''),familyMember=ref(''),healthMemberId=ref(''),kind=ref('weight'),start=ref(''),end=ref(''),result=ref(null),selected=ref([]),busy=ref(false),error=ref('')
const kinds=['weight','blood_glucose','blood_lipids','blood_pressure'],names=['体重','血糖','血脂','血压']
const labels={weight:'体重',glucose:'血糖',systolic:'收缩压',diastolic:'舒张压',tc:'总胆固醇',tg:'甘油三酯',hdl:'高密度脂蛋白',ldl:'低密度脂蛋白'}
const conditions={fasting:'空腹',after_meal_2h:'餐后2小时',random:'随机',same_observation:'同类测量'}
let epoch=0,requested=''
onLoad(o=>{requested=o.memberId||'';const date=new Date(Date.now()+8*3600000).toISOString().slice(0,10);start.value=date;end.value=date})
async function load(){if(busy.value)return;const mine=++epoch,rev=sessionRevision();busy.value=true;error.value='';try{const p=await loadCloudProfile();if(mine!==epoch||rev!==sessionRevision())return;members.value=p.members;familyId.value=p.householdId;const chosen=p.members.find(m=>m.id===requested||m.healthMemberId===requested)||p.members.find(m=>m.relation==='本人')||p.members[0];if(!chosen)throw new Error('请先建立家庭健康档案');familyMember.value=chosen.id;healthMemberId.value=chosen.healthMemberId||''}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch)busy.value=false}}
function discard(){epoch++;members.value=[];familyMember.value='';healthMemberId.value='';result.value=null;selected.value=[];busy.value=false;error.value=''}
onShow(load);onHide(discard);onUnload(discard)
function change(field,value){epoch++;result.value=null;selected.value=[];error.value='';field==='kind'?kind.value=value:field==='start'?start.value=value:end.value=value}
function selectMember(m){if(busy.value)return;result.value=null;selected.value=[];familyMember.value=m.id;healthMemberId.value=m.healthMemberId||''}
async function read(onlySelected=false){if(busy.value)return;if(!familyMember.value){error.value='请先选择成员，或重新读取家庭档案';return}if(onlySelected){const rows=result.value?.records.filter(r=>selected.value.includes(r.record_id))||[];if(!rows.length)return;result.value={...result.value,records:rows,review:{groups:summarizeMeasurements(rows,kind.value),questions:[]}};return}const mine=++epoch,rev=sessionRevision();busy.value=true;error.value='';result.value=null;try{const value=await readMeasurements(familyId.value,familyMember.value,kind.value,start.value,end.value);if(mine===epoch&&rev===sessionRevision()){result.value=value;selected.value=[]}}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch)busy.value=false}}
function toggle(id){selected.value=selected.value.includes(id)?selected.value.filter(x=>x!==id):[...selected.value,id]}
async function consult(){
 if(!healthMemberId.value||kind.value==='weight'||busy.value)return
 const chosen=members.value.find(m=>m.id===familyMember.value)
 if(chosen?.relation!=='本人'){error.value='指标助手目前只接受本人实测记录；其他成员仍可查看获授权的原值。';return}
 const rows=result.value.records.filter(r=>!selected.value.length||selected.value.includes(r.record_id))
 if(!rows.length||rows.length>100){error.value='请明确选择1至100条本人实测记录再咨询。';return}
 const mine=++epoch,rev=sessionRevision();busy.value=true;error.value=''
 try{const selection={start_date:start.value,end_date:end.value,records:rows.map(r=>({record_id:r.record_id,version:r.version}))};const {data}=await request({path:`/api/health/v1/members/${healthMemberId.value}/indicator-reviews/${kind.value}`,method:'POST',data:selection});if(mine!==epoch||rev!==sessionRevision())return;if(data.source_member_id!==familyMember.value||data.records.length!==rows.length)throw new Error('实测来源已变化，请重新读取记录后选择');const task=kind.value+'_review';scopedStorage.setStorageSync(`indicator-choice:${healthMemberId.value}:${task}`,data.selection);uni.navigateTo({url:`/pages/chat/index?memberId=${encodeURIComponent(healthMemberId.value)}&taskType=${task}&indicatorChoice=1`})}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch)busy.value=false}
}
</script>
<template><view class="screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack()">‹</button><text class="nav-title">实测记录回顾</text></view></AppNavBar>
<view class="panel"><text class="display-title">回顾测量事实</text><text class="safe-note">北京时间最多366天；统计原值，不作诊断或个体化建议。</text>
<picker :range="members.map(m=>m.name)" :disabled="busy" @change="selectMember(members[$event.detail.value])"><view class="field-input">{{members.find(m=>m.id===familyMember)?.name||'选择成员'}} ›</view></picker>
<picker :range="names" :disabled="busy" @change="change('kind',kinds[$event.detail.value])"><view class="field-input">{{names[kinds.indexOf(kind)]}} ›</view></picker>
<text>开始日期</text><picker mode="date" :value="start" :disabled="busy" @change="change('start',$event.detail.value)"><view class="field-input">{{start}} ›</view></picker>
<text>结束日期</text><picker mode="date" :value="end" :disabled="busy" @change="change('end',$event.detail.value)"><view class="field-input">{{end}} ›</view></picker>
<button class="primary-button" :disabled="busy" @click="read()">{{busy?'正在读取…':'读取记录与统计'}}</button><text v-if="error" class="inline-error">{{error}}</text>
<template v-if="result"><text v-if="!result.source_member_id" class="inline-error">尚未关联本人的指标来源，请返回账号页完成本人档案关联。</text><text>范围内 {{result.total}} 条，本次 {{result.records.length}} 条{{result.truncated?'，已截断，请缩短范围':''}}</text><text v-if="result.source_member_id&&!result.records.length" class="safe-note">所选范围没有可用记录，未按零值统计。</text><text class="safe-note">以下统计仅依据本次返回的记录，不代表未返回记录或全天完整情况。</text>
<view v-for="row in result.records" :key="row.record_id" class="card item" @click="toggle(row.record_id)"><text>{{selected.includes(row.record_id)?'☑':'☐'}} {{new Date(row.measured_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}} · {{conditions[row.condition]||'同条测量'}} · v{{row.version}}</text><template v-for="(label,key) in labels" :key="key"><text v-if="row[key]!==undefined">{{label}} {{row[key]}} {{row.unit}}</text></template><text>来源：{{row.source}}</text></view>
<button v-if="result.records.length" class="secondary-button" :disabled="busy||!selected.length" @click="read(true)">仅回顾勾选记录</button>
<view v-for="group in result.review.groups" :key="group.condition" class="card item"><text>{{conditions[group.condition]}}</text><text v-for="(value,key) in group.statistics" :key="key">{{labels[key]}}：{{value.count}}次，均值{{value.mean}}，最低{{value.minimum}}，最高{{value.maximum}} {{group.unit}}</text></view>
<text v-if="result.source_member_id" class="section-title">进一步回顾需补充</text><text v-for="question in result.review.questions" :key="question" class="safe-note">{{question}}</text><text class="safe-note">统计只使用当前读取的实测值；不同测量条件分别统计。</text><button v-if="result.source_member_id&&healthMemberId&&kind!=='weight'&&members.find(m=>m.id===familyMember)?.relation==='本人'" class="secondary-button" @click="consult">就这些记录聊聊</button></template>
</view></view></template>
<style scoped>.panel{display:flex;flex-direction:column;gap:22rpx;margin-top:30rpx}.item{display:flex;flex-direction:column;gap:12rpx;padding:22rpx;font-size:25rpx}.safe-note{text-align:left}.field-input{display:flex;align-items:center}</style>
