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
async function load(){if(busy.value)return;const mine=++epoch;busy.value=true;error.value='';profile.value=null;try{const result=await loadCloudProfile();if(mine===epoch)profile.value=result}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch)busy.value=false}}
function discard(){epoch++;profile.value=null;busy.value=false;error.value=''}
onMounted(load);onShow(load);onHide(discard)
function detail(member){uni.navigateTo({url:'/pages/profile/member?id='+encodeURIComponent(member.id)})}
</script>
<template><view class="screen family-overview"><AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/chat/index'})})">‹</button><text class="nav-title">家庭健康档案</text><button class="icon-button" aria-label="切换家庭" @click="uni.navigateTo({url:'/pages/family-select/index'})">···</button></view></AppNavBar><view class="page-heading"><text class="display-title">家人的健康，都在这里</text><text class="muted">{{profile?.householdName||'我的家'}}</text></view><text v-if="busy" class="safe-note">正在读取家庭档案…</text><view v-if="error" class="card error-state"><text class="inline-error">{{error}}</text><button class="secondary-button" @click="load">重新读取</button><button @click="uni.navigateTo({url:'/pages/family-select/index'})">选择家庭</button></view><button v-for="member in profile?.members||[]" :key="member.id" class="card member-card" @click="detail(member)"><view class="avatar">{{member.name.slice(0,1)}}</view><view><text>{{member.name}}<text v-if="member.id===profile.selfMemberId" class="self-badge"> · 本人</text></text><text>{{ageLabel(member)}} · {{member.gender}}</text></view><text>›</text></button><button v-if="profile&&owner" class="secondary-button" @click="uni.navigateTo({url:'/pages/onboarding/index'})">管理家庭成员</button></view></template>
<style scoped>.member-card{border-radius:28rpx;background:#fff;border:1rpx solid #ebebef;width:100%;display:flex;gap:22rpx;align-items:center;padding:26rpx;margin-bottom:18rpx;text-align:left}.avatar{width:86rpx;height:86rpx;display:flex;align-items:center;justify-content:center;border-radius:26rpx;background:#f0f1f4;color:#292a2e;font-size:32rpx;font-weight:500}.member-card>view:nth-child(2){flex:1;display:flex;flex-direction:column;gap:12rpx}.member-card>view:nth-child(2)>text:first-child{font-size:30rpx;font-weight:500}.member-card>view:nth-child(2)>text:last-child,.muted{font-size:25rpx;color:#767680}.member-card>text{font-size:40rpx;color:#767680}.note{margin-top:28rpx;text-align:left}.error-state{padding:24rpx}</style>

<style scoped>
/* Approved v5 presentation. */
.member-card{padding:28rpx;gap:24rpx;border-radius:24rpx;min-height:158rpx}.avatar{width:104rpx;height:104rpx;border-radius:50%;background:#eaf0f8;color:#34465d;font-size:38rpx;font-weight:400;flex-shrink:0}.member-card:nth-of-type(even) .avatar{background:#f3ede8;color:#7b604a}.member-card>view:nth-child(2){min-width:0}.member-card>view:nth-child(2)>text:first-child{font-size:32rpx;font-weight:400}.member-card>view:nth-child(2)>text:last-child{font-size:27rpx;overflow-wrap:anywhere}.family-overview .secondary-button{color:#0674ed;border-color:#c6d9f4}.note{font-size:25rpx;line-height:1.7;margin-top:32rpx}
</style>
