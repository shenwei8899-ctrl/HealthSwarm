<script setup>
import { ref } from 'vue'
import { onLoad, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import { request } from '../../services/request.js'
import { sessionRevision } from '../../services/session.js'
import { scopedStorage } from '../../services/storage.js'
const memberId=ref(''), kind=ref('blood_glucose'), start=ref(''), end=ref(''), result=ref(null), selected=ref([]), busy=ref(false), error=ref('')
const kinds=['blood_glucose','blood_lipids','blood_pressure'], names=['血糖','血脂','血压']
const labels={glucose:'血糖',systolic:'收缩压',diastolic:'舒张压',tc:'总胆固醇',tg:'甘油三酯',hdl:'高密度脂蛋白',ldl:'低密度脂蛋白'}
const conditions={fasting:'空腹',after_meal_2h:'餐后2小时',random:'随机',same_observation:'同条测量'}
let epoch=0
onLoad(options=>{memberId.value=options.memberId||'';const date=new Date(Date.now()+8*3600000).toISOString().slice(0,10);start.value=date;end.value=date})
function discard(){epoch++;result.value=null;selected.value=[];busy.value=false;error.value=''}
onHide(discard);onUnload(discard)
function change(field,value){discard();field==='kind'?kind.value=value:field==='start'?start.value=value:end.value=value}
async function read(onlySelected=false){
  if(busy.value||!memberId.value)return
  const refs=onlySelected?result.value.records.filter(r=>selected.value.includes(r.record_id)).map(r=>({record_id:r.record_id,version:r.version})):[]
  if(onlySelected&&!refs.length)return
  const mine=++epoch,revision=sessionRevision();busy.value=true;error.value='';result.value=null
  try{const {data}=await request({path:`/api/health/v1/members/${memberId.value}/indicator-reviews/${kind.value}`,method:'POST',data:{start_date:start.value,end_date:end.value,records:refs}});if(mine===epoch&&revision===sessionRevision()){result.value=data;selected.value=[]}}
  catch(e){if(mine===epoch)error.value=e.message}
  finally{if(mine===epoch){if(revision!==sessionRevision())discard();busy.value=false}}
}
function toggle(id){selected.value=selected.value.includes(id)?selected.value.filter(x=>x!==id):[...selected.value,id]}
function consult(){
  if(!result.value?.source_member_id)return
  const task=kind.value+'_review'
  scopedStorage.setStorageSync(`indicator-choice:${memberId.value}:${task}`,result.value.selection)
  uni.navigateTo({url:`/pages/chat/agent?memberId=${encodeURIComponent(memberId.value)}&taskType=${task}&indicatorChoice=1`,fail(){error.value='进入咨询失败，可重试；实测记录未改变。'}})
}
</script>
<template><view class="screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack()">‹</button><text class="nav-title">实测记录回顾</text></view></AppNavBar>
<view class="panel"><text class="display-title">回顾测量事实</text><text class="safe-note">北京时间最多366天；统计原值，不作诊断或个体化建议。</text>
<picker :range="names" :disabled="busy" @change="change('kind',kinds[$event.detail.value])"><view class="field-input">{{names[kinds.indexOf(kind)]}} ›</view></picker>
<text>开始日期</text><picker mode="date" :value="start" :disabled="busy" @change="change('start',$event.detail.value)"><view class="field-input">{{start}} ›</view></picker>
<text>结束日期</text><picker mode="date" :value="end" :disabled="busy" @change="change('end',$event.detail.value)"><view class="field-input">{{end}} ›</view></picker>
<button class="primary-button" :disabled="busy" @click="read()">{{busy?'正在读取…':'读取记录与统计'}}</button><text v-if="error" class="inline-error">{{error}}</text>
<template v-if="result"><text v-if="!result.source_member_id" class="inline-error">尚未关联本人的指标来源，请返回账号页完成本人档案关联。</text><text>范围内 {{result.total}} 条，本次 {{result.records.length}} 条{{result.truncated?'，已截断，请缩短范围':''}}</text><text v-if="result.source_member_id&&!result.records.length" class="safe-note">所选范围没有可用记录，未按零值统计。</text><text class="safe-note">以下统计仅依据本次返回的记录，不代表未返回记录或全天完整情况。</text>
<view v-for="row in result.records" :key="row.record_id" class="card item" @click="toggle(row.record_id)"><text>{{selected.includes(row.record_id)?'☑':'☐'}} {{new Date(row.measured_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}} · {{conditions[row.condition]||'同条测量'}} · v{{row.version}}</text><template v-for="(label,key) in labels" :key="key"><text v-if="row[key]!==undefined">{{label}} {{row[key]}} {{row.unit}}</text></template><text>来源：{{row.source}}</text></view>
<button v-if="result.records.length" class="secondary-button" :disabled="busy||!selected.length" @click="read(true)">仅回顾勾选记录</button>
<view v-for="group in result.review.groups" :key="group.condition" class="card item"><text>{{conditions[group.condition]}}</text><text v-for="(value,key) in group.statistics" :key="key">{{labels[key]}}：{{value.count}}次，均值{{value.mean}}，最低{{value.minimum}}，最高{{value.maximum}} {{result.records[0]?.unit}}</text></view>
<text v-if="result.source_member_id" class="section-title">进一步回顾需补充</text><text v-for="question in result.review.questions" :key="question" class="safe-note">{{question}}</text><text class="safe-note">审核解释尚未请求，暂无引用。咨询仍需独立授权及模型配置。</text><button v-if="result.source_member_id" class="secondary-button" @click="consult">就这个范围进入指标助手</button></template>
</view></view></template>
<style scoped>.panel{display:flex;flex-direction:column;gap:22rpx;margin-top:30rpx}.item{display:flex;flex-direction:column;gap:12rpx;padding:22rpx;font-size:24rpx}.safe-note{text-align:left}.field-input{display:flex;align-items:center}</style>
