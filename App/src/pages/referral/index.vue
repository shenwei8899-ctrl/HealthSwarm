<script setup>
import { ref, getCurrentInstance } from 'vue'
import { onShow, onHide, onUnload, onShareAppMessage } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import AppIcon from '../../components/AppIcon.vue'
import { request } from '../../services/request.js'
import { getSession, sessionRevision } from '../../services/session.js'
import { qrcodeFile, drawReferralPoster } from '../../services/referral-poster.js'

const cover='/pages/referral/static/invite-meal.jpg'
const instance=getCurrentInstance()
const invite=ref(null),qrcode=ref(''),records=ref([]),total=ref(null),cursor=ref(null)
const busy=ref(false),qrBusy=ref(false),saving=ref(false),loadingMore=ref(false)
const error=ref(''),qrError=ref(''),recordError=ref(''),saveError=ref('')
let epoch=0,owner='',alive=false
const identity=()=>JSON.stringify([getSession()?.accountId,getSession()?.token,sessionRevision()])
const current=(mine,scope)=>alive&&mine===epoch&&scope===identity()
function discard(){alive=false;epoch++;invite.value=null;qrcode.value='';records.value=[];total.value=null;cursor.value=null;busy.value=false;qrBusy.value=false;saving.value=false;loadingMore.value=false;error.value='';qrError.value='';recordError.value='';saveError.value=''}
async function load(){
  discard();alive=true;owner=identity()
  const mine=epoch,scope=owner
  if(!getSession()?.token){uni.reLaunch({url:'/pages/index/index'});return}
  busy.value=true
  try{
    const {data}=await request({path:'/api/referrals/mine',method:'POST'})
    if(!current(mine,scope))return
    if(!/^[A-Za-z0-9_-]{24}$/.test(data?.code)||data.enabled!==true||data.path!=='/pages/index/index?ref='+data.code)throw Error('邀请入口暂不可用，请重试')
    invite.value=data
    void loadCode();void loadRecords()
  }catch(e){if(current(mine,scope))error.value=e.message||'邀请信息读取失败，请重试'}
  finally{if(current(mine,scope))busy.value=false}
}
async function loadCode(){
  if(qrBusy.value||!invite.value)return
  const mine=epoch,scope=owner;qrBusy.value=true;qrError.value=''
  let envVersion='release'
  // #ifdef MP-WEIXIN
  envVersion=uni.getAccountInfoSync?.().miniProgram?.envVersion||'release'
  // #endif
  try{const {data}=await request({path:'/api/referrals/mine/qrcode?env_version='+encodeURIComponent(envVersion),timeout:30000});if(!current(mine,scope))return
    const path=await qrcodeFile(data.image_base64,invite.value.code);if(current(mine,scope))qrcode.value=path
  }catch(e){if(current(mine,scope))qrError.value=e.message||'小程序码读取失败，请重试'}
  finally{if(current(mine,scope))qrBusy.value=false}
}
async function loadRecords(more=false){
  if(loadingMore.value)return
  const mine=epoch,scope=owner;loadingMore.value=true;recordError.value=''
  try{const {data}=await request({path:'/api/referrals/mine/records'+(more&&cursor.value?'?before='+cursor.value:'')})
    if(!current(mine,scope))return
    if(!Number.isSafeInteger(data.total)||data.total<0||!Array.isArray(data.items)||data.items.some(x=>!/^好友\d{3,}$/.test(x.label)||!Number.isFinite(Date.parse(x.completed_at))))throw Error('邀请记录返回无效，请重试')
    records.value=more?[...records.value,...data.items]:data.items;total.value=data.total;cursor.value=data.next_cursor
  }catch(e){if(current(mine,scope))recordError.value=e.message||'记录读取失败，请重试'}
  finally{if(current(mine,scope))loadingMore.value=false}
}
function date(value){const d=new Date(new Date(value).getTime()+8*3600000);return `${d.getUTCMonth()+1}月${d.getUTCDate()}日`}
async function savePoster(){
  if(saving.value||!qrcode.value)return
  const mine=epoch,scope=owner;saving.value=true;saveError.value=''
  try{
    const path=await drawReferralPoster({canvasId:'referral-poster',component:instance.proxy,cover,qrcode:qrcode.value})
    if(!current(mine,scope))return
    // #ifdef MP-WEIXIN
    await new Promise((resolve,reject)=>uni.saveImageToPhotosAlbum({filePath:path,success:resolve,fail:()=>reject(Error('未能保存海报，请检查相册权限后重试'))}))
    if(current(mine,scope))uni.showToast({title:'海报已保存',icon:'success'})
    // #endif
    // #ifndef MP-WEIXIN
    uni.previewImage({urls:[path]})
    // #endif
  }catch(e){if(current(mine,scope))saveError.value=e.message||'海报保存失败，请重试'}
  finally{if(current(mine,scope))saving.value=false}
}
onShow(()=>{if(saving.value&&owner===identity())return;void load()});onHide(()=>{if(!saving.value)discard()});onUnload(discard)
onShareAppMessage(()=>alive&&owner===identity()&&invite.value?{title:invite.value.title,path:invite.value.path,imageUrl:cover}:{title:'家庭营养师',path:'/pages/index/index',imageUrl:cover})
</script>
<template>
  <view class="screen referral-screen">
    <AppNavBar title="邀请好友"><template #left><button class="icon-button" aria-label="返回" @click="uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/my/index'})})">‹</button></template></AppNavBar>
    <view class="intro">
      <text class="title">把家庭营养师分享给朋友</text>
      <view class="subtitle">
        <text>分享给你一个家庭营养师，</text>
        <text>一起把每天吃什么安排好。</text>
      </view>
    </view>
    <view v-if="error" class="message" role="alert"><text>{{error}}</text><button @click="load">重新读取</button></view>
    <view class="invite-card">
      <image class="hero" :src="cover" mode="widthFix"/>
      <view class="code-area">
        <view class="code-frame">
          <image v-if="qrcode" class="qrcode" :src="qrcode" mode="aspectFit" @error="qrcode='';qrError='小程序码显示失败，请重试'"/>
          <view v-else class="code-placeholder" role="status"><text>{{qrError||(qrBusy?'正在生成专属小程序码…':busy?'正在读取邀请信息…':'专属小程序码')}}</text><button v-if="qrError" @click="loadCode">重新生成</button></view>
        </view>
        <text class="scan-label">扫码开始使用</text>
      </view>
    </view>
    <button class="share-button" open-type="share" :disabled="!invite||busy"><AppIcon name="chat" :size="23"/><text>分享给微信好友</text></button>
    <button class="poster-button" :disabled="!qrcode||saving" @click="savePoster"><text class="download-icon">↓</text><text>{{saving?'正在保存海报…':'保存邀请海报'}}</text></button>
    <text v-if="saveError" class="action-error" role="alert">{{saveError}}</text>
    <view class="records-card">
      <view class="records-heading"><text class="records-title">我的邀请</text><text class="count">成功邀请 <text>{{total===null?'—':total}}</text> 人</text></view>
      <text class="rule">好友通过你的邀请注册并完成建档后，计为邀请成功。</text>
      <view v-for="record in records" :key="record.label" class="record"><view class="avatar"><AppIcon name="user" :size="24"/></view><view class="record-copy"><text>{{record.label}}</text><text class="status">已完成建档</text></view><text class="date">{{date(record.completed_at)}}</text></view>
      <view v-if="recordError" class="message"><text>{{recordError}}</text><button @click="loadRecords(!!records.length)">重新读取</button></view>
      <text v-else-if="total===0" class="empty">还没有邀请记录，分享给朋友一起体验吧。</text>
      <text v-else-if="loadingMore&&!records.length" class="empty">正在读取邀请记录…</text>
      <button v-if="cursor" class="more" :disabled="loadingMore" @click="loadRecords(true)">{{loadingMore?'正在读取…':'查看更多'}}</button>
    </view>
    <canvas canvas-id="referral-poster" id="referral-poster" class="poster-canvas" :width="375" :height="500"/>
  </view>
</template>
<style scoped>
.referral-screen{min-height:100vh;box-sizing:border-box;padding:0 18px calc(env(safe-area-inset-bottom) + 24px);background:#faf7ff;background-image:radial-gradient(ellipse at 0 0,#f7dff8,transparent 65%),radial-gradient(ellipse at 100% 0,#e5e5ff,transparent 65%);color:#38213f}
.intro{text-align:center;padding:18px 0 16px}.title{display:block;font-size:24px;font-weight:600;line-height:1.45;letter-spacing:-.5px}.subtitle{margin-top:6px;color:#69606c;font-size:14px;line-height:1.55}.subtitle text{display:block}
.invite-card{overflow:hidden;border:1px solid #dec1f1;border-radius:18px;background:rgba(255,255,255,.84)}
.hero{display:block;width:100%;height:auto}
.code-area{display:flex;flex-direction:column;align-items:center;padding:10px 16px 16px}
.code-frame{box-sizing:border-box;display:flex;flex:none;align-items:center;justify-content:center;width:166px;height:166px;padding:10px;border:1px solid #eee3f5;border-radius:16px;background:#fff}
.qrcode,.code-placeholder{display:block;flex:none;width:100%;height:100%}
.code-placeholder{display:flex;align-items:center;justify-content:center;flex-direction:column;text-align:center;font-size:12px;line-height:1.7;color:#776d80}
.code-placeholder button{font-size:13px;color:#8b4ac4;margin-top:4px;min-height:44px;padding:8px}
.scan-label{font-size:15px;font-weight:500;color:#67388b;margin-top:8px}
.share-button,.poster-button{display:flex;align-items:center;justify-content:center;gap:12px;width:100%;min-height:48px;border-radius:15px;font-size:18px;font-weight:500}.share-button{margin-top:16px;background:linear-gradient(110deg,#8f4bc6,#9655cb);color:#fff}.poster-button{margin-top:10px;border:1px solid #9d65d1;background:rgba(255,255,255,.8);color:#69358d}.download-icon{font-size:28px;line-height:1;border-bottom:2px solid currentColor;padding:0 4px}.share-button[disabled],.poster-button[disabled]{opacity:.5}.action-error{display:block;font-size:13px;color:#945063;line-height:1.6;margin-top:10px}
.records-card{margin-top:20px;padding:16px 14px 8px;background:rgba(255,255,255,.85);border:1px solid #eddaf7;border-radius:17px}.records-heading{display:flex;align-items:center;justify-content:space-between;gap:8px}.records-title{font-size:19px;font-weight:600}.count{font-size:14px;color:#69606c}.count>text{font-size:20px;color:#964bc9;font-weight:600}.rule{display:block;font-size:13px;line-height:1.6;color:#77707c;margin:8px 0 10px}.record{display:flex;gap:12px;align-items:center;min-height:64px;border-top:1px solid #eee0f4}.avatar{display:flex;align-items:center;justify-content:center;background:#f1e7fa;border-radius:50%;width:38px;height:38px;color:#a27db5;flex:none}.record-copy{display:flex;flex-direction:column;gap:3px;flex:1;font-size:15px}.status,.date{font-size:12px;color:#847b8b}.message{display:flex;flex-direction:column;align-items:center;gap:8px;font-size:13px;color:#945063;line-height:1.6;padding:10px}.message button,.more{font-size:13px;color:#7941a4;min-height:44px}.empty{display:block;text-align:center;color:#8b8191;font-size:13px;line-height:1.7;padding:20px 0}.more{width:100%;border-top:1px solid #eee0f4}.poster-canvas{position:fixed;left:-10000px;top:0;width:375px;height:500px;pointer-events:none}
@media(max-width:350px){.title{font-size:21px}.code-frame{width:150px;height:150px}.count{font-size:12px}}
</style>
