<script setup>
import { ref } from 'vue'
import { onShow,onHide,onUnload } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import AiAnswer from './AiAnswer.vue'
import { loadCloudProfile } from '../services/cloud-profile.js'
import { readChatDays,readChatMessages } from '../services/cloud-chat.js'
import { scopedStorage } from '../services/storage.js'
import { sessionRevision } from '../services/session.js'
import { previewChatImage } from '../services/chat-images.js'
const days=ref([]),active=ref(null),messages=ref([]),busy=ref(false),error=ref(''),before=ref(''),memberId=ref('')
let epoch=0
function hide(){epoch++;days.value=[];active.value=null;messages.value=[];busy.value=false;error.value='';memberId.value='';before.value=''}
async function load(more=false){if(busy.value)return;const mine=++epoch,rev=sessionRevision();busy.value=true;error.value='';try{if(!memberId.value){const p=await loadCloudProfile();if(mine!==epoch||rev!==sessionRevision())return;memberId.value=p.members.find(m=>m.relation==='本人')?.healthMemberId||''}const value=await readChatDays(memberId.value,more?before.value:'');if(mine!==epoch||rev!==sessionRevision())return;const prefix='homepage-chat-threads:'+memberId.value+':';const local=(scopedStorage.getStorageInfoSync().keys||[]).filter(k=>k.startsWith(prefix)).map(k=>({date:k.slice(prefix.length),threads:scopedStorage.getStorageSync(k)||[]})).filter(d=>/^\d{4}-\d{2}-\d{2}$/.test(d.date)&&d.threads.length);const merged=value.days.map(d=>({...d,threads:[{thread_id:d.thread_id},...(local.find(x=>x.date===d.date)?.threads||[])].filter((p,i,arr)=>arr.findIndex(x=>x.thread_id===p.thread_id)===i)}));if(!more)merged.push(...local.filter(d=>!merged.some(x=>x.date===d.date)));merged.sort((a,b)=>b.date.localeCompare(a.date));value.days=merged;days.value=more?[...days.value,...value.days.filter(d=>!days.value.some(old=>old.date===d.date))]:value.days;before.value=value.nextBefore}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch)busy.value=false}}
async function open(day){
 if(busy.value)return
 const mine=++epoch,rev=sessionRevision();busy.value=true;error.value='';messages.value=[];active.value=day
 try{
  const results=await Promise.allSettled((day.threads||[{thread_id:day.thread_id}]).map(t=>readChatMessages(t.thread_id)))
  if(mine!==epoch||rev!==sessionRevision())return
  const fatal=results.find(r=>r.status==='rejected'&&![403,404,409,410].includes(Number(r.reason?.code)))
  if(fatal)throw fatal.reason
  messages.value=results.filter(r=>r.status==='fulfilled').flatMap(r=>r.value).filter(m=>!m.createdAt||new Date(Date.parse(m.createdAt)+8*3600000).toISOString().slice(0,10)===day.date).sort((a,b)=>(Date.parse(a.createdAt)||0)-(Date.parse(b.createdAt)||0))
  if(results.some(r=>r.status==='rejected'))error.value='部分旧对话的授权或资料来源已变化，其他有效消息已显示。'
 }catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch)busy.value=false}
}
function back(){if(active.value){epoch++;active.value=null;messages.value=[];busy.value=false;error.value=''}else uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/chat/index'})})}
onShow(()=>load());onHide(hide);onUnload(hide)
</script>
<template>
 <view class="screen history-screen">
  <AppNavBar>
   <view class="nav-row history-nav">
    <button v-if="active" class="history-back" aria-label="返回历史会话" @click="back">‹</button>
    <text class="history-title">{{active?active.date:'历史会话'}}</text>
    <button v-if="!active" class="history-close" aria-label="关闭历史会话" @click="back"><view/><view/></button>
   </view>
  </AppNavBar>
  <scroll-view class="history-content" scroll-y :show-scrollbar="false">
   <text v-if="busy" class="history-loading" role="status">正在读取对话…</text>
   <view v-if="error" class="history-error" role="alert"><text>{{error}}</text><button @click="active?open(active):load()">重新读取</button></view>
   <template v-if="!active">
    <view v-if="!busy&&!error&&!days.length" class="history-empty"><text>还没有对话历史</text><text>与家庭营养师的对话会按日期保存在这里。</text><button @click="back">返回对话</button></view>
    <button v-for="day in days" :key="day.date" class="history-row" :disabled="busy" @click="open(day)">
     <view class="history-conversation-icon" aria-hidden="true"><image src="/static/chat/conversation.png" mode="aspectFit"/></view>
     <view class="history-row-copy"><text class="history-date">{{day.date}}</text><text class="history-row-note">查看当天对话</text></view>
    </button>
    <button v-if="before" class="history-earlier" :disabled="busy" @click="load(true)">更早的对话</button>
   </template>
   <template v-else>
    <text class="history-saved-note">已保存对话</text>
    <view v-for="message in messages" :key="message.id" class="history-message" :class="message.role">
     <text class="history-message-role">{{message.role==='user'?'我':'家庭营养师'}}</text>
     <view class="history-message-body"><image v-if="message.image" :src="message.image.localPath" mode="widthFix" @click="previewChatImage(message.image)"/><AiAnswer v-if="message.role==='assistant'" :text="message.text" :citations="message.citations||[]"/><text v-else selectable>{{message.text}}</text></view>
    </view>
    <text v-if="!busy&&!error&&!messages.length" class="history-loading">当天暂无可读取的消息。</text>
   </template>
   <view class="history-bottom-space"/>
  </scroll-view>
 </view>
</template>
<style scoped>
.history-screen{height:100vh;height:100dvh;display:flex;flex-direction:column;overflow:hidden;box-sizing:border-box;padding:6px 20px calc(env(safe-area-inset-bottom) + 12px);background:#fff;color:#161616}
.history-nav{display:flex;align-items:center;min-height:48px;gap:8px}.history-title{font-size:22px;line-height:1.4;font-weight:500;color:#111;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.history-close,.history-back{display:flex;align-items:center;justify-content:center;position:relative;flex-shrink:0;width:44px;min-width:44px;height:44px;min-height:44px;padding:0;border:0;border-radius:0;background:transparent;color:#202020}.history-close{margin:0 -10px 0 auto}.history-close:after,.history-back:after{border:0}.history-close>view{position:absolute;width:25px;height:1.5px;background:currentColor;transform:rotate(45deg)}.history-close>view+view{transform:rotate(-45deg)}.history-back{margin:0 0 0 -12px;font-size:35px;font-weight:300;line-height:1}.history-back+.history-title{position:absolute;left:50%;transform:translateX(-50%);max-width:calc(100% - 88px);font-size:19px}.history-close:active,.history-back:active{background:#f5f5f5}
.history-content{flex:1;min-height:0;width:100%;margin-top:12px}.history-content :deep(.uni-scroll-view){scrollbar-width:none}.history-content :deep(.uni-scroll-view::-webkit-scrollbar){display:none}.history-row{display:flex;align-items:center;gap:20px;width:100%;min-height:94px;box-sizing:border-box;margin:0;padding:18px 0;border:0;border-radius:0;background:#fff;color:#161616;text-align:left;line-height:1.5;white-space:normal;box-shadow:none}.history-row:after{border:0}.history-row:active{background:#f8f8f8}.history-row[disabled]{background:#fff;opacity:.55}.history-conversation-icon{position:relative;flex-shrink:0;width:28px;height:28px;overflow:hidden}.history-conversation-icon image{position:absolute;left:-11.4px;top:0;width:50.9px;height:27.7px}.history-row-copy{display:flex;flex-direction:column;gap:8px;flex:1;min-width:0}.history-date{font-size:19px;line-height:1.4;font-weight:400;color:#111}.history-row-note{font-size:13px;line-height:1.5;color:#888b96}
.history-loading,.history-saved-note{display:block;font-size:13px;line-height:1.8;color:#888;margin:16px 0}.history-error{padding:16px 0;font-size:14px;line-height:1.8;color:#8d4c40}.history-error>text{display:block}.history-earlier,.history-error button,.history-empty button{display:flex;align-items:center;justify-content:center;min-height:44px;padding:8px 16px;border:1px solid #e2e2e2;border-radius:8px;background:#fff;color:#333;font-size:14px;line-height:1.5;margin:16px 0}.history-earlier:after,.history-error button:after,.history-empty button:after{border:0}.history-earlier{width:100%;min-height:52px;padding:12px 16px;border:0;border-radius:8px;background:#000;color:#fff;font-size:16px;line-height:1.5}.history-earlier:active{background:#1c1c1c}.history-earlier[disabled]{opacity:.5}.history-empty{display:flex;flex-direction:column;align-items:center;gap:12px;padding:80px 0 24px;text-align:center}.history-empty>text:first-child{font-size:19px;color:#222}.history-empty>text+text{font-size:14px;line-height:1.8;color:#888}.history-empty button{min-width:128px;background:#111;color:#fff;border:0}
.history-message{margin:24px 0;min-width:0;font-size:16px;line-height:1.8;white-space:pre-line;overflow-wrap:anywhere}.history-message-role{display:block;margin-bottom:8px;font-size:12px;color:#888;line-height:1.6}.history-message-body{color:#242424}.history-message-body>text{display:block}.history-message-body image{display:block;width:210px;max-width:100%;height:auto;margin-bottom:8px;border-radius:8px}.history-message.user{display:flex;flex-direction:column;align-items:flex-end;padding-left:42px}.user .history-message-body{max-width:100%;box-sizing:border-box;padding:12px 16px;border-radius:10px 2px 10px 10px;background:#111;color:#fff;line-height:1.6}.history-bottom-space{height:24px}
@media(max-width:350px){.history-screen{padding-left:16px;padding-right:16px}.history-title{font-size:21px}.history-row{gap:18px;min-height:90px}.history-date{font-size:18px}.history-message{font-size:15px}.history-message.user{padding-left:30px}}
</style>
