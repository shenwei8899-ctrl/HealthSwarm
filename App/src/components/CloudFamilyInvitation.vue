<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import { request } from '../services/request.js'
import { wechatAuth } from '../services/wechat-auth.js'
import { getSession } from '../services/session.js'
import { resolveAppEntry } from '../services/app-entry.js'
import { pendingInvitation, rememberInvitation, clearInvitation } from '../services/family-invitations.js'
const props=defineProps({token:String})
const invitation=ref(null),busy=ref(false),error=ref('')
let alive=true,epoch=0,code=''
function leave(){clearInvitation(code);uni.reLaunch({url:'/pages/index/index'})}
async function load(){
  if(busy.value)return
  const ticket=++epoch;busy.value=true;error.value='';invitation.value=null
  try{
    code=rememberInvitation(props.token||pendingInvitation())
    if(!getSession()?.token){uni.reLaunch({url:'/pages/index/index'});return}
    const {data}=await request({path:'/api/family/invitations/'+encodeURIComponent(code)})
    if(alive&&ticket===epoch)invitation.value=data
  }catch(e){if(alive&&ticket===epoch)error.value=e.message}
  finally{if(alive&&ticket===epoch)busy.value=false}
}
async function decide(accept){
  if(busy.value||!invitation.value)return
  if(accept&&!invitation.value.can_accept)return
  const ticket=epoch;busy.value=true;error.value=''
  try{
    if(accept){
      const data=invitation.value.already_accepted?{id:invitation.value.family_id}:(await request({path:'/api/family/join',method:'POST',data:{code}})).data
      if(!alive||ticket!==epoch)return
      await wechatAuth.selectFamily(data.id)
    }else await request({path:'/api/family/invitations/'+encodeURIComponent(code)+'/decline',method:'POST'})
    if(!alive||ticket!==epoch)return
    clearInvitation(code)
    const url=await resolveAppEntry()
    if(alive&&ticket===epoch)uni.reLaunch({url})
  }catch(e){if(alive&&ticket===epoch)error.value=e.code==='NETWORK_ERROR'?'操作结果尚未确认，请重新读取邀请；系统会核对原加入结果，不会重复创建档案。':e.message}
  finally{if(alive&&ticket===epoch)busy.value=false}
}
onMounted(load);onShow(load)
onHide(()=>{epoch++;invitation.value=null;busy.value=false})
onUnmounted(()=>{alive=false;epoch++})
</script>
<template>
 <view class="screen invitation-screen">
  <AppNavBar><view class="nav-row"><text class="nav-title">家庭邀请</text><view/></view></AppNavBar>
  <text v-if="busy" class="safe-note" role="status">正在核对邀请…</text>
  <view v-if="error" class="card invitation-card" role="alert"><text>{{error}}</text><button :disabled="busy" @click="load">重新读取邀请</button><button :disabled="busy" @click="leave">暂不处理这份邀请</button></view>
  <view v-if="invitation" class="card invitation-card">
   <text class="display-title">邀请你加入家庭</text>
   <template v-if="invitation.state==='member_conflict'"><text>你已加入该家庭，此邀请对应另一份档案，请联系家庭创建人处理。</text></template>
   <template v-else-if="invitation.state==='inactive'"><text>当前家庭关系已停用，请联系家庭创建人。</text></template>
   <template v-else>
    <text v-if="invitation.already_accepted">你已加入该家庭，可以继续核对本人资料或进入家庭。</text>
    <template v-else><text>{{invitation.kind==='member'?'家人已为你填写「'+invitation.member_name+'」的资料，加入后请核对、补充。':'加入后，请填写你自己的资料。'}}</text><text v-if="invitation.kind==='member'" class="invitation-hint">如果这不是你的资料，请勿接受，并联系邀请人。</text></template>
    <text class="section-title">加入后的共享范围</text><text v-for="line in invitation.sharing" :key="line">{{line}}</text>
    <text class="invitation-hint">接受前不展示健康资料。接受后立即加入，无需家人再次批准。</text>
    <button class="primary-button" :disabled="busy||!invitation.can_accept" @click="decide(true)">{{invitation.already_accepted?'继续进入家庭':'接受邀请，加入家庭'}}</button>
   </template>
   <button class="secondary-button" :disabled="busy" @click="invitation.already_accepted||!invitation.can_accept?leave():decide(false)">{{invitation.already_accepted||!invitation.can_accept?'返回':'暂不加入'}}</button>
  </view>
 </view>
</template>
<style scoped>.invitation-card{margin:32rpx 0;padding:30rpx;display:flex;flex-direction:column;gap:24rpx;font-size:27rpx;line-height:1.7}.invitation-card .display-title{font-size:42rpx}.invitation-hint{color:#8c8295;font-size:23rpx}</style>
