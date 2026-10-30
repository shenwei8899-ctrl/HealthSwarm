<script setup>
import { ref, computed, onMounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import { loadCloudProfile } from '../services/cloud-profile.js'
import { getSession } from '../services/session.js'
import { ageLabel } from '../utils/member-age.js'
const profile=ref(null),error=ref(''),busy=ref(false)
const owner=computed(()=>getSession()?.families?.find(f=>f.id===profile.value?.householdId)?.isOwner===true)
let epoch=0
async function load(){if(busy.value)return;const mine=++epoch;busy.value=true;error.value='';profile.value=null;try{const result=await loadCloudProfile({openConsultation:false,readConfiguration:false});if(mine===epoch)profile.value=result}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch)busy.value=false}}
function discard(){epoch++;profile.value=null;busy.value=false;error.value=''}
onMounted(load);onShow(load);onHide(discard)
function detail(member){uni.navigateTo({url:'/pages/profile/member?id='+encodeURIComponent(member.id)})}
</script>
<template>
  <view class="screen family-overview">
    <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/chat/index'})})">‹</button><text class="nav-title">家庭健康档案</text><text/></view></AppNavBar>
    <view class="family-heading">
      <view class="family-summary"><text class="family-name">{{profile?.householdName||'我的家'}}</text><text v-if="profile" class="family-count">共 {{profile.members.length}} 位成员</text></view>
      <button class="switch-family" @click="uni.navigateTo({url:'/pages/family-select/index'})">切换家庭<text class="switch-arrow">›</text></button>
    </view>
    <text v-if="busy" class="loading-note">正在读取家庭档案…</text>
    <view v-if="busy&&!profile" class="member-list" aria-hidden="true"><view v-for="row in 3" :key="row" class="member-row"><view class="avatar"/><view class="member-copy"><view class="skeleton"/><view class="skeleton"/></view></view></view>
    <view v-if="error" class="error-state"><text class="inline-error">{{error}}</text><button class="secondary-button" @click="load">重新读取</button><button class="choose-family" @click="uni.navigateTo({url:'/pages/family-select/index'})">选择家庭</button></view>
    <view v-if="profile" class="member-list">
      <button v-for="member in profile.members" :key="member.id" class="member-row" :aria-label="member.name+'，查看健康档案'" @click="detail(member)">
        <view class="avatar">{{member.name.slice(0,1)}}</view>
        <view class="member-copy"><view class="member-name-line"><text class="member-name">{{member.name}}</text><text v-if="member.id===profile.selfMemberId" class="self-badge">本人</text></view><text class="member-meta">{{ageLabel(member)==='0 个月'?'未满1个月':ageLabel(member)}} · {{member.gender}}</text></view>
        <text class="member-arrow">›</text>
      </button>
      <text v-if="!profile.members.length" class="empty-note">暂无家庭成员</text>
    </view>
    <button v-if="profile&&owner" class="manage-members" @click="uni.navigateTo({url:'/pages/onboarding/index'})">管理家庭成员</button>
  </view>
</template>
<style scoped>
.family-overview{background:#fff;color:#202020;padding-left:20px;padding-right:20px;padding-bottom:calc(env(safe-area-inset-bottom) + 32px)}
.icon-button{min-width:44px;min-height:44px}
.family-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:26px 0 24px}
.family-summary{flex:1;min-width:0;display:flex;flex-direction:column;gap:8px}.family-name{font-size:21px;font-weight:600;line-height:1.4;overflow-wrap:anywhere}.family-count{font-size:13px;color:#767676;line-height:1.5}
.switch-family{display:flex;align-items:center;gap:7px;flex:none;min-height:44px;font-size:13px;color:#555}.switch-arrow{font-size:20px;color:#929292}
.member-list{border-top:1px solid #ededed}.member-row{width:100%;min-height:96px;display:flex;align-items:center;gap:14px;padding:20px 0;border-bottom:1px solid #ededed;text-align:left;box-sizing:border-box}
.avatar{width:48px;height:48px;display:flex;align-items:center;justify-content:center;flex:none;border-radius:50%;background:#f3f1ed;color:#625d54;font-size:20px;font-weight:400}
.member-copy{flex:1;min-width:0;display:flex;flex-direction:column;gap:8px}.member-name-line{display:flex;align-items:flex-start;gap:8px;min-width:0}.member-name{flex:0 1 auto;min-width:0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-all;font-size:17px;font-weight:500;line-height:1.5}.self-badge{flex:none;white-space:nowrap;margin-top:3px;padding:1px 6px;border-radius:4px;background:#f3f3f3;color:#646464;font-size:11px;line-height:18px}
.member-meta{font-size:13px;color:#777;line-height:1.5;overflow-wrap:anywhere}.member-arrow{flex:none;color:#969696;font-size:23px;line-height:1}
.manage-members{width:100%;min-height:48px;display:flex;align-items:center;justify-content:center;margin-top:28px;padding:12px 16px;border-radius:8px;background:#222;color:#fff;font-size:16px;line-height:1.5;box-sizing:border-box}.manage-members:active{background:#383838}.member-row:active{background:#fafafa}.switch-family:active{opacity:.6}
.loading-note,.empty-note{display:block;font-size:14px;color:#737373;line-height:1.6;padding:16px 0}.error-state{padding:0 0 20px}.choose-family{width:100%;min-height:44px;margin-top:8px;font-size:14px;color:#333}
.skeleton{background:#f1f1f1;border-radius:6px;width:40%;height:16px}.skeleton+.skeleton{width:60%;height:12px}
</style>
