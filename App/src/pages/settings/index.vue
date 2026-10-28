<script setup>
import { ref, computed } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import { loadCloudProfile } from '../../services/cloud-profile.js'
import { wechatAuth } from '../../services/wechat-auth.js'
import { isCommerceEnabled, isMockMode } from '../../services/config.js'
import { commerce, usesCommerceIdentity } from '../../services/commerce.js'
import { getProfile } from '../../utils/profile.js'

const profile=ref(null),busy=ref(false),error=ref('')
const selfMember=computed(()=>profile.value?.members.find(member=>String(member.id)===String(profile.value.selfMemberId)))
let epoch=0
function discard(){epoch++;profile.value=null;busy.value=false;error.value=''}
async function load(){
  if(busy.value)return
  const mine=++epoch;busy.value=true;error.value='';profile.value=null
  try{
    if(isMockMode){profile.value=getProfile();return}
    const account=await wechatAuth.restore()
    if(mine!==epoch)return
    if(!account){uni.reLaunch({url:'/pages/index/index'});return}
    const result=await loadCloudProfile({openConsultation:false})
    if(mine===epoch)profile.value=result
  }catch(e){if(mine===epoch)error.value=e.message||'资料读取失败，请重试'}
  finally{if(mine===epoch)busy.value=false}
}
onShow(load);onHide(discard);onUnload(discard)
function go(url){uni.navigateTo({url})}
function openSelf(){
  const member=selfMember.value||(isMockMode?profile.value?.members.find(m=>m.relation==='本人'):null)
  if(!member){uni.showModal({title:'我的健康档案',content:error.value||'当前家庭尚未关联本人的健康档案，请进入家庭成员查看。',showCancel:false});return}
  go('/pages/profile/member?id='+encodeURIComponent(member.id))
}
function back(){uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/my/index'})})}
function logout(){uni.showModal({title:'退出账号？',content:'已保存的云端家庭资料不会删除。',success:async r=>{if(r.confirm){try{if(usesCommerceIdentity)await commerce.logout();else wechatAuth.logout();discard();uni.reLaunch({url:'/pages/index/index'})}catch(e){uni.showToast({title:e.message,icon:'none'})}}}})}
</script>
<template>
  <view class="screen settings-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回我的" @click="back">‹</button><text class="nav-title">设置</text><text/></view></AppNavBar>
    <view v-if="error" class="settings-error"><text>{{error}}</text><button @click="load">重新读取</button></view>
    <view class="settings-group">
      <button class="settings-row" :disabled="busy" @click="openSelf"><text>我的健康档案</text><view><text v-if="busy" class="row-detail">读取中…</text><text class="row-arrow">›</text></view></button>
      <button v-if="isCommerceEnabled" class="settings-row" @click="go('/pages/address/index')"><text>收货地址</text><text class="row-arrow">›</text></button>
      <button class="settings-row" @click="go('/pages/profile/index')"><text>家庭成员</text><view><text class="row-detail">{{busy ? '读取中…' : profile ? '共 '+profile.members.length+' 人' : '暂未读取'}}</text><text class="row-arrow">›</text></view></button>
    </view>
    <view class="settings-divider"/>
    <view class="settings-group"><button class="settings-row" @click="go('/pages/settings/privacy')"><text>隐私与账号</text><text class="row-arrow">›</text></button></view>
    <button class="settings-logout" @click="logout">退出登录</button>
  </view>
</template>
<style scoped>
.settings-screen{background:#fff;color:#171717;padding-left:36rpx;padding-right:36rpx;padding-bottom:calc(env(safe-area-inset-bottom) + 48rpx)}
.settings-group{padding-top:10rpx}.settings-row{width:100%;display:flex;align-items:center;justify-content:space-between;gap:24rpx;min-height:60px;border-bottom:1rpx solid #e9e9e9;font-size:16px;text-align:left;line-height:1.5}.settings-row:last-child{border-bottom:0}.settings-row>view{display:flex;align-items:center;gap:16rpx}.row-detail{font-size:14px;color:#85858c}.row-arrow{font-size:22px;line-height:1;color:#92929a;flex:none}.settings-divider{height:20rpx;background:#f7f7f8;margin:0 -36rpx}.settings-logout{width:100%;min-height:48px;display:flex;align-items:center;justify-content:center;margin-top:52rpx;border:1px solid #d0d0d0;border-radius:14rpx;background:#fff;font-size:16px;color:#302c28;font-weight:500}.settings-row:active,.settings-logout:active{background:#fafafa}.settings-row[disabled]{background:#fff;color:#777}.settings-error{display:flex;align-items:center;justify-content:space-between;gap:16rpx;padding:24rpx 0;color:#a53632;font-size:13px}.settings-error>text{flex:1}.settings-error button{min-height:44px;font-size:13px;color:#222;flex:none}
.icon-button{min-width:44px;min-height:44px}
</style>
