<script setup>
import AppIcon from '../../components/AppIcon.vue'
import AppNavBar from '../../components/AppNavBar.vue'
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { backHome,getProfile,getRecords,saveProfile } from '../../utils/profile.js'
import { getOrders } from '../../utils/orders.js'
import DinerPicker from '../../components/DinerPicker.vue'
const defaultOpen=ref(false)
function defaultMembers(ids){profile.value.defaultDiners=ids;saveProfile(profile.value);defaultOpen.value=false}
import MenuGroup from '../../components/MenuGroup.vue'
const profile=ref(getProfile()),records=ref(getRecords()),orders=ref(getOrders())
onShow(()=>{profile.value=getProfile();records.value=getRecords();orders.value=getOrders()})
function go(url){uni.navigateTo({url})}
function changeMode(){const next=profile.value.usageMode==='家庭使用'?'个人使用':'家庭使用';uni.showModal({title:`切换为${next}？`,content:'家人档案与历史记录会保留；已支付计划仍按购买时的内容执行。',confirmText:'确认切换',success:({confirm})=>{if(confirm){profile.value.usageMode=next;if(next==='家庭使用'&&profile.value.sharedDinerCount<2)profile.value.sharedDinerCount=2;saveProfile(profile.value)}}})}
function privacy(){uni.showModal({title:'隐私与账号',content:'当前为离线交互原型，使用明确标注的测试数据。正式版需通过 Supabase 处理账号与家庭健康数据，图片、订单与支付依据实际服务状态。',showCancel:false})}
</script>
<template>
<view class="screen my-screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">我的</text><text></text></view></AppNavBar><view class="profile-heading"><view class="profile-avatar"><AppIcon name="user" :size="52"/></view><view><text>{{profile.members.find(m=>m.relation==='本人')?.name||'我'}}</text><text>照顾自己，也照顾家人的每一餐</text></view></view><button class="family-card" @click="go('/pages/profile/index')"><view class="family-icon"><AppIcon name="family" :size="46"/></view><view><text class="family-title">我的家 · {{profile.members.length}}位成员</text><text>查看与管理家庭健康档案</text></view><text>›</text></button><view class="mode-row card"><text>使用方式</text><view><text>{{profile.usageMode}}</text><button @click="changeMode">更改</button></view></view><MenuGroup title="饮食与反馈" :items="[{icon:'record',name:'饮食记录',desc:records.length+'条已保存记录',url:'/pages/records/index'},{icon:'chat',name:'反馈',desc:'当餐 · 当日 · 近期趋势',url:'/pages/feedback/index'}]" @go="go"/><MenuGroup title="计划与订单" :items="[{icon:'calendar',name:'AI专属计划',desc:'一次支付 · 分21批配送',url:'/pages/exclusive-plans/index'},{icon:'order',name:'我的订单',desc:orders.length+'笔测试订单',url:'/pages/orders/index'}]" @go="go"/><MenuGroup title="资料管理" :items="[{icon:'memory',name:'AI 记住的事',desc:'查看、修改或删除长期记忆',url:'/pages/memories/index'},{icon:'device',name:'健康设备',desc:'连接血压计等健康设备',url:'/pages/devices/index'}]" @go="go"/><MenuGroup title="设置" :items="[{icon:'shield',name:'隐私与账号',desc:'家庭共享与账号管理',url:'/pages/settings/privacy'},{icon:'supplier',name:'合作商合作',desc:'供应、渠道及经销合作申请',url:'/pages/supplier/index'}]" @go="go"/><text class="safe-note">前端体验版 · 所有交易与推荐均为测试数据</text></view>
</template>
<style scoped>
.my-screen{padding-bottom:60rpx}.profile-heading{display:flex;align-items:center;gap:24rpx;margin:36rpx 0}.profile-avatar{height:104rpx;width:104rpx;display:flex;align-items:center;justify-content:center;border-radius:50%;background:#e6ede9;color:#246b50}.profile-heading>view:last-child{display:flex;flex-direction:column;gap:10rpx}.profile-heading text:first-child{font-size:42rpx;font-weight:600}.profile-heading text:last-child{font-size:25rpx;color:#63636b}.family-card{width:100%;display:flex;align-items:center;gap:20rpx;padding:32rpx;border-radius:28rpx;background:#fff;text-align:left;border:1rpx solid #ebebef}.family-icon{color:#246b50;height:84rpx;width:84rpx;display:flex;align-items:center;justify-content:center;background:#eaf2ed;border-radius:24rpx}.family-card>view:nth-child(2){flex:1;display:flex;flex-direction:column;gap:12rpx}.family-title{font-size:34rpx;font-weight:600}.family-card>view:nth-child(2)>text:last-child{font-size:25rpx;color:#63636b}.family-card>text{color:#9b9ba2;font-size:40rpx}.mode-row{display:flex;justify-content:space-between;align-items:center;margin-top:18rpx;padding:28rpx 32rpx;font-size:29rpx}.mode-row>view{display:flex;align-items:center;gap:20rpx}.mode-row>view>text{color:#63636b;font-size:26rpx}.mode-row button{min-height:80rpx;color:#246b50;font-size:27rpx}.safe-note{margin-top:36rpx;font-size:23rpx}
</style>
