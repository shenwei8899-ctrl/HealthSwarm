<script setup>
import {ref,watch,nextTick,onMounted,onUnmounted,getCurrentInstance} from 'vue'
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'

const props=defineProps({historyOpen:Boolean, followBottom:Boolean, latestAvailable:Boolean, scrollLocked:Boolean, scrollTarget: String, voiceBusy: Boolean, entryTransition: Boolean,
  welcomeMounted: Boolean, welcomeLeaving: Boolean, transitionTicket: Number,
  keyboardOpen: Boolean, viewportStyle: Object })
const conversationTop=ref(0),restoreTop=ref(0)
const emit=defineEmits(['history','profile','shortcut','welcomeFinished','readingChange','latest'])
const instance=getCurrentInstance()
let savedTop=0,userScrolling=false,following=true,measureTimer=null,measureRead=false,layoutGeneration=0,alive=true
function publish(){emit('readingChange',{following,scrollTop:conversationTop.value})}
/** 只量布局节点，不把正文内容交给滚动控制器。 */
function measure(recompute=false){
 measureRead=measureRead||recompute
 if(measureTimer!==null)return
 measureTimer=setTimeout(()=>{
  measureTimer=null;const read=measureRead;measureRead=false;const ticket=layoutGeneration
  if(!alive||props.scrollLocked)return
  const query=uni.createSelectorQuery().in(instance.proxy)
  query.select('.conversation').boundingClientRect();query.select('#chat-bottom-anchor').boundingClientRect()
  query.exec(rects=>{if(!alive||ticket!==layoutGeneration||props.scrollLocked)return;if(read&&rects[0]&&rects[1])following=rects[1].bottom-rects[0].bottom<=48;publish()})
 },60)
}
watch(()=>props.scrollLocked,async locked=>{
 const ticket=++layoutGeneration;userScrolling=false
 if(locked){savedTop=conversationTop.value;return}
 restoreTop.value=-1;await nextTick();if(!alive||ticket!==layoutGeneration||props.scrollLocked)return
 restoreTop.value=savedTop;await nextTick();if(ticket===layoutGeneration)measure(true)
})
watch(()=>props.followBottom,value=>{following=value!==false;if(following)userScrolling=false})
watch(()=>props.scrollTarget,target=>{if(target&&props.followBottom!==false)userScrolling=false})
watch(()=>props.viewportStyle?.height,()=>{userScrolling=false;measure()},{flush:'post'})
function beginRead(event){layoutGeneration++;userScrolling=true;if(event?.deltaY<0){following=false;publish()}}
function rememberScroll(event){
 if(props.scrollLocked)return
 const top=event.detail.scrollTop
 if(userScrolling&&top<conversationTop.value-2){following=false;publish()}
 conversationTop.value=top
 if(userScrolling)measure(true)
}
onMounted(()=>measure())
onUnmounted(()=>{alive=false;layoutGeneration++;clearTimeout(measureTimer)})

const shortcuts = [
  { key: 'plans', icon: 'calendar', name: 'AI专属计划' },
  { key: 'family', icon: 'family', name: '家庭档案' },
  { key: 'camera', icon: 'camera', name: '拍照记餐' },
  { key: 'today', icon: 'record', name: '今日餐单' },
  { key: 'community', icon: 'chat', name: '加入社群' },
]
function choose(key){emit('shortcut',key)}
function openProfile(){emit('profile')}
function finishWelcome(event){
 const name=event.animationName||event.detail?.animationName||''
 if(!props.welcomeLeaving||event.target?.id!==event.currentTarget?.id||name&&!name.startsWith('welcome-leave'))return
 emit('welcomeFinished',props.transitionTicket)
}
</script>
<template>
 <view class="screen nutritionist-layout chat-screen" :class="{'voice-is-busy':voiceBusy,'entry-transition':entryTransition,'keyboard-open':entryTransition&&keyboardOpen}" :style="entryTransition?viewportStyle:null">
  <AppNavBar capsule-aligned><view class="nav-row chat-nav">
   <button class="history-button" aria-label="打开对话列表" :aria-expanded="historyOpen" :disabled="voiceBusy" @click="$emit('history')"><view class="header-entry-icon" aria-hidden="true"><image class="history-entry-icon" src="/static/chat/history.png" mode="aspectFit"/></view></button>
   <view class="assistant-title"><text>家庭营养师</text></view>
   <button class="profile-button" aria-label="我的" :disabled="voiceBusy" @click="openProfile"><view class="header-entry-icon" aria-hidden="true"><view class="profile-entry-glyph"><view class="profile-entry-head"/><view class="profile-entry-body"/></view></view></button>
  </view></AppNavBar>
  <view class="conversation-stage" :class="{'edge-fades':!welcomeMounted,'has-scrolled':conversationTop>2}">
   <scroll-view class="conversation" :class="{'awaiting-welcome':entryTransition&&welcomeLeaving}" :scroll-y="!scrollLocked" :scroll-top="restoreTop" @scroll="rememberScroll" @touchstart="beginRead" @wheel="beginRead" :show-scrollbar="false" :scroll-into-view="scrollTarget"><slot/><view id="chat-bottom-anchor" class="conversation-spacer"/></scroll-view>
   <scroll-view v-if="entryTransition&&welcomeMounted" :key="transitionTicket" id="chat-welcome-layer" class="welcome-layer" :class="{'is-leaving':welcomeLeaving}" :scroll-y="!welcomeLeaving" :show-scrollbar="false" :aria-hidden="welcomeLeaving" @animationend="finishWelcome"><slot name="welcome"/></scroll-view>
   <button v-if="latestAvailable&&!scrollLocked" class="latest-reply-button" aria-label="查看最新回复" @click="$emit('latest')"><text>↓</text> 查看最新回复</button>
  </view>
  <view class="composer-wrap">
   <view class="shortcut-reveal">
   <scroll-view class="shortcut-scroll" scroll-x :show-scrollbar="false">
   <view class="bottom-shortcuts" role="group" aria-label="常用功能">
    <button v-for="item in shortcuts" :key="item.key" class="shortcut-button" :aria-label="item.name" :disabled="voiceBusy" @click="choose(item.key)"><AppIcon :name="item.icon" :size="34"/><text>{{item.name}}</text></button>
   </view>
   </scroll-view>
   </view>
   <slot name="composer"/>
  </view>
  <slot name="overlays"/>
 </view>
</template>
<style scoped>
.nutritionist-layout.chat-screen{height:100vh;height:100dvh;display:flex;flex-direction:column;background:var(--ui-canvas-gradient);color:var(--ui-text);padding:6px 16px calc(env(safe-area-inset-bottom) + 10px);box-sizing:border-box;overflow:hidden}
.chat-nav{display:flex;align-items:center;justify-content:space-between;flex-shrink:0;gap:8px;position:relative;min-height:48px}.history-button,.profile-button{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:44px;min-width:44px;height:44px;min-height:44px;color:#64606f;background:transparent;padding:0;border-radius:50%}.history-button:after,.profile-button:after{border:0}.history-button{margin-left:-8px}.profile-button{margin-right:-8px;margin-left:auto}.history-entry-icon{display:block;width:27px;height:27px;opacity:.66}.assistant-title{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);max-width:calc(100vw - 160px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:18px;font-weight:500;line-height:1.4;pointer-events:none}
.header-entry-icon{display:flex;align-items:center;justify-content:center;flex:0 0 28px;width:28px;height:28px;font-size:0;line-height:0}.profile-entry-glyph{position:relative;display:block;width:19px;height:23px}.profile-entry-head,.profile-entry-body{position:absolute;display:block;box-sizing:border-box;border:1.6px solid currentColor}.profile-entry-head{top:0;left:5px;width:9px;height:9px;border-radius:50%}.profile-entry-body{bottom:0;left:0;width:19px;height:11px;border-radius:50% 50% 25% 25%}
.conversation-stage{position:relative;flex:1;min-height:0}
/* Keep the curtains outside the scrolling content and below the latest-reply control. */
.edge-fades:before,.edge-fades:after{content:'';position:absolute;left:0;right:0;z-index:2;pointer-events:none}
.edge-fades.has-scrolled:before{top:0;height:28px;background:linear-gradient(180deg,#f1f3fb,rgba(241,243,251,0))}
.edge-fades:after{bottom:0;height:28px;background:linear-gradient(0deg,#eef0f8,rgba(238,240,248,0))}
.conversation{height:100%;width:100%}.conversation :deep(.uni-scroll-view),.shortcut-scroll :deep(.uni-scroll-view){scrollbar-width:none}.conversation :deep(.uni-scroll-view::-webkit-scrollbar),.shortcut-scroll :deep(.uni-scroll-view::-webkit-scrollbar){display:none}.conversation-spacer{height:40px}.composer-wrap{flex-shrink:0;padding-top:10px;border:0}.voice-is-busy .conversation{opacity:.35;pointer-events:none}
.welcome-layer{position:absolute;inset:0;z-index:1;background:transparent;animation:welcome-appear 180ms ease-out both}.welcome-layer.is-leaving{pointer-events:none;animation:welcome-leave 260ms ease-out both}.awaiting-welcome{visibility:hidden}.shortcut-reveal{height:50px;opacity:1;overflow:hidden}.nutritionist-layout.entry-transition{min-height:0}.nutritionist-layout.keyboard-open{padding-bottom:10px}
.shortcut-scroll{width:100%;height:44px;margin-bottom:6px;white-space:nowrap}.bottom-shortcuts{display:inline-flex;align-items:center;gap:8px;min-width:100%;height:44px;vertical-align:top;white-space:nowrap}.shortcut-button{position:relative;display:inline-flex;flex:0 0 auto;align-items:center;justify-content:center;gap:6px;height:44px;min-height:44px;margin:0;padding:0 13px;border:0;border-radius:999px;background:transparent;color:#686371;font-size:13px;font-weight:400;line-height:1.4;white-space:nowrap;box-shadow:none}.shortcut-button:before{content:'';position:absolute;inset:4px 0;border-radius:999px;background:var(--ui-surface);pointer-events:none}.shortcut-button:after{border:0}.shortcut-button>text,.shortcut-button :deep(.app-icon){position:relative;flex-shrink:0}.shortcut-button:active:before{background:var(--ui-accent-soft)}.shortcut-button[disabled]{opacity:.5}.profile-button:active,.history-button:active{background:var(--ui-accent-soft)}
.latest-reply-button{position:absolute;right:4px;bottom:10px;display:flex;align-items:center;gap:7px;min-height:44px;margin:0;padding:0 15px;border:0;border-radius:999px;background:var(--ui-surface);color:var(--ui-accent);box-shadow:0 3px 16px rgba(45,36,72,.06);font-size:13px;z-index:3}.latest-reply-button:after{border:0}.latest-reply-button>text{font-size:19px}
@keyframes welcome-leave{from{opacity:1}to{opacity:0}}@keyframes welcome-appear{from{opacity:0}to{opacity:1}}@media(prefers-reduced-motion:reduce){.welcome-layer,.welcome-layer.is-leaving{animation-duration:1ms}}
/* #ifdef MP-WEIXIN */
.nutritionist-layout.chat-screen{padding-top:0;padding-left:20px;padding-right:20px}.nav-row.chat-nav{height:44px;min-height:44px}.chat-nav .history-button{position:absolute;left:-10px;top:0;margin:0}.chat-nav .profile-button{position:absolute;right:var(--chat-profile-right,81px);top:0;margin:0}.chat-nav .assistant-title{left:var(--chat-title-left,50%);font-size:var(--chat-title-font,18px);max-width:none}
@media(max-width:350px){.nutritionist-layout.chat-screen{padding-left:16px;padding-right:16px}}
/* #endif */
</style>
