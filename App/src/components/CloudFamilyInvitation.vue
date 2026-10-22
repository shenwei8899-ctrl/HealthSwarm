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
  const ticket=epoch;busy.value=true;error.value=''
  try{
    if(accept){
      const {data}=await request({path:'/api/family/join',method:'POST',data:{code}})
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
<template><view class="screen invitation-screen"><AppNavBar><view class="nav-row"><text class="nav-title">家庭邀请</text><view/></view></AppNavBar><text v-if="busy" class="safe-note">正在核对邀请…</text><view v-if="error" class="card invitation-card" role="alert"><text>{{error}}</text><button :disabled="busy" @click="load">重新读取邀请</button><button :disabled="busy" @click="leave">暂不处理这份邀请</button></view><view v-if="invitation" class="card invitation-card"><text class="display-title">{{invitation.inviter_name}}邀请你加入家庭</text><text class="section-title">{{invitation.family_name}}</text><text>{{invitation.kind==='member'?'核对并认领「'+invitation.member_name+'」的已有档案，不会重复创建。':'接受后填写并建立你自己的档案。'}}</text><text class="section-title">加入后的共享范围</text><text v-for="line in invitation.sharing" :key="line">{{line}}</text><text>接受前不会展示家庭健康资料。你无需重新选择家庭使用方式或设置全家的默认就餐成员。</text><button class="primary-button" :disabled="busy||!invitation.can_accept" @click="decide(true)">{{invitation.already_accepted?'继续核对本人档案':'确认接受邀请加入家庭'}}</button><button class="secondary-button" :disabled="busy" @click="decide(false)">拒绝邀请</button></view></view></template>
<style scoped>.invitation-card{margin:32rpx 0;padding:30rpx;display:flex;flex-direction:column;gap:24rpx;font-size:27rpx;line-height:1.7}.invitation-card .display-title{font-size:42rpx}</style>
