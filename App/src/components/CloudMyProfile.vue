<script setup>
import { ref, computed, onMounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'
import MenuGroup from './MenuGroup.vue'
import { loadCloudProfile } from '../services/cloud-profile.js'
import { getSession } from '../services/session.js'
import { wechatAuth } from '../services/wechat-auth.js'
import { isCommerceEnabled } from '../services/config.js'
const profile=ref(null),busy=ref(false),error=ref('')
const name=computed(()=>profile.value?.members.find(m=>m.relation==='本人')?.name||getSession()?.accountName||'我')
const unavailableFeatures = {
  
  devices: '健康设备', supplier: '合作商合作',
}
const dietItems = [
  { icon: 'record', name: '饮食记录', desc: '查看云端已确认的记录与更正', url: '/pages/records/index' },
  { icon: 'chat', name: '反馈', desc: '回顾已记录餐次与近期饮食', url: '/pages/feedback/index' },
  { icon: 'record', name: '实测指标', desc: '体重、血糖、血压与血脂原值', url: '/pages/indicators/index' },
]
const planItems = [
  { icon: 'calendar', name: 'AI专属计划', desc: '查看当前可用计划与安排', url: '/pages/exclusive-plans/index' },
  { icon: 'calendar', name: '我的餐单', desc: '查看已保存餐单与使用状态', url: '/pages/health/plans' },
  ...(isCommerceEnabled ? [
    { icon: 'calendar', name: '今日食材采购', desc: '来自当前保存的餐单', url: '/pages/purchase/index?source=daily' },
    { icon: 'order', name: '我的订单', desc: '查看商城订单与配送', url: '/pages/orders/index' },
  ] : []),
]
const profileItems = [
  { icon: 'user', name: '我的健康资料', desc: '维护本人资料与健康咨询权限', url: '/pages/settings/health-profile' },
  { icon: 'memory', name: 'AI 记住的事', desc: '查看、修改与删除长期记忆', url: '/pages/memories/index' },
  { icon: 'device', name: '健康设备', desc: '设备连接尚未开放', url: 'devices' },
]
const settingItems = [
  { icon: 'shield', name: '隐私与账号', desc: '家庭共享与账号管理', url: '/pages/settings/privacy' },
  ...(isCommerceEnabled ? [{ icon: 'family', name: '收货地址', desc: '管理当前账号的配送地址', url: '/pages/address/index' }] : []),
  { icon: 'supplier', name: '合作商合作', desc: '正式服务尚未接入', url: 'supplier' },
]
let epoch=0
async function load(){if(busy.value)return;const mine=++epoch;profile.value=null;error.value='';busy.value=true;try{const account=await wechatAuth.restore();if(mine!==epoch)return;if(!account){uni.reLaunch({url:'/pages/index/index'});return}const result=await loadCloudProfile();if(mine===epoch)profile.value=result}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch)busy.value=false}}
function discard(){epoch++;busy.value=false;profile.value=null;error.value=''}
onMounted(load);onShow(load);onHide(discard)
function go(url){if(Object.hasOwn(unavailableFeatures,url)){unavailable(unavailableFeatures[url]);return}uni.navigateTo({url})}
function unavailable(name){uni.showModal({title:name,content:'这项功能的正式服务尚未接入，开通后可在这里使用。',showCancel:false})}
function logout(){uni.showModal({title:'退出账号？',content:'已保存的云端家庭资料不会删除。',success:r=>{if(r.confirm){discard();wechatAuth.logout();uni.reLaunch({url:'/pages/index/index'})}}})}
</script>
<template><view class="screen cloud-my"><AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/chat/index'})})">‹</button><text class="nav-title">我的</text><text/></view></AppNavBar><view class="profile-heading"><view class="profile-avatar"><AppIcon name="user" :size="52"/></view><view><text>{{name}}</text><text>照顾自己，也照顾家人的每一餐</text></view></view><text v-if="busy" class="safe-note">正在读取云端资料…</text><view v-if="error" class="card error-state"><text class="inline-error">{{error}}</text><button class="secondary-button" @click="load">重新读取</button></view><button class="family-card card" @click="go('/pages/profile/index')"><view class="family-icon"><AppIcon name="family" :size="46"/></view><view><text>{{profile?.householdName||'我的家'}} · {{profile?.members.length??'—'}}位成员</text><text>查看与管理家庭健康档案</text></view><text>›</text></button><view v-if="profile" class="mode-row card"><text>使用方式</text><view><text>{{profile.usageMode}}</text><button @click="go('/pages/onboarding/index')">更改</button></view></view><MenuGroup title="饮食与反馈" :items="dietItems" @go="go"/>
<MenuGroup title="计划与订单" :items="planItems" @go="go"/>
<MenuGroup title="资料管理" :items="profileItems" @go="go"/>
<MenuGroup title="设置" :items="settingItems" @go="go"/>
<button class="secondary-button logout" @click="logout">退出登录</button><text class="safe-note note">资料按当前账号和家庭读取，以服务端保存结果为准。</text></view></template>
<style scoped>.cloud-my{padding-bottom:60rpx}.profile-heading{display:flex;align-items:center;gap:24rpx;margin:36rpx 0}.profile-avatar,.family-icon{display:flex;align-items:center;justify-content:center;background:#eaf2ed;color:#246b50;flex-shrink:0}.profile-avatar{height:104rpx;width:104rpx;border-radius:50%}.profile-heading>view+view{display:flex;flex-direction:column;gap:10rpx}.profile-heading text:first-child{font-size:42rpx;font-weight:600}.profile-heading text:last-child{font-size:25rpx;color:#63636b}.family-card{border-radius:28rpx;background:#fff;border:1rpx solid #ebebef;width:100%;display:flex;align-items:center;gap:20rpx;padding:32rpx;text-align:left}.family-icon{height:84rpx;width:84rpx;border-radius:24rpx}.family-card>view:nth-child(2){flex:1;display:flex;flex-direction:column;gap:12rpx}.family-card>view:nth-child(2)>text:first-child{font-size:32rpx;font-weight:600}.family-card>view:nth-child(2)>text+text{font-size:25rpx;color:#63636b}.family-card>text{font-size:40rpx;color:#999}.mode-row{display:flex;justify-content:space-between;padding:28rpx 32rpx;margin-top:18rpx;font-size:29rpx}.mode-row>view{display:flex;gap:20rpx;align-items:center;font-size:26rpx;color:#63636b}.mode-row button{color:#246b50;min-height:64rpx}.logout{width:100%;margin-top:36rpx}.note{font-size:23rpx;margin-top:30rpx}.error-state{padding:24rpx;margin:24rpx 0}</style>
