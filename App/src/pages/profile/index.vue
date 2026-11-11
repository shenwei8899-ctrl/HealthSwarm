<script setup>
import CloudFamilyOverview from '../../components/CloudFamilyOverview.vue'
import { isMockMode } from '../../services/config.js'
import FamilyMemberDeck from '../../components/FamilyMemberDeck.vue'
import AppNavBar from '../../components/AppNavBar.vue'
import { ref, reactive } from 'vue'
import { onShow, onHide, onShareAppMessage } from '@dcloudio/uni-app'
import { backHome,getProfile,newMember,normalizeMember,saveProfile } from '../../utils/profile.js'
import { familyShareState, createFamilyShareController } from '../../services/family-invitations.js'
import { createInvite, shareInvite } from '../../utils/invitations.js'
const profile=ref(getProfile()),shareState=reactive(familyShareState())
const shareController=createFamilyShareController({state:shareState})
onShow(()=>{if(!isMockMode)uni.hideShareMenu?.()})
onHide(()=>shareController.discard())
onShow(()=>profile.value=getProfile())
function detail(m){uni.navigateTo({url:'/pages/profile/member?id='+m.id})}
function add(){const m=normalizeMember(newMember(profile.value.members.length));profile.value.members.push(m);saveProfile(profile.value);uni.navigateTo({url:'/pages/profile/member?id='+m.id+'&edit=1'})}
onShareAppMessage(event=>isMockMode?shareInvite(createInvite()):shareController.share(event))
function share(){uni.showActionSheet({itemList:['转发家庭邀请卡片（模拟）'],success:()=>uni.navigateTo({url:'/pages/invite/index?token='+createInvite()})})}
</script>
<template><CloudFamilyOverview v-if="!isMockMode" :share-state="shareState" @prepare-invites="shareController.prepare" @revoke-invite="shareController.revoke" @discard-invites="shareController.discard"/><view v-else class="screen family-overview"><AppNavBar title="家庭健康档案"><template #left><button class="icon-button" @click="backHome">‹</button></template><template #right><button class="icon-button" aria-label="家庭分享菜单" @click="share">···</button></template></AppNavBar><view class="hero"><text class="display-title">{{profile.householdName||'我的家'}}</text><text>每位成员的健康资料独立保存，点击卡片查看和维护。</text></view><FamilyMemberDeck :members="profile.members" scope="local-preview" :self-id="profile.selfMemberId||profile.members[0]?.id" can-manage @open="detail" @manage="add"/><button class="secondary-button add" @click="add">＋ 添加家庭成员</button></view></template>
<style scoped>.family-overview{background:var(--ui-canvas-gradient)}.hero{display:flex;flex-direction:column;gap:16rpx;margin:50rpx 0 32rpx}.hero .display-title{font-size:50rpx}.hero>text:last-child{color:#697c70;font-size:25rpx;line-height:1.7}.member-card{width:100%;display:flex;gap:22rpx;align-items:center;padding:26rpx;margin-bottom:18rpx;text-align:left}.avatar{width:86rpx;height:86rpx;border-radius:26rpx;display:flex;align-items:center;justify-content:center;font-size:32rpx;font-weight:500}.member-card>view:nth-child(2){flex:1;display:flex;flex-direction:column;gap:10rpx}.member-card>view:nth-child(2)>text:first-child{font-size:30rpx;font-weight:500}.member-card>view:nth-child(2)>text:last-child{font-size:25rpx;color:#748477}.member-card>text:last-child{font-size:40rpx;color:#719380}.add{width:100%;margin:30rpx 0}</style>
