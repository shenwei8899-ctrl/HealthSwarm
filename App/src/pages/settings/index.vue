<script setup>
import { ref } from 'vue'
import { onShow, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import AppIcon from '../../components/AppIcon.vue'
import { wechatAuth } from '../../services/wechat-auth.js'
import { accountSettings } from '../../services/account-settings.js'
import { sessionRevision } from '../../services/session.js'
const avatar=ref(''),nickname=ref(''),busy=ref(false),error=ref(''),nicknameOpen=ref(false),nicknameDraft=ref(''),nicknameError=ref('')
let alive=true,epoch=0,own=sessionRevision()
async function load(){
 if(busy.value)return
 const mine=++epoch;own=sessionRevision();error.value=''
 try{const result=await accountSettings.profile();if(alive&&mine===epoch){avatar.value=result.avatar;nickname.value=result.nickname}}
 catch(e){if(alive&&mine===epoch)error.value=e.message||'账号资料读取失败，请重试'}
}
onShow(()=>{if(own!==sessionRevision()){avatar.value='';nickname.value='';nicknameDraft.value='';nicknameOpen.value=false;error.value='';busy.value=false;epoch++}void load()})
onUnload(()=>{alive=false;epoch++})
async function save(path){
 if(!path||busy.value)return
 const mine=++epoch;busy.value=true;error.value=''
 try{const result=await accountSettings.saveAvatar(path);if(alive&&mine===epoch){avatar.value=result;uni.showToast({title:'头像已更新',icon:'success'})}}
 catch(e){if(alive&&mine===epoch)error.value=e.message||'头像保存失败，请重试'}
 finally{if(alive&&mine===epoch)busy.value=false}
}
function openNickname(){if(busy.value)return;nicknameDraft.value=nickname.value;nicknameError.value='';nicknameOpen.value=true}
function closeNickname(){if(!busy.value){nicknameOpen.value=false;nicknameDraft.value='';nicknameError.value=''}}
async function saveNickname(){
 if(busy.value)return
 const mine=++epoch;busy.value=true;nicknameError.value=''
 try{const result=await accountSettings.saveNickname(nicknameDraft.value);if(alive&&mine===epoch){nickname.value=result;nicknameOpen.value=false;nicknameDraft.value='';uni.showToast({title:'昵称已更新',icon:'success'})}}
 catch(e){if(alive&&mine===epoch)nicknameError.value=e.message||'昵称保存失败，请重试'}
 finally{if(alive&&mine===epoch)busy.value=false}
}
function chooseAvatar(event){void save(event.detail?.avatarUrl)}
function chooseImage(){uni.chooseImage({count:1,sizeType:['compressed'],success:r=>void save(r.tempFilePaths[0]),fail:e=>{if(!/cancel/i.test(e.errMsg||''))error.value='图片选择失败，请重试'}})}
function go(url){if(!busy.value)uni.navigateTo({url})}
function back(){if(!busy.value)uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/my/index'})})}
function logout(){uni.showModal({title:'退出账号？',content:'已保存的云端家庭资料不会删除。',success:r=>{if(r.confirm){epoch++;avatar.value='';nickname.value='';wechatAuth.logout();uni.reLaunch({url:'/pages/index/index'})}}})}
</script>
<template>
 <view class="screen settings-screen">
  <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回我的" :disabled="busy" @click="back">‹</button><text class="nav-title">设置</text><text/></view></AppNavBar>
  <view class="settings-group">
   <!-- #ifdef MP-WEIXIN -->
   <button class="settings-row" open-type="chooseAvatar" :disabled="busy" @chooseavatar="chooseAvatar"><text>头像</text><view><text v-if="busy&&!nicknameOpen" class="row-detail">保存中…</text><image v-if="avatar" class="avatar" :src="avatar" mode="aspectFill" @error="avatar=''"/><view v-else class="avatar avatar-fallback"><AppIcon name="user" :size="34"/></view><text class="row-arrow">›</text></view></button>
   <!-- #endif -->
   <!-- #ifndef MP-WEIXIN -->
   <button class="settings-row" :disabled="busy" @click="chooseImage"><text>头像</text><view><text v-if="busy&&!nicknameOpen" class="row-detail">保存中…</text><image v-if="avatar" class="avatar" :src="avatar" mode="aspectFill" @error="avatar=''"/><view v-else class="avatar avatar-fallback"><AppIcon name="user" :size="34"/></view><text class="row-arrow">›</text></view></button>
   <!-- #endif -->
   <button class="settings-row" :disabled="busy" aria-label="修改昵称" @click="openNickname"><text>昵称</text><view><text class="nickname-value">{{nickname||'未设置'}}</text><text class="row-arrow">›</text></view></button>
   <button class="settings-row" :disabled="busy" @click="go('/pages/settings/feedback')"><text>反馈</text><text class="row-arrow">›</text></button>
  </view>
  <view v-if="error" class="settings-error" role="alert"><text>{{error}}</text><button :disabled="busy" @click="load">重新读取</button></view>
  <view class="settings-divider"/>
  <view class="settings-group"><button class="settings-row" :disabled="busy" @click="go('/pages/settings/privacy')"><text>隐私与账号</text><text class="row-arrow">›</text></button></view>
  <button class="settings-logout" :disabled="busy" @click="logout">退出登录</button>
  <view v-if="nicknameOpen" class="nickname-mask" @click.self="closeNickname"><view class="nickname-sheet" role="dialog" aria-label="修改昵称"><text class="nickname-title">修改昵称</text><input v-model="nicknameDraft" class="nickname-input" type="nickname" maxlength="20" placeholder="请输入昵称" aria-label="新昵称" :focus="nicknameOpen" :disabled="busy" confirm-type="done" @confirm="saveNickname"/><text class="nickname-hint">2–20个字符，支持中文、英文、数字和下划线</text><text v-if="nicknameError" class="nickname-error" role="alert">{{nicknameError}}</text><view class="nickname-actions"><button class="nickname-cancel" :disabled="busy" @click="closeNickname">取消</button><button class="nickname-save" :disabled="busy||!nicknameDraft.trim()" :loading="busy" @click="saveNickname">{{busy?'保存中…':'保存'}}</button></view></view></view>
 </view>
</template>
<style scoped>
.settings-screen{background:var(--ui-canvas-gradient);color:var(--ui-text);padding:0 36rpx calc(env(safe-area-inset-bottom) + 48rpx)}
.settings-group{padding-top:12px}.settings-row{width:100%;display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:66px;border-bottom:1px solid rgba(255,255,255,.7);font-size:16px;text-align:left}.settings-row:last-child{border:0}.settings-row>view{display:flex;align-items:center;gap:12px}.row-arrow{font-size:22px;color:#92929a}.row-detail{font-size:12px;color:var(--ui-muted)}.avatar{display:block;width:42px;height:42px;border-radius:50%}.avatar-fallback{display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.8);color:#686371}.settings-divider{height:12px;background:rgba(230,231,242,.45);margin:12px -36rpx 0}.settings-logout{width:100%;min-height:48px;margin-top:32px;border:1px solid #d0cdda;border-radius:12px;font-size:16px;color:#494453;background:rgba(255,255,255,.55)}.settings-error{display:flex;align-items:center;gap:12px;padding:12px 0;font-size:13px;color:#a53632}.settings-error text{flex:1}.settings-error button{min-height:44px;font-size:13px}.icon-button{min-width:44px;min-height:44px}.settings-row:active{opacity:.65}.settings-row[disabled]{opacity:.6}
.nickname-value{display:block;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ui-muted);font-size:14px}.nickname-mask{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(34,30,49,.28);box-sizing:border-box}.nickname-sheet{width:100%;max-width:340px;padding:24px 20px;border-radius:22px;background:#fafaff;box-sizing:border-box}.nickname-title{display:block;font-size:19px;font-weight:500}.nickname-input{height:48px;padding:0 12px;margin-top:20px;border:1px solid #dcd8e9;border-radius:12px;background:#fff;font-size:16px;box-sizing:border-box}.nickname-hint{display:block;margin-top:12px;color:var(--ui-muted);font-size:12px;line-height:1.7}.nickname-error{display:block;margin-top:10px;color:#a53632;font-size:13px;line-height:1.6}.nickname-actions{display:flex;gap:12px;margin-top:22px}.nickname-actions button{flex:1;min-height:44px;display:flex;align-items:center;justify-content:center;border-radius:12px;font-size:15px}.nickname-cancel{background:#eeecf5;color:#676173}.nickname-save{background:#a08be9;color:#fff}.nickname-save[disabled]{opacity:.5}
</style>
