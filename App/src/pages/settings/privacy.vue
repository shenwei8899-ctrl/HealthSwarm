<script setup>
import { commerce, usesCommerceIdentity } from '../../services/commerce.js'
import { isMockMode } from '../../services/config.js'
import { wechatAuth } from '../../services/wechat-auth.js'
import { clearSession } from '../../services/session.js'
import AppNavBar from '../../components/AppNavBar.vue'
import { backHome } from '../../utils/profile.js'
function logout(){uni.showModal({title:'退出账号？',content:'已保存的资料不会删除，退出后需重新登录才能读取。',success:async r=>{if(r.confirm){try{if(usesCommerceIdentity)await commerce.logout();else wechatAuth.logout();uni.reLaunch({url:'/pages/index/index'})}catch(e){uni.showToast({title:e.message,icon:'none'})}}}})}
</script>
<template><view class="screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">隐私与账号</text><text></text></view></AppNavBar><view class="page-heading"><text class="display-title">了解你的数据</text><text class="subtitle">{{isMockMode?'前端体验版中的资料仅存于本机。请使用测试信息。':'正式账号的家庭资料、饮食记录和订单按服务端权限读取。本机仅保留会话与操作恢复信息。'}}</text></view><view class="list-card card"><text class="section-title">家庭共享范围</text><text>共同菜单、共享记录和计划可供家庭成员查看；个人 AI 对话默认不向全家公开。</text><text>体检报告需本人明确同意才开放。共享范围以本人授权和服务端实际校验为准。</text></view><view v-if="isMockMode" class="list-card card"><text class="section-title">AI 记住的事</text><text>家人可通过明确的对话补充另一位成员健康信息，保留“家人提供、用户自述”来源，并可撤回。</text><button class="secondary-button" @click="uni.navigateTo({url:'/pages/memories/index'})">查看长期记忆</button></view><button class="secondary-button" @click="logout">退出账号</button></view></template>
