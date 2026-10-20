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
function detail(member){uni.navigateTo({url:'/pages/family-shared/index?memberId='+encodeURIComponent(member.id)})}
</script>
<template><view class="screen family-overview"><AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/chat/index'})})">‹</button><text class="nav-title">家庭健康档案</text><button class="icon-button" aria-label="切换或加入家庭" @click="uni.navigateTo({url:'/pages/family-select/index'})">···</button></view></AppNavBar><view class="page-heading"><text class="eyebrow">FAMILY HEALTH</text><text class="display-title">快速看全家。</text><text class="muted">{{profile?.householdName||'我的家'}} · 资料来自当前云端家庭</text></view><text v-if="busy" class="safe-note">正在读取家庭档案…</text><view v-if="error" class="card error-state"><text class="inline-error">{{error}}</text><button class="secondary-button" @click="load">重新读取</button><button @click="uni.navigateTo({url:'/pages/family-select/index'})">选择家庭</button></view><button v-for="member in profile?.members||[]" :key="member.id" class="card member-card" @click="detail(member)"><view class="avatar">{{member.name.slice(0,1)}}</view><view><text>{{member.name}}</text><text>{{ageLabel(member)}} · {{member.gender}}</text></view><text>›</text></button><button v-if="profile&&owner" class="secondary-button" @click="uni.navigateTo({url:'/pages/onboarding/index'})">维护档案 / 添加家庭成员</button><text v-if="profile" class="safe-note note">点击成员可查看获授权的资料、实测记录与修改历史。</text></view></template>
<style scoped>.member-card{border-radius:28rpx;background:#fff;border:1rpx solid #ebebef;width:100%;display:flex;gap:22rpx;align-items:center;padding:26rpx;margin-bottom:18rpx;text-align:left}.avatar{width:86rpx;height:86rpx;display:flex;align-items:center;justify-content:center;border-radius:26rpx;background:#eaf2ed;color:#246b50;font-size:32rpx;font-weight:600}.member-card>view:nth-child(2){flex:1;display:flex;flex-direction:column;gap:12rpx}.member-card>view:nth-child(2)>text:first-child{font-size:30rpx;font-weight:600}.member-card>view:nth-child(2)>text:last-child,.muted{font-size:25rpx;color:#767680}.member-card>text{font-size:40rpx;color:#999}.note{margin-top:28rpx;text-align:left}.error-state{padding:24rpx}</style>
