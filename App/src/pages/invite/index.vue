<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { ref,computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { backHome,getProfile,saveProfile } from '../../utils/profile.js'
import { getInvite,acceptInvite } from '../../utils/invitations.js'
const token=ref(''),loggedIn=ref(false),account=ref('受邀账号 A'),error=ref('')
onLoad(o=>token.value=o.token||'')
const invitation=computed(()=>getInvite(token.value))
function accept(){const result=acceptInvite(token.value,account.value);if(result.error){error.value=result.error;return}uni.redirectTo({url:'/pages/onboarding/index?member='+result.id})}
function back(){const p=getProfile();p.viewerAccount='creator';saveProfile(p);backHome()}
</script>
<template><view class="screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="back">‹</button><text class="nav-title">家庭邀请</text><text class="pill">模拟</text></view></AppNavBar><view class="invitation card"><text class="display-title">邀请你加入家庭</text><text class="helper">分享卡片不展示基础病、过敏等健康信息。当前为离线分享及身份模拟，不是真实微信转发。</text><template v-if="!invitation"><text>邀请不存在或不可用</text></template><template v-else-if="!loggedIn"><text class="label">模拟微信登录账号</text><input v-model="account" class="field-input" placeholder="演示账号名称，不需要手机号"/><button class="primary-button" @click="account.trim()?loggedIn=true:null">模拟微信登录</button></template><template v-else><text class="section-title">{{invitation.inviter}}邀请你加入“{{invitation.householdName}}”</text><text>共享范围：加入后可按家庭权限查看成员健康档案及饮食记录。接受前不展示健康资料。</text><text v-if="invitation.memberId">本邀请绑定已有成员档案，接受后核对预填资料，不重复创建。</text><text v-else>接受后建立你自己的成员档案。</text><text v-if="error" class="error">{{error}}</text><button class="primary-button" @click="accept">确认接受邀请加入家庭</button></template></view></view></template>
<style scoped>.invitation{margin-top:50rpx;padding:30rpx;display:flex;flex-direction:column;gap:28rpx}.invitation .display-title{font-size:46rpx}.invitation>text:not(.display-title){font-size:23rpx;line-height:1.75}.helper{color:#768276}.error{color:#a04635}</style>
