<script setup>
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'

defineProps({ scrollTarget: String, voiceBusy: Boolean, historyOpen: Boolean })
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
   <scroll-view class="shortcut-scroll" scroll-x :show-scrollbar="false">
   <view class="bottom-shortcuts" role="group" aria-label="常用功能">
    <button v-for="item in shortcuts" :key="item.key" class="shortcut-button" :aria-label="item.name" :disabled="voiceBusy" @click="choose(item.key)"><AppIcon :name="item.icon" :size="42"/><text>{{item.name}}</text></button>
   </view>
   </scroll-view>
   <slot name="composer"/>
  </view>
  <slot name="overlays"/>
 </view>
</template>
<style scoped>
.conversation-menu-icon{display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:6px;width:23px;height:24px}.conversation-menu-icon>view{width:23px;height:2px;border-radius:2px;background:currentColor}.conversation-menu-icon>view+view{width:16px}
.nutritionist-layout{height:100vh;height:100dvh;display:flex;flex-direction:column;background:#fff;color:#161616;padding:6px 20px calc(env(safe-area-inset-bottom) + 10px);box-sizing:border-box;overflow:hidden}
.chat-nav{display:flex;align-items:center;justify-content:space-between;flex-shrink:0;gap:8px;position:relative;min-height:48px}.history-button,.profile-button{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:44px;min-width:44px;height:44px;min-height:44px;color:#161616;background:transparent;padding:0}.history-button:after,.profile-button:after{border:0}.history-button{margin:0 0 0 -10px}.history-entry-icon{display:block;width:28px;height:28px}.profile-button{margin:0 -10px 0 auto}.assistant-title{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);max-width:calc(100vw - 160px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:20px;font-weight:600;letter-spacing:.2px;line-height:1.4;pointer-events:none}
.conversation{flex:1;min-height:0;width:100%}.conversation :deep(.uni-scroll-view){scrollbar-width:none}.conversation :deep(.uni-scroll-view::-webkit-scrollbar){display:none}.conversation-spacer{height:24px}.composer-wrap{flex-shrink:0;background:#fff;padding-top:10px;border-top:1px solid #f7f7f7}.voice-is-busy .conversation{opacity:.35;pointer-events:none}
.shortcut-scroll{width:100%;height:44px;margin-bottom:8px;white-space:nowrap}.shortcut-scroll :deep(.uni-scroll-view){scrollbar-width:none}.shortcut-scroll :deep(.uni-scroll-view::-webkit-scrollbar){display:none}.bottom-shortcuts{display:inline-flex;align-items:center;gap:8px;min-width:100%;height:44px;vertical-align:top;white-space:nowrap}.shortcut-button{display:inline-flex;flex:0 0 auto;align-items:center;justify-content:center;gap:6px;width:auto;min-width:0;height:40px;min-height:40px;box-sizing:border-box;margin:0;padding:0 11px;border:0;border-radius:20px;background:#f5f7f4;color:#46574b;font-size:13px;font-weight:400;line-height:1.4;text-align:center;white-space:nowrap;box-shadow:none}.shortcut-button:after{border:0}.shortcut-button>text{display:block;flex-shrink:0;white-space:nowrap}.shortcut-button :deep(.app-icon){flex-shrink:0;width:18px!important;height:18px!important}.shortcut-button:active{background:#eaf0e8}.shortcut-button[disabled]{background:#fafafa;color:#aaa}.profile-button:active,.history-button:active{background:#f5f5f5}
@media(max-width:350px){.nutritionist-layout{padding-left:16px;padding-right:16px}.assistant-title{font-size:18px}}
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
