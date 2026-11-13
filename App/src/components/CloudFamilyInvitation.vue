<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'
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
      const source=invitation.value.switch?.family_id
      const transfer=invitation.value.switch?.transfer
      const data=invitation.value.already_accepted?{id:invitation.value.family_id}:(await request({
        path:'/api/family/join',method:'POST',data:{code,...(source?{expected_family_id:source}:{}),
          ...(transfer?.accepted?{expected_transfer_id:transfer.id}:{})}
      })).data
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
async function proposeTransfer(memberId){
  if(busy.value||invitation.value?.state!=='transfer_required')return
  const ticket=epoch
  const familyId=invitation.value.switch.family_id
  busy.value=true;error.value=''
  try{
    const {data}=await request({
      path:'/api/family/'+encodeURIComponent(familyId)+'/owner-transfer',method:'POST',data:{member_id:memberId}
    })
    if(alive&&ticket===epoch)invitation.value.switch.transfer=data
  }catch(e){if(alive&&ticket===epoch)error.value=e.message}
  finally{if(alive&&ticket===epoch)busy.value=false}
}
onMounted(load);onShow(load)
onHide(()=>{epoch++;invitation.value=null;busy.value=false})
onUnmounted(()=>{alive=false;epoch++})
</script>
<template>
 <view class="screen invitation-screen">
  <view class="invitation-canvas" aria-hidden="true"/>
  <view class="invitation-content">
  <AppNavBar title="家庭邀请"></AppNavBar>
  <text v-if="busy" class="invitation-loading" role="status">正在核对邀请…</text>
  <view v-if="error" class="invitation-notice" role="alert"><text class="notice-title">邀请暂未确认</text><text class="notice-copy">{{error}}</text><button class="primary-button" :disabled="busy" @click="load">重新读取邀请</button><button class="secondary-button" :disabled="busy" @click="leave">暂不处理这份邀请</button></view>
  <view v-if="invitation" class="invitation-card">
   <view class="invitation-heading">
    <view class="invitation-symbol" aria-hidden="true"><AppIcon name="family" :size="56"/></view>
    <text class="invitation-eyebrow">一起照顾每一餐</text>
    <text class="display-title">邀请你加入家庭</text>
   </view>
   <template v-if="invitation.state==='member_conflict'"><view class="invitation-notice"><text class="notice-copy">你已加入该家庭，此邀请对应另一份档案，请联系家庭创建人处理。</text></view></template>
   <template v-else-if="invitation.state==='inactive'"><view class="invitation-notice"><text class="notice-copy">当前家庭关系已停用，请联系家庭创建人。</text></view></template>
   <template v-else-if="invitation.state==='transfer_required'">
    <text class="invitation-description">「{{invitation.switch.family_name}}」还有家人使用。请先选择接手人。</text>
    <button v-for="person in invitation.switch.successors" :key="person.id" class="secondary-button" :disabled="busy" @click="proposeTransfer(person.id)">{{person.name}}{{invitation.switch.transfer?.member_id===person.id?' · 等待确认':''}}</button>
    <button class="primary-button" :disabled="busy" @click="load">重新核对交接状态</button>
   </template>
   <template v-else>
    <text v-if="invitation.already_accepted" class="invitation-description">你已加入该家庭，可以继续核对本人资料或进入家庭。</text>
    <template v-else><text class="invitation-description">{{invitation.kind==='member'?'家人已为你填写「'+invitation.member_name+'」的资料，加入后请核对、补充。':'加入后，请填写你自己的资料。'}}</text><text v-if="invitation.kind==='member'" class="invitation-hint member-hint">如果这不是你的资料，请勿接受，并联系邀请人。</text></template>
    <view class="sharing-card">
     <view class="sharing-heading"><view class="sharing-symbol" aria-hidden="true"><AppIcon name="shield" :size="32"/></view><text class="section-title">加入后的共享范围</text></view>
     <view v-for="(line,index) in invitation.sharing" :key="line" class="sharing-row"><text class="sharing-index" aria-hidden="true">{{index+1<10?'0'+(index+1):index+1}}</text><text class="sharing-copy">{{line}}</text></view>
    </view>
    <view class="invitation-actions">
    <text v-if="invitation.switch" class="invitation-hint">接受后，你本人将离开「{{invitation.switch.family_name}}」并加入新家庭。家人及原家庭档案保留在原处。</text>
    <text v-else class="invitation-hint">接受前不展示健康资料。接受后立即加入，无需家人再次批准。</text>
    <button class="primary-button" :disabled="busy||!invitation.can_accept" @click="decide(true)">{{invitation.already_accepted?'继续进入家庭':invitation.switch?'确认切换家庭':'接受邀请，加入家庭'}}</button>
    </view>
   </template>
   <button class="secondary-button" :disabled="busy" @click="invitation.already_accepted||!invitation.can_accept?leave():decide(false)">{{invitation.already_accepted||!invitation.can_accept?'返回':'暂不加入'}}</button>
  </view>
  </view>
 </view>
</template>
<style scoped>
.invitation-screen{position:relative;min-height:100vh;padding:0 23px calc(env(safe-area-inset-bottom) + 26px);background:transparent;color:#51485f}
.invitation-canvas{position:fixed;inset:0;height:100vh;height:100dvh;pointer-events:none;background:radial-gradient(ellipse at 8% 0%,rgba(255,255,255,.65),transparent 54%),linear-gradient(145deg,#e4e8f9 0%,#eee7f5 48%,#e6f1ed 100%)}
.invitation-content{position:relative;max-width:434px;margin:0 auto}
.invitation-card{margin:12px 0 0}
.invitation-heading{display:flex;flex-direction:column;align-items:center;text-align:center;padding:6px 0 0}
.invitation-symbol{display:flex;align-items:center;justify-content:center;width:64px;height:64px;margin-bottom:15px;border:1px solid rgba(255,255,255,.85);border-radius:22px;background:radial-gradient(circle at 25% 15%,rgba(255,255,255,.9),transparent 65%),linear-gradient(145deg,#e3daf5,#f0eaf8);color:#967db0;box-shadow:inset 0 1px 2px #fff,0 6px 18px rgba(97,80,135,.05)}
.invitation-eyebrow{display:block;margin-bottom:6px;color:#81738f;font-size:12px;font-weight:500;letter-spacing:1px}
.invitation-heading .display-title{font-size:24px;font-weight:600;line-height:1.45;color:#554362}
.invitation-description{display:block;max-width:340px;margin:12px auto 22px;color:#7c6a88;font-size:13px;line-height:1.8;text-align:center;overflow-wrap:anywhere}
.sharing-card{padding:20px 18px 5px;border:1px solid rgba(255,255,255,.8);border-radius:28px;background:linear-gradient(135deg,rgba(255,255,255,.75),rgba(255,255,255,.32) 65%,rgba(232,236,255,.4));box-shadow:inset 0 1px 2px rgba(255,255,255,.8),0 7px 20px rgba(97,80,135,.035)}
.sharing-heading{display:flex;align-items:center;gap:9px;margin-bottom:5px}
.sharing-symbol{display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:9px;background:rgba(154,129,181,.09);color:#89719c;flex:none}
.sharing-heading .section-title{font-size:15px;font-weight:600;color:#63556f}
.sharing-row{display:flex;align-items:flex-start;gap:11px;padding:14px 0;border-top:1px solid rgba(255,255,255,.72)}
.sharing-heading+.sharing-row{border-top:0}
.sharing-index{flex:none;min-width:21px;margin-top:2px;color:#9987ac;font-size:11px;font-weight:500;line-height:1.8}
.sharing-copy{flex:1;min-width:0;color:#756582;font-size:13px;line-height:1.8;overflow-wrap:anywhere}
.invitation-actions{margin-top:18px}
.invitation-hint{display:block;margin:0 5px 14px;color:#897795;font-size:11px;line-height:1.8;text-align:center;overflow-wrap:anywhere}
.member-hint{margin-top:-12px;margin-bottom:20px}
.invitation-screen .primary-button{width:100%;min-height:48px;padding:12px 18px;border:1px solid rgba(255,255,255,.7);border-radius:24px;background:linear-gradient(120deg,#d9c9ee,#e8dcf4);color:#68517e;font-size:15px;font-weight:600;line-height:1.5;box-shadow:inset 0 1px 0 rgba(255,255,255,.65),0 4px 12px rgba(113,85,146,.06)}
.invitation-screen .secondary-button{width:100%;min-height:46px;margin-top:10px;padding:11px 18px;border:1px solid rgba(255,255,255,.72);border-radius:23px;background:linear-gradient(120deg,rgba(255,255,255,.5),rgba(238,231,247,.42));color:#796386;font-size:14px;font-weight:500;line-height:1.5;box-shadow:inset 0 1px 0 rgba(255,255,255,.55)}
.invitation-screen button:active{filter:brightness(.97)}
.invitation-screen button[disabled]{opacity:.45}
.invitation-loading{display:block;margin:24px 0;color:#897795;font-size:12px;text-align:center}
.invitation-notice{margin:24px 0;padding:24px 20px;border:1px solid rgba(255,255,255,.8);border-radius:27px;background:rgba(255,255,255,.6);text-align:center}
.notice-title{display:block;margin-bottom:10px;color:#63556f;font-size:17px;font-weight:600}
.notice-copy{display:block;margin-bottom:20px;color:#7c6a88;font-size:13px;line-height:1.8;overflow-wrap:anywhere}
@media(max-width:350px){.invitation-screen{padding-left:17px;padding-right:17px}.sharing-card{padding-left:15px;padding-right:15px}.invitation-heading .display-title{font-size:22px}}
</style>
