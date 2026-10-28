<script setup>
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'

const props=defineProps({ scrollTarget: String, voiceBusy: Boolean, historyOpen: Boolean, showShortcuts: { type: Boolean, default: true } })
const emit=defineEmits(['history', 'profile', 'shortcut'])
const shortcuts = [
  { key: 'plans', icon: 'calendar', name: 'AI专属计划' },
  { key: 'family', icon: 'family', name: '家庭档案' },
  { key: 'camera', icon: 'camera', name: '拍照记餐' },
  { key: 'today', icon: 'record', name: '今日餐单' },
  { key: 'community', icon: 'chat', name: '加入社群' },
]
function choose(key){emit('shortcut',key)}
function openProfile(){emit('profile')}
</script>
<template>
 <view class="screen nutritionist-layout chat-screen" :class="{'voice-is-busy':voiceBusy}">
  <AppNavBar capsule-aligned><view class="nav-row chat-nav">
   <button class="history-button" aria-label="打开对话列表" :aria-expanded="historyOpen" :disabled="voiceBusy" @click="$emit('history')"><view class="conversation-menu-icon" aria-hidden="true"><view/><view/></view></button>
   <view class="assistant-title"><text>家庭营养师</text></view>
   <button class="profile-button" aria-label="我的" :disabled="voiceBusy" @click="openProfile"><AppIcon name="user" :size="40"/></button>
  </view></AppNavBar>
  <scroll-view class="conversation" scroll-y :show-scrollbar="false" :scroll-into-view="scrollTarget"><slot/><view class="conversation-spacer"/></scroll-view>
  <view class="composer-wrap">
   <scroll-view v-if="props.showShortcuts" class="shortcut-scroll" scroll-x :show-scrollbar="false">
   <view class="bottom-shortcuts" role="group" aria-label="常用功能">
    <button v-for="item in shortcuts" :key="item.key" class="shortcut-button" :class="'shortcut-'+item.key" :aria-label="item.name" :disabled="voiceBusy" @click="choose(item.key)"><view class="shortcut-symbol" aria-hidden="true"><AppIcon :name="item.icon" :size="46"/></view><text>{{item.name}}</text></button>
   </view>
   </scroll-view>
   <slot name="composer"/>
  </view>
  <slot name="overlays"/>
 </view>
</template>
<style scoped>

.conversation-menu-icon{position:relative;z-index:1;display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:5px;width:18px;height:22px}.conversation-menu-icon>view{width:18px;height:2px;border-radius:2px;background:currentColor}.conversation-menu-icon>view+view{width:12px}
.nutritionist-layout.chat-screen{height:100vh;height:100dvh;display:flex;flex-direction:column;background:radial-gradient(ellipse at 12% 0%,rgba(188,213,255,.35),transparent 44%),linear-gradient(165deg,#e0e5fd 0%,#ecf0ff 40%,#ecf0ff 100%);color:#252637;padding:6px 14px calc(env(safe-area-inset-bottom) + 8px);box-sizing:border-box;overflow:hidden}
.chat-nav{display:flex;align-items:center;justify-content:space-between;flex-shrink:0;gap:8px;position:relative;min-height:48px;margin:0 6px}.history-button,.profile-button{position:relative;display:flex;align-items:center;justify-content:center;flex-shrink:0;width:44px;min-width:44px;height:44px;min-height:44px;color:#303343;background:transparent;padding:0;border-radius:50%}.history-button:before,.profile-button:before{content:'';position:absolute;inset:4px;border-radius:50%;background:rgba(255,255,255,.65);box-shadow:0 1px 8px rgba(255,255,255,.25)}.history-button:after,.profile-button:after{border:0}.history-button{margin:0 0 0 -10px}.profile-button{margin:0 -10px 0 auto}.profile-button :deep(.app-icon){position:relative;z-index:1}.assistant-title{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);max-width:calc(100vw - 160px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:18px;font-weight:500;letter-spacing:.2px;line-height:1.4;pointer-events:none;color:#36344c}
.conversation{flex:1;min-height:0;width:100%;box-sizing:border-box;padding:0 6px}.conversation :deep(.uni-scroll-view){scrollbar-width:none}.conversation :deep(.uni-scroll-view::-webkit-scrollbar){display:none}.conversation-spacer{height:16px}.composer-wrap{flex-shrink:0;background:transparent;padding-top:6px;border:0}.voice-is-busy .conversation{opacity:.35;pointer-events:none}
.shortcut-scroll{width:100%;height:82px;margin-bottom:8px;white-space:nowrap}.shortcut-scroll :deep(.uni-scroll-view){scrollbar-width:none}.shortcut-scroll :deep(.uni-scroll-view::-webkit-scrollbar){display:none}.bottom-shortcuts{display:inline-flex;align-items:center;gap:9px;min-width:100%;height:80px;vertical-align:top;white-space:nowrap;padding-right:3px}
.shortcut-button{display:inline-flex;flex:0 0 auto;flex-direction:column;align-items:center;justify-content:center;gap:5px;width:70px;min-width:70px;height:72px;min-height:72px;box-sizing:border-box;margin:0;padding:6px 2px;border:1px solid rgba(255,255,255,.8);border-radius:14px;background:linear-gradient(155deg,rgba(255,255,255,.4),rgba(255,255,255,.82));color:#454252;font-size:11px;font-weight:400;line-height:1.4;text-align:center;white-space:nowrap;box-shadow:0 2px 6px rgba(164,161,207,.03)}.shortcut-button:after{border:0}.shortcut-button>text{display:block;flex-shrink:0;white-space:nowrap}
.shortcut-symbol{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:33px;height:33px;border-radius:10px;color:#fff;background:linear-gradient(140deg,#c3a4ff,#8557ed);box-shadow:inset 1px 1px 1px rgba(255,255,255,.7),0 4px 7px rgba(123,84,216,.2);transform:rotate(-7deg)}.shortcut-symbol :deep(.app-icon){width:22px!important;height:22px!important;transform:rotate(7deg)}
.shortcut-family .shortcut-symbol{background:linear-gradient(140deg,#ffcb91,#f27350);box-shadow:inset 1px 1px 1px rgba(255,255,255,.7),0 4px 7px rgba(232,136,76,.18);transform:rotate(7deg)}.shortcut-camera .shortcut-symbol{background:linear-gradient(140deg,#ffdc85,#ed9e35);box-shadow:inset 1px 1px 1px rgba(255,255,255,.7),0 4px 7px rgba(226,160,62,.18)}.shortcut-today .shortcut-symbol{background:linear-gradient(140deg,#a0e5d1,#46b69f);box-shadow:inset 1px 1px 1px rgba(255,255,255,.7),0 4px 7px rgba(66,167,144,.18);transform:rotate(7deg)}.shortcut-community .shortcut-symbol{background:linear-gradient(140deg,#c8bbff,#8d6ce9)}
.shortcut-button:active{background:rgba(255,255,255,.9)}.shortcut-button[disabled]{opacity:.45;color:#777}.profile-button:active:before,.history-button:active:before{background:rgba(255,255,255,.9)}
@media(max-width:350px){.nutritionist-layout{padding-left:12px;padding-right:12px}.assistant-title{font-size:17px}.chat-nav{margin-left:8px;margin-right:8px}.conversation{padding-left:5px;padding-right:5px}}
/* #ifdef MP-WEIXIN */
.assistant-title{font-size:18px;max-width:calc(100vw - 180px)}

/* Chat-only: align the controls with the native WeChat capsule center. */
.nutritionist-layout.chat-screen{padding-top:0}
.nav-row.chat-nav{height:44px;min-height:44px}
.chat-nav .history-button{position:absolute;left:-10px;top:0;margin:0}
.chat-nav .profile-button{position:absolute;right:var(--chat-profile-right,81px);top:0;margin:0}
.chat-nav .assistant-title{top:50%;left:var(--chat-title-left,50%);font-size:var(--chat-title-font,18px);max-width:none;transform:translate(-50%,-50%)}

/* #endif */
</style>
