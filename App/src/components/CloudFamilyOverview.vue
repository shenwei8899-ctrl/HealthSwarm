<script setup>
import {ref,computed,onMounted,onUnmounted} from 'vue'
import {onShow,onHide,onBackPress} from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import FamilyMemberDeck from './FamilyMemberDeck.vue'
import CloudMemberDetail from './CloudMemberDetail.vue'
import {loadCloudProfile} from '../services/cloud-profile.js'
import {storageContext} from '../services/storage.js'
import {getSession} from '../services/session.js'
const profile=ref(null),error=ref(''),busy=ref(false),profileContext=ref(''),selectedId=ref('')
const owner=computed(()=>profile.value?.isOwner===true)
const sheetId=ref(''),sheetName=ref(''),sheetSection=ref('basic'),sheetDetail=ref(null),sheetClosing=ref(false),sheetExpanded=ref(false)
let sheetContext='',sheetTimer=null,dragStart=null
let epoch=0,remembered=null
async function load(){
 if(busy.value)return
 const mine=++epoch,context=storageContext()
 busy.value=true;error.value='';profile.value=null;profileContext.value=''
 try{
  const result=await loadCloudProfile({openConsultation:false,readConfiguration:false})
  if(mine!==epoch)return
  if(context!==storageContext()||result.householdId!==getSession()?.householdId){error.value='账号或家庭已变化，请重新读取。';return}
  selectedId.value=remembered?.context===context&&result.members.some(m=>String(m.id)===remembered.memberId)?remembered.memberId:String(result.selfMemberId||result.members[0]?.id||'')
  profileContext.value=context;profile.value=result
 }catch(e){if(mine===epoch)error.value=e.message}
 finally{if(mine===epoch)busy.value=false}
}
function select(id){if(profileContext.value!==storageContext()){discard();return}selectedId.value=String(id);remembered={context:profileContext.value,memberId:String(id)}}
function discard(){epoch++;profile.value=null;profileContext.value='';busy.value=false;error.value=''}
function detail(member,section='basic'){if(!profile.value||profileContext.value!==storageContext()){discard();return}if(!profile.value.members.some(m=>String(m.id)===String(member.id)))return;select(member.id);sheetContext=profileContext.value;sheetName.value=member.name;sheetSection.value=['health','preferences','restrictions'].includes(section)?section:'basic';sheetClosing.value=false;sheetExpanded.value=false;sheetId.value=String(member.id)}
function clearSheet(){clearTimeout(sheetTimer);sheetId.value='';sheetContext='';sheetClosing.value=false}
function requestSheetClose(){if(!sheetClosing.value)sheetDetail.value?.requestClose?.()}
function closeSheet(){if(sheetClosing.value)return;sheetClosing.value=true;sheetTimer=setTimeout(()=>{clearSheet();void refreshCard()},240)}
function updateSaved(next){if(sheetContext===storageContext()&&next?.householdId===profile.value?.householdId){profile.value=next;sheetName.value=next.members.find(m=>String(m.id)===sheetId.value)?.name||sheetName.value}}
async function refreshCard(){const ticket=epoch,context=storageContext();try{const next=await loadCloudProfile({openConsultation:false,readConfiguration:false});if(ticket===epoch&&context===storageContext()&&next.householdId===profile.value?.householdId)profile.value=next}catch(e){if(ticket===epoch&&[401,403,404,410].includes(Number(e.code)))discard()}}
function beginDrag(event){const p=event.touches?.[0];dragStart=p?{x:p.clientX,y:p.clientY}:null}
function endDrag(event){const p=event.changedTouches?.[0],start=dragStart;dragStart=null;if(!p||!start)return;const dy=p.clientY-start.y;if(Math.abs(dy)<50||Math.abs(dy)<Math.abs(p.clientX-start.x)*1.4)return;if(dy>0)requestSheetClose();else sheetExpanded.value=true}
function manage(){if(owner.value&&profileContext.value===storageContext())uni.navigateTo({url:'/pages/onboarding/index'})}
onMounted(load);onShow(()=>{if(sheetId.value&&sheetContext!==storageContext())clearSheet();void load()});onHide(discard)
onBackPress(()=>{if(sheetId.value){requestSheetClose();return true}return false})
onUnmounted(()=>{remembered=null;clearSheet();discard()})
</script>
<template>
 <view class="screen family-overview">
  <view class="family-canvas" aria-hidden="true"/>
  <view class="family-content" :class="{'sheet-open':sheetId}">
   <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/chat/index'})})">‹</button><text class="nav-title">家庭健康档案</text><text/></view></AppNavBar>
   <view class="family-heading"><view class="family-summary"><text class="family-name">{{profile?.householdName||'我的家'}}</text><text class="family-eyebrow">把家人的健康，放在心上</text><text v-if="profile" class="family-count">{{profile.members.length}} 位家人，各有一份专属档案</text></view><button class="switch-family" @click="uni.navigateTo({url:'/pages/family-select/index'})">切换家庭 <text>›</text></button></view>
   <view v-if="busy" class="family-loading" role="status"><view class="loading-tabs"/><view class="loading-card"><view class="loading-avatar"/><view class="loading-line"/><view class="loading-line short"/></view><text>正在读取家庭档案…</text></view>
   <view v-else-if="error" class="family-notice" role="alert"><view class="notice-symbol" aria-hidden="true">↻</view><text class="notice-title">家庭档案暂未读取</text><text class="notice-copy">{{error}}</text><button class="retry-button" @click="load">重新读取</button><button class="choose-family" @click="uni.navigateTo({url:'/pages/family-select/index'})">选择家庭 ›</button></view>
   <template v-else-if="profile">
    <FamilyMemberDeck v-if="profile.members.length" :members="profile.members" :scope="profileContext" :self-id="profile.selfMemberId" :preferred-id="selectedId" :can-manage="owner" @selected="select" @open="detail" @manage="manage"/>
    <view v-else class="family-notice"><text class="notice-title">先为家人留一个位置</text><text class="notice-copy">添加成员后，就能查看每位家人的健康档案。</text></view>
   </template>
  </view>
  <view v-if="sheetId" class="archive-sheet-mask" :class="{'is-closing':sheetClosing}">
   <view class="archive-sheet-backdrop" aria-hidden="true" @click="requestSheetClose" @touchmove.stop.prevent @wheel.prevent/>
   <view class="archive-sheet-window" :class="{'is-expanded':sheetExpanded}" role="dialog" aria-modal="true" :aria-label="sheetName+'的健康档案'">
    <view class="archive-sheet-hero" @touchstart="beginDrag" @touchend="endDrag"><view class="sheet-grab"/><text class="sheet-title">健康档案</text><text class="sheet-person">{{sheetName}}</text><image class="sheet-assistant" src="/static/chat/nutrition-boy-v2-poster.png" mode="aspectFit" aria-hidden="true"/><button class="sheet-close" aria-label="关闭档案面板" @click.stop="requestSheetClose">×</button></view>
    <view class="sheet-detail"><CloudMemberDetail ref="sheetDetail" :key="sheetId" :id="sheetId" :initial-section="sheetSection" embedded @close="closeSheet" @saved="updateSaved"/></view>
   </view>
  </view>
 </view>
</template>
<style scoped>
.archive-sheet-backdrop{position:absolute;inset:0}
.family-overview{--archive-canvas:linear-gradient(180deg,#d6e1fd 0%,#e8edff 42%,#edf0ff 70%);--ui-text:#343546;position:relative;min-height:100vh;padding:0 21px calc(env(safe-area-inset-bottom) + 28px);background:transparent;color:var(--ui-text)}.family-canvas{position:fixed;inset:0;z-index:0;height:100vh;height:100dvh;background:var(--archive-canvas);pointer-events:none}.family-content{position:relative;z-index:1;max-width:440px;margin:0 auto}.icon-button{min-width:44px;min-height:44px;margin-left:-9px;color:#645b70}
.family-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:18px 1px 20px}.family-summary{flex:1;min-width:0}.family-eyebrow{display:block;margin-top:7px;color:#7e829a;font-size:10px;line-height:1.8;letter-spacing:.5px}.family-name{display:block;margin-top:0;font-size:27px;line-height:1.4;font-weight:600;overflow-wrap:anywhere;color:#494052}.family-count{display:block;margin-top:4px;color:#7e829a;font-size:11px;line-height:1.6}.switch-family{display:flex;align-items:center;gap:5px;flex:none;min-height:44px;padding:0 1px;color:#7466a2;font-size:11px;line-height:1.5}.switch-family:after{border:0}.switch-family>text{font-size:19px;color:#a596b1}
.manage-members{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:49px;margin:3px 0 0;padding:10px 18px;border:1px solid rgba(255,255,255,.95);border-radius:16px;background:rgba(255,255,255,.61);color:#84718f;font-size:12px;line-height:1.5}.manage-members:after{border:0}.manage-members>text+text{font-size:20px;color:#b09dbd}.family-footnote{display:block;margin:19px 0 0;text-align:center;color:#7e829a;font-size:10px;line-height:1.8}
.family-notice{display:flex;flex-direction:column;align-items:center;margin:35px 0 28px;padding:34px 22px 24px;border-radius:27px;border:1px solid rgba(255,255,255,.94);background:rgba(255,255,255,.84);text-align:center}.notice-symbol{display:flex;align-items:center;justify-content:center;width:49px;height:49px;margin-bottom:18px;border-radius:50%;background:#f1edf8;color:#a08ab6;font-size:26px}.notice-title{display:block;color:#63556f;font-size:16px;line-height:1.6}.notice-copy{display:block;margin-top:10px;color:#8d7f98;font-size:12px;line-height:1.8}.retry-button{width:100%;min-height:46px;margin-top:25px;border-radius:14px;background:#ede7f5;color:#78618f;font-size:13px;line-height:1.5}.retry-button:after,.choose-family:after{border:0}.choose-family{min-height:44px;margin-top:9px;color:#9989a7;font-size:12px}
.family-loading{padding:6px 8px 18px;text-align:center;color:#958a9f;font-size:12px}.loading-tabs{width:160px;height:43px;margin-bottom:27px;border-radius:15px;background:rgba(255,255,255,.65)}.loading-card{height:382px;padding:45px 25px;margin:0 18px 22px 0;border:1px solid rgba(255,255,255,.85);border-radius:29px;background:rgba(255,255,255,.7);transform:rotate(1.2deg)}.loading-avatar{width:60px;height:60px;margin-bottom:40px;border-radius:50%;background:#ece7f4}.loading-line{height:14px;margin-top:20px;border-radius:8px;background:#f0ecf6}.loading-line.short{width:65%}
@media(min-width:520px){.family-overview{padding-top:10px}}@media(max-width:350px){.family-overview{padding-left:17px;padding-right:17px}.family-name{font-size:25px}.family-heading{gap:8px}.family-count{font-size:10px}}
.sheet-open{pointer-events:none}
.archive-sheet-mask{position:fixed;inset:0;z-index:180;display:flex;align-items:flex-end;animation:archive-mask-in .3s ease both}.archive-sheet-window{position:relative;display:flex;flex-direction:column;width:100%;height:84vh;height:84dvh;max-height:calc(100vh - 72px);max-width:480px;margin:0 auto;background:var(--archive-canvas);border-radius:29px 29px 0 0;overflow:hidden;box-shadow:0 -12px 45px rgba(65,57,109,.1);animation:archive-sheet-in .38s cubic-bezier(.22,1,.36,1) both;transition:height .24s ease}.archive-sheet-window.is-expanded{height:92vh;height:92dvh}.archive-sheet-hero{position:relative;flex:none;height:86px;padding:21px 120px 9px 23px}.sheet-grab{position:absolute;left:50%;top:7px;width:32px;height:4px;border-radius:99px;background:#b6add4;transform:translateX(-50%)}.sheet-title{display:block;font-size:19px;line-height:1.5;font-weight:600;color:#39364d}.sheet-person{display:block;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px;font-weight:500;color:#7d7297}.sheet-assistant{position:absolute;right:48px;bottom:-5px;width:80px;height:88px;z-index:1;pointer-events:none}.sheet-close{position:absolute;right:12px;top:13px;display:flex;align-items:center;justify-content:center;width:44px;height:44px;border-radius:50%;font-size:28px;color:#7c6c9d;background:rgba(255,255,255,.55)}.sheet-close:after{border:0}.sheet-detail{display:flex;flex-direction:column;flex:1;min-height:0;width:100%;height:0}.is-closing{animation:archive-mask-out .24s ease both}.is-closing .archive-sheet-window{animation:archive-sheet-out .24s ease both}@keyframes archive-mask-in{from{background:transparent}to{background:rgba(49,51,86,.2)}}@keyframes archive-mask-out{to{background:transparent}}@keyframes archive-sheet-in{from{transform:translateY(100%)}to{transform:translateY(0)}}@keyframes archive-sheet-out{to{transform:translateY(100%)}}@media(prefers-reduced-motion:reduce){.archive-sheet-mask,.archive-sheet-window,.is-closing .archive-sheet-window{animation-duration:1ms;transition:none}}
</style>
