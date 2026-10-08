<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { ref } from 'vue'
import { onShow, onShareAppMessage } from '@dcloudio/uni-app'
import { backHome,getProfile,newMember,normalizeMember,saveProfile } from '../../utils/profile.js'
import { createInvite, shareInvite } from '../../utils/invitations.js'
const profile=ref(getProfile())
onShow(()=>profile.value=getProfile())
function detail(m){uni.navigateTo({url:'/pages/profile/member?id='+m.id})}
function add(){const m=normalizeMember(newMember(profile.value.members.length));profile.value.members.push(m);saveProfile(profile.value);uni.navigateTo({url:'/pages/profile/member?id='+m.id+'&edit=1'})}
onShareAppMessage(()=>shareInvite(createInvite()))
function share(){uni.showActionSheet({itemList:['转发家庭邀请卡片（模拟）'],success:()=>uni.navigateTo({url:'/pages/invite/index?token='+createInvite()})})}
</script>
<template><view class="screen family-overview"><AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">家庭健康档案</text><button class="icon-button" aria-label="家庭分享菜单" @click="share">···</button></view></AppNavBar><view class="hero"><text class="eyebrow">FAMILY HEALTH</text><text class="display-title">快速看全家。</text><text>每位成员的健康资料独立保存，点击卡片查看和维护。</text></view><button v-for="m in profile.members" :key="m.id" class="member-card card" @click="detail(m)"><view class="avatar" :style="{background:m.color}">{{m.name.slice(0,1)}}</view><view><text>{{m.name}}</text><text>{{m.birthDate?m.age+' 岁':'年龄未填写'}} · {{m.gender}}</text></view><text>›</text></button><button class="secondary-button add" @click="add">＋ 添加家庭成员</button></view></template>
<style scoped>.hero{display:flex;flex-direction:column;gap:16rpx;margin:50rpx 0 32rpx}.hero .display-title{font-size:50rpx}.hero>text:last-child{color:#697c70;font-size:23rpx;line-height:1.7}.member-card{width:100%;display:flex;gap:22rpx;align-items:center;padding:26rpx;margin-bottom:18rpx;text-align:left}.avatar{width:86rpx;height:86rpx;border-radius:26rpx;display:flex;align-items:center;justify-content:center;font-size:32rpx;font-weight:800}.member-card>view:nth-child(2){flex:1;display:flex;flex-direction:column;gap:10rpx}.member-card>view:nth-child(2)>text:first-child{font-size:30rpx;font-weight:800}.member-card>view:nth-child(2)>text:last-child{font-size:21rpx;color:#748477}.member-card>text:last-child{font-size:40rpx;color:#719380}.add{width:100%;margin:30rpx 0}</style>
