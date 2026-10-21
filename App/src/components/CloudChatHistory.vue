<script setup>
import { ref } from 'vue'
import { onShow,onHide,onUnload } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
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
<template><view class="screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="back">‹</button><text class="nav-title">{{active?active.date:'历史记录'}}</text></view></AppNavBar><view v-if="!active" class="page-heading"><text class="display-title">每天的对话，都在这里</text><text class="subtitle">按北京时间归档的 AI 对话。饮食事实请查看饮食记录。</text></view><text v-if="busy" class="safe-note">正在读取对话…</text><view v-if="error" class="card history-message"><text class="inline-error">{{error}}</text><button @click="active?open(active):load()">重新读取</button></view><template v-if="!active"><view v-if="!busy&&!error&&!days.length" class="card empty"><text>还没有对话历史</text><button class="primary-button" @click="back">开始聊天</button></view><button v-for="day in days" :key="day.date" class="card history-row" @click="open(day)"><text>{{day.date}}</text><text>查看当天对话 ›</text></button><button v-if="before" class="secondary-button" :disabled="busy" @click="load(true)">更早的对话</button></template><template v-else><text class="safe-note">已保存对话</text><view v-for="message in messages" :key="message.id" class="card history-message" :class="message.role"><text>{{message.role==='user'?'我':'家庭营养师'}}</text><image v-if="message.image" :src="message.image.localPath" mode="widthFix" @click="previewChatImage(message.image)"/><text>{{message.text}}</text></view><text v-if="!busy&&!error&&!messages.length" class="safe-note">当天暂无可读取的消息。</text></template></view></template>
<style scoped>.history-row{width:100%;padding:28rpx;margin:18rpx 0;display:flex;justify-content:space-between;text-align:left;font-size:28rpx}.history-message{padding:28rpx;margin:24rpx 0;font-size:28rpx;line-height:1.7;white-space:pre-line}.history-message text{display:block}.history-message text:first-child{font-size:24rpx;color:#63636b;margin-bottom:12rpx}.history-message.user{background:#eaf2ed}.history-message image{width:360rpx;max-width:100%;border-radius:16rpx}</style>
