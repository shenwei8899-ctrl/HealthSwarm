<script setup>
import { ref } from 'vue'
import { onShow,onHide,onUnload } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import { request } from '../services/request.js'
import { scopedStorage,storageContext } from '../services/storage.js'
import { newHealthRequestId } from '../services/health-task-flow.js'
const members=ref([]),memberId=ref(''),memories=ref([]),busy=ref(false),error=ref(''),pending=ref(null),truncated=ref(false)
let epoch=0
async function load(id=memberId.value){if(busy.value)return;const mine=++epoch,scope=storageContext();busy.value=true;error.value='';memories.value=[];try{const {data}=await request({path:'/api/health/v1/members'});if(mine!==epoch||scope!==storageContext())return;members.value=data.filter(m=>m.scopes?.includes('ai_use'));memberId.value=members.value.find(m=>m.id===id)?.id||members.value.find(m=>m.is_owner&&m.relationship_label==='本人')?.id||members.value[0]?.id||'';pending.value=scopedStorage.getStorageSync('memory-management-pending')||null;if(!memberId.value)return;const result=(await request({path:'/api/health/v1/members/'+memberId.value+'/memory'})).data;if(mine!==epoch||scope!==storageContext())return;memories.value=result.memories;truncated.value=result.truncated}catch(e){if(mine===epoch){if(scope!==storageContext()||[401,403,404,410].includes(Number(e.code))){hide();error.value='当前授权或来源已变化，请重新读取。'}else error.value=e.message}}finally{if(mine===epoch)busy.value=false}}
async function perform(){if(busy.value||!pending.value)return;const mine=++epoch,scope=storageContext();busy.value=true;error.value='';try{await request(pending.value);if(mine!==epoch||scope!==storageContext())return;scopedStorage.setStorageSync('memory-management-pending',null);pending.value=null}catch(e){if(mine===epoch&&(scope!==storageContext()||[401,403,404,410].includes(Number(e.code)))){hide();error.value='当前授权或来源已变化，请重新读取。'}else if(mine===epoch&&scope===storageContext()){error.value=e.message;if([400,403,404,409,410,422].includes(Number(e.code))){scopedStorage.setStorageSync('memory-management-pending',null);pending.value=null}}}finally{if(mine===epoch)busy.value=false}if(mine===epoch&&!error.value)await load()}
function prepare(item,content,revoke=false){const id=newHealthRequestId();pending.value={path:'/api/health/v1/memory/'+item.memory_id+(revoke?'/revoke':''),method:revoke?'POST':'PATCH',headers:{'Idempotency-Key':id,'If-Match':'"'+item.version+'"'},data:{client_request_id:id,version:item.version,...(revoke?{}:{content,kind:item.kind})}};scopedStorage.setStorageSync('memory-management-pending',pending.value);void perform()}
function edit(item){if(busy.value||pending.value)return;const scope=storageContext();uni.showModal({title:'修改长期记忆',editable:true,content:item.content,success:r=>{if(r.confirm&&r.content?.trim()&&scope===storageContext())prepare(item,r.content.trim())}})}
function remove(item){if(busy.value||pending.value)return;const scope=storageContext();uni.showModal({title:'删除这条记忆？',content:'之后的建议不再引用它；已支付订单不会被改写。',success:r=>{if(r.confirm&&scope===storageContext())prepare(item,'',true)}})}
function hide(){epoch++;members.value=[];memories.value=[];pending.value=null;busy.value=false;error.value=''}
onShow(()=>load());onHide(hide);onUnload(hide)
function memberLabel(member={}){
  const name=member.display_name||member.name||''
  return name&&!/^微信用户[_-]/.test(name)?name:(member.relationship_label==='本人'||member.is_owner?'我':member.relationship_label||'家庭成员')
}
</script>
<template>
<view class="screen mm-page">
<AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="uni.navigateBack()">‹</button><text class="nav-title">AI 记住的事</text></view></AppNavBar>
<view class="mm-hero"><text class="mm-title">让每一次建议，<br/>更懂你一点。</text></view>

<view class="mm-heading"><text>{{memberId?memberLabel(members.find(m=>m.id===memberId))+'的记忆':'已保存的记忆'}}</text><button :disabled="busy||!!pending" aria-label="重新读取记忆" @click="load()">{{busy?'同步中…':'↻ 刷新'}}</button></view>
<view v-if="error||pending" class="card mm-state" role="alert"><text>{{error||'上次修改待确认，请重试同步。'}}</text><button class="mm-primary" :disabled="busy" @click="pending?perform():load()">{{pending?'重试原记忆操作':'重新读取'}}</button></view>
<view v-for="item in memories" :key="item.memory_id" class="card mm-card"><text class="mm-content">{{item.content}}</text><view class="mm-bottom"><text class="mm-label">用户自述</text><view><button :disabled="busy||!!pending" @click="edit(item)">修改</button><button :disabled="busy||!!pending" @click="remove(item)">删除</button></view></view></view>
<view v-if="!memories.length&&!error&&!pending" class="card mm-empty" role="status"><view class="mm-symbol">✦</view><text class="mm-empty-title">{{busy?'正在核对记忆…':memberId?'慢慢了解，认真记住':'暂无可查看的成员'}}</text></view>
<text v-if="truncated&&!busy&&!error" class="safe-note">当前显示前 100 条记忆</text>

</view>
</template>
<style>
.mm-page{background-color:#f5f6fa;background-image:linear-gradient(135deg,#d6e5fe,#e7def8 35%,#f5f6fa 80%);background-size:100% 520rpx;background-repeat:no-repeat;font-family:"PingFang SC","Microsoft YaHei",sans-serif}
.mm-hero{padding:38rpx 8rpx 40rpx}.mm-title{display:block;font-size:48rpx;font-weight:600;line-height:1.5;margin-bottom:20rpx}.mm-primary{background:linear-gradient(135deg,#e2efff,#c9ddfb,#b9cdf3);color:#31588f}
.mm-heading,.mm-bottom,.mm-bottom>view{display:flex;align-items:center;justify-content:space-between;gap:12rpx}.mm-heading{font-size:31rpx;font-weight:500;margin-bottom:16rpx}.mm-heading button,.mm-bottom button{min-height:88rpx;min-width:88rpx;font-size:24rpx;color:#6283b9}.mm-card{padding:30rpx 30rpx 4rpx;margin-bottom:20rpx;border:0}.mm-label{font-size:22rpx;color:#8a99b0}.mm-content{display:block;margin:22rpx 0;white-space:pre-wrap;overflow-wrap:anywhere}.mm-bottom{border-top:1rpx solid #eef1f7}.mm-bottom button:last-child{color:#9b858a}
.mm-state{padding:28rpx;margin-bottom:20rpx;font-size:26rpx;overflow-wrap:anywhere}.mm-primary{min-height:88rpx;margin-top:20rpx;border-radius:24rpx;font-size:26rpx}.mm-empty{text-align:center;padding:44rpx 28rpx;border:0}.mm-symbol{margin-bottom:24rpx;font-size:76rpx;color:#b4a9db}.mm-empty-title{display:block;font-size:31rpx;font-weight:500}</style>
