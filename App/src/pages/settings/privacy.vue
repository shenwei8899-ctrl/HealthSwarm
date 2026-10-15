<script setup>
import { commerce, usesCommerceIdentity } from '../../services/commerce.js'
import { clearSession } from '../../services/session.js'
import AppNavBar from '../../components/AppNavBar.vue'
import { backHome } from '../../utils/profile.js'
function logout(){uni.showModal({title:'退出账号？',content:'本机健康档案和饮食记录会按会员保留。',success:async r=>{if(r.confirm){try{if(usesCommerceIdentity)await commerce.logout();else clearSession();uni.reLaunch({url:'/pages/index/index'})}catch(e){uni.showToast({title:e.message,icon:'none'})}}}})}
</script>
<template><view class="screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">隐私与账号</text><text></text></view></AppNavBar><view class="page-heading"><text class="display-title">了解你的数据</text><text class="subtitle">前端体验版中的资料仅存于本机。请使用测试信息。</text></view><view class="list-card card"><text class="section-title">家庭共享范围</text><text>共同菜单、共享记录和计划可供家庭成员查看；个人 AI 对话默认不向全家公开。</text><text>体检报告需本人明确同意才开放。退出家庭、移除成员和注销在真实联调阶段接入后端授权流程。</text></view><view class="list-card card"><text class="section-title">AI 记住的事</text><text>家人可通过明确的对话补充另一位成员健康信息，保留“家人提供、用户自述”来源，并可撤回。</text><button class="secondary-button" @click="uni.navigateTo({url:'/pages/memories/index'})">查看长期记忆</button></view><button class="secondary-button" @click="logout">退出账号</button></view></template>
