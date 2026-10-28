<script setup>
import {newHealthRequestId} from '../../services/health-request-id.js'
import {computed,ref} from 'vue'
import {onLoad,onShow,onHide,onUnload} from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import {request} from '../../services/request.js'
import {sessionRevision} from '../../services/session.js'
import {scopedStorage,storageScope} from '../../services/storage.js'
import {createPreparationClient} from '../../services/preparation-client.js'
import {preparationRoot} from '../../services/onboarding-preparation.js'

const state=ref({status:'preparing',stage:'saving',profile_saved:false}),busy=ref(false)
const steps=[{key:'saving',label:'保存档案',detail:'收好你和家人的饮食资料'},{key:'analyzing',label:'分析饮食需求',detail:'认真核对偏好与饮食限制'},{key:'arranging',label:'准备今日安排',detail:'搭配三餐，并核对餐食详情'}]
const active=computed(()=>state.value.stage==='ready'?3:Math.max(0,steps.findIndex(s=>s.key===state.value.stage)))
const problem=computed(()=>['failed','blocked','stale','connection_error','waiting','submission_error'].includes(state.value.status))
const statusTitle=computed(()=>problem.value?'准备暂时停在这里':active.value===3?'今天的安排，准备好了':steps[active.value].label==='保存档案'?'正在保存档案':active.value===1?'正在分析饮食需求':'正在准备今日安排')
let visible=true,disposed=false,routeId='',scope='',revision='',entering=false
const client=createPreparationClient({send:request,root:preparationRoot,storage:scopedStorage,newId:newHealthRequestId,
  current:()=>visible&&!disposed&&scope===storageScope()&&revision===sessionRevision(),
  onInvalidated(){hide();state.value={status:'connection_error',message:'登录或家庭已变化，请重新进入。'};uni.reLaunch({url:'/pages/index/index'})},
  onSaved(){scopedStorage.setStorageSync('frontend-onboarding-progress-v1',null);scopedStorage.setStorageSync('frontend-onboarding-progress-v1:conflict',null);scopedStorage.setStorageSync('frontend-onboarded-v1',true)},
  onChange(value){state.value=value;if(value.id)routeId=value.id;if(value.profile_saved===true&&!entering){entering=true;uni.reLaunch({url:'/pages/chat/index'})}}
})
async function load(resume=false){
  if(busy.value||disposed)return
  visible=true;scope=storageScope();revision=sessionRevision();busy.value=true
  try{await client.run({body:scopedStorage.getStorageSync('onboarding-preparation-pending'),id:routeId,resume:resume&&state.value.status==='failed'})}
  finally{busy.value=false}
}
function hide(){visible=false;client.stop();busy.value=false}
function archives(){client.stop();uni.navigateTo({url:(['stale','submission_error'].includes(state.value.status)||state.value.error_code==='preparation_policy_changed')?'/pages/onboarding/index':'/pages/profile/index'})}
onLoad(options=>{routeId=options.id||'';void load()})
onShow(()=>{visible=true;void load()})
onHide(hide);onUnload(()=>{disposed=true;hide()})
</script>
<template>
 <view class="preparation-screen">
  <AppNavBar><view class="preparation-nav"><text class="brand-mark">鲜</text><text>家庭营养师</text><text class="nav-note">为每一餐，认真准备</text></view></AppNavBar>
  <view class="kitchen-scene"><image src="/static/food/welcome-kitchen-20261026.jpg" mode="aspectFill"/><view class="scene-shade"/><text class="scene-caption">一日三餐，好好照顾自己</text></view>
  <view class="preparation-content">
   <view class="eyebrow"><view class="warm-dot"/><text>你的专属饮食准备</text></view>
   <text class="preparation-title">{{'好好吃饭，\n从这一餐开始'}}</text>
   <text class="preparation-subtitle">{{'把你的偏好放在心上，\n把适合的三餐安排妥当。'}}</text>
   <view class="preparation-card" role="status" aria-live="polite">
    <view class="current-status"><view class="status-orbit" :class="{paused:problem}"><view/></view><text>{{statusTitle}}</text></view>
    <view class="stage-list"><view v-for="(step,i) in steps" :key="step.key" class="stage-row" :class="{done:i<active,current:i===active}"><view class="stage-indicator">{{i<active?'✓':String(i+1).padStart(2,'0')}}</view><view class="stage-copy"><text>{{step.label}}</text><text>{{i<active?'已完成':step.detail}}</text></view><text v-if="i===active&&!problem" class="stage-working">进行中</text></view></view>
   </view>
   <view v-if="problem" class="preparation-error" role="alert"><text>{{state.message}}</text><button v-if="state.retryable!==false" :disabled="busy" @click="load(true)">{{busy?'正在读取…':state.status==='failed'?'继续准备':'继续查看进度'}}</button><button class="text-button" @click="archives">核对档案与授权</button></view>
   <view class="preparation-note"><view class="note-line"/><text>{{state.profile_saved?'档案已保存，可以进入对话后再准备餐单':'完成准备后，将自动进入对话'}}{{'\n'}}{{state.profile_saved?'暂时离开，也可以回来继续':'正在安全提交本次填写内容'}}</text><view class="note-line"/></view>
  </view>
 </view>
</template>
<style scoped>
.preparation-screen{min-height:100vh;min-height:100dvh;background:#faf8f3;color:#302a24;padding:12rpx 0 calc(env(safe-area-inset-bottom) + 28rpx)}
.preparation-nav{display:flex;align-items:center;gap:14rpx;padding:0 36rpx;font-size:28rpx;font-weight:600;min-height:48px}.brand-mark{display:flex;align-items:center;justify-content:center;width:48rpx;height:48rpx;border-radius:14rpx;background:#a84031;color:#fff;font-family:serif;font-size:29rpx}.nav-note{margin-left:auto;font-size:20rpx;font-weight:400;color:#9a8c7e}
.kitchen-scene{position:relative;height:334rpx;overflow:hidden;margin-top:14rpx}.kitchen-scene image{width:100%;height:100%;object-position:center 48%}.scene-shade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(250,248,243,.03) 45%,#faf8f3 100%)}.scene-caption{position:absolute;bottom:46rpx;left:44rpx;font-size:20rpx;letter-spacing:5rpx;color:#665440}
.preparation-content{position:relative;margin-top:-12rpx;padding:0 44rpx}.eyebrow{display:flex;align-items:center;gap:12rpx;font-size:21rpx;letter-spacing:2rpx;color:#a24634}.warm-dot{height:9rpx;width:9rpx;border-radius:50%;background:#a24634}.preparation-title{white-space:pre-line;display:block;margin-top:20rpx;font-size:53rpx;line-height:1.4;font-weight:600;letter-spacing:2rpx}.preparation-subtitle{white-space:pre-line;display:block;margin-top:18rpx;color:#918475;font-size:25rpx;line-height:1.8}
.preparation-card{margin-top:34rpx;padding:26rpx 28rpx 12rpx;background:#fff;border:1rpx solid #eee8dd;border-radius:26rpx;box-shadow:0 12rpx 38rpx rgba(91,63,32,.025)}.current-status{display:flex;align-items:center;gap:16rpx;padding-bottom:22rpx;border-bottom:1rpx solid #f0ece4;font-size:27rpx;font-weight:500}.status-orbit{width:28rpx;height:28rpx;border:3rpx solid #f2e3d5;border-top-color:#ae4e39;border-radius:50%;animation:preparing-turn 1.3s linear infinite}.status-orbit.paused{animation:none;border-color:#b58b61}.status-orbit>view{height:6rpx;width:6rpx;border-radius:50%;background:#ae4e39;margin:8rpx}.stage-row{display:flex;align-items:center;gap:18rpx;min-height:104rpx;color:#b8afa3}.stage-indicator{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:38rpx;height:38rpx;border:1rpx solid #eee9e0;border-radius:50%;font-size:18rpx}.stage-copy{display:flex;flex-direction:column;gap:6rpx;font-size:25rpx}.stage-copy>text+text{font-size:20rpx;color:#b1a698}.stage-row.current{color:#493b30}.current .stage-indicator{background:#a84b37;border-color:#a84b37;color:#fff}.stage-row.done{color:#827b6c}.done .stage-indicator{color:#71846b;border-color:#e8ede1;background:#f4f6f0}.stage-working{margin-left:auto;font-size:19rpx;color:#a95c43;background:#fbf3e9;padding:7rpx 12rpx;border-radius:7rpx;white-space:nowrap}.preparation-note{white-space:pre-line;display:flex;align-items:center;justify-content:center;gap:16rpx;margin:30rpx 0 10rpx;text-align:center;font-size:20rpx;line-height:1.9;color:#aa9d8d}.note-line{width:24rpx;height:1rpx;background:#d8cdbf}.preparation-error{margin-top:24rpx;color:#8b5d45;font-size:24rpx;line-height:1.8}.preparation-error>text{display:block}.preparation-error button{min-height:46px;margin-top:20rpx;display:flex;align-items:center;justify-content:center;background:#a84b37;color:#fff;border-radius:14rpx;font-size:27rpx}.preparation-error .text-button{background:transparent;color:#837362;font-size:24rpx}
@keyframes preparing-turn{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.status-orbit{animation:none}}@media(max-height:720px){.kitchen-scene{height:230rpx}.preparation-title{font-size:46rpx}.preparation-subtitle{margin-top:12rpx}.preparation-card{margin-top:24rpx}.stage-row{min-height:90rpx}.preparation-note{margin-top:20rpx}}@media(max-width:350px){.preparation-content{padding:0 32rpx}.preparation-nav{padding:0 28rpx}.nav-note{font-size:18rpx}.preparation-card{padding-left:22rpx;padding-right:22rpx}}
</style>
