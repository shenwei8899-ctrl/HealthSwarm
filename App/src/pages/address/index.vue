<script setup>
import { isCommerceEnabled } from '../../services/config.js'
import CommerceAddresses from '../../components/CommerceAddresses.vue'
import CommerceAccess from '../../components/CommerceAccess.vue'

import AppNavBar from '../../components/AppNavBar.vue'
import { ref } from 'vue'
import { onShow,onUnload } from '@dcloudio/uni-app'
import { backHome } from '../../utils/profile.js'
import { service as mockService } from '../../services/index.js'
let loadVersion=0
const addresses=ref([]),loading=ref(true),saving=ref(false),error=ref('')
async function load(){const version=++loadVersion;loading.value=true;error.value='';try{const next=await mockService.addresses();if(version===loadVersion)addresses.value=next}catch(e){if(version===loadVersion)error.value=e.message}finally{if(version===loadVersion)loading.value=false}}
onUnload(()=>loadVersion++)
onShow(()=>{if(!isCommerceEnabled)return load()})
async function select(item){if(saving.value)return;saving.value=true;try{await mockService.selectAddress(item.id);backHome()}catch(e){error.value=e.message}finally{saving.value=false}}
function edit(id=''){uni.navigateTo({url:'/pages/address/edit'+(id?'?id='+id:'')})}
</script>
<template>
<CommerceAccess v-if="isCommerceEnabled"><CommerceAddresses /></CommerceAccess>
<view v-else class="screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">选择配送地址</text><text></text></view></AppNavBar><view class="page-heading"><text class="display-title">送到哪里？</text><text class="subtitle">地址只用于本次下单。已支付订单保留原地址。</text></view><text v-if="loading" class="safe-note">正在读取地址…</text><view v-if="error"><text class="inline-error">{{error}}</text><button :disabled="loading||saving" class="secondary-button" @click="load">重试读取</button></view><view v-if="!loading&&!error&&!addresses.length" class="card empty"><text class="section-title">还没有收货地址</text><text class="demo-label">添加一条测试地址，就可以继续体验购买流程。</text></view><view v-for="item in addresses" :key="item.id" class="address-item card"><button class="address-main" :disabled="saving" @click="select(item)"><text class="section-title">{{item.name}} <text class="phone">{{item.phone}}</text></text><text>{{item.region}} {{item.detail}}</text><text class="status-chip">选择这个地址</text></button><button class="edit" @click="edit(item.id)">编辑</button></view><button class="primary-button" @click="edit()">新增收货地址</button><text class="demo-label">当前为本地测试地址，不会上传或产生配送。</text></view></template>
<style scoped>.address-item{display:flex;align-items:center;gap:20rpx;margin-bottom:24rpx;padding:28rpx}.address-main{flex:1;min-width:0;text-align:left;display:flex;flex-direction:column;gap:20rpx;font-size:29rpx;line-height:1.6}.phone{font-size:25rpx;color:#63636b;font-weight:400}.edit{font-size:27rpx;color:#246b50;min-height:88rpx;padding:16rpx}.empty{margin-bottom:28rpx}</style>
