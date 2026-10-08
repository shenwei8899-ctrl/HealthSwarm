<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { reactive,ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { backHome } from '../../utils/profile.js'
import { mockService } from '../../services/mock.js'
const form=reactive({name:'',phone:'',region:'',detail:''}),saving=ref(false),error=ref('')
onLoad(async o=>{if(o.id){const addresses=await mockService.addresses();Object.assign(form,addresses.find(a=>a.id===o.id)||{})}})
function sample(){Object.assign(form,{name:'测试收件人',phone:'13800000000',region:'上海市 徐汇区',detail:'示例路 88 号 1 幢 101 室（虚构）'})}
async function save(){if(saving.value)return;saving.value=true;error.value='';try{await mockService.saveAddress(form);backHome()}catch(e){error.value=e.message}finally{saving.value=false}}
</script>
<template><view class="screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">{{form.id?'编辑':'新增'}}收货地址</text><text></text></view></AppNavBar><view class="page-heading"><text class="display-title">填写配送信息</text><text class="subtitle">前端体验版，请使用虚构测试资料。</text></view><view class="card form"><text class="form-label">收件人</text><input v-model="form.name" class="field-input" placeholder="姓名或称呼"/><text class="form-label">联系电话</text><input v-model="form.phone" class="field-input" type="number" maxlength="11" placeholder="11 位手机号"/><text class="form-label">省、市、区</text><input v-model="form.region" class="field-input" placeholder="例如 上海市 徐汇区"/><text class="form-label">详细地址</text><textarea v-model="form.detail" class="text-area" placeholder="街道、门牌号等"/></view><text v-if="error" class="inline-error">{{error}}</text><button class="primary-button" :disabled="saving" @click="save">{{saving?'正在保存…':'保存并使用'}}</button><button class="secondary-button sample" @click="sample">填入虚构示例地址</button></view></template>
<style scoped>.form{padding:8rpx 28rpx 28rpx;margin-bottom:28rpx}.sample{margin-top:20rpx}</style>
