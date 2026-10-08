<script setup>
import AppIcon from '../../components/AppIcon.vue'
import AppNavBar from '../../components/AppNavBar.vue'
import { computed,ref } from 'vue'
import { onLoad,onShow } from '@dcloudio/uni-app'
import { getProfile,backHome } from '../../utils/profile.js'
import { mockService } from '../../services/mock.js'
const id=ref(''),profile=ref(getProfile()),busy=ref(false)
const member=computed(()=>profile.value.members.find(m=>String(m.id)===id.value))
onLoad(o=>id.value=String(o.member||''));onShow(()=>profile.value=getProfile())
async function add(source){if(busy.value)return;busy.value=true;try{await mockService.addReport(id.value,source);profile.value=getProfile()}catch(e){uni.showToast({title:e.message,icon:'none'})}finally{busy.value=false}}
function open(report){uni.navigateTo({url:'/pages/reports/detail?member='+id.value+'&id='+report.id})}
</script>
<template><view class="screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">体检报告</text><text></text></view></AppNavBar><template v-if="member"><view class="page-heading"><text class="display-title">{{member.name}}的体检报告</text><text class="subtitle">报告始终归属当前成员，识别结果需要核对。</text></view><view v-if="!member.reports?.length" class="card empty"><text class="section-title">尚未上传报告</text><text class="demo-label">可以稍后补充，不影响浏览通用建议。</text></view><button v-for="report in member.reports||[]" :key="report.id" class="report card" @click="open(report)"><AppIcon name="record" :size="44"/><view><text>{{report.name}}</text><text>{{report.status==='done'?'已核对':'待核对'}} · {{report.shared?'已开启家庭共享':'仅本人'}}</text></view><text>›</text></button><view class="upload-actions"><button class="primary-button" :disabled="busy" @click="add('拍照上传')">{{busy?'正在创建示例…':'体验拍照上传'}}</button><button class="secondary-button" :disabled="busy" @click="add('微信聊天文件')">体验微信聊天文件</button></view><text class="demo-label">当前创建虚构报告样例，不读取或上传真实报告。真实文件能力在后续联调接入。</text></template><text v-else class="inline-error">成员不存在，请返回家庭档案。</text></view></template>
<style scoped>.report{width:100%;display:flex;align-items:center;gap:24rpx;text-align:left;padding:28rpx;margin:24rpx 0}.report>view{flex:1;display:flex;flex-direction:column;gap:12rpx}.report>view text:first-child{font-size:29rpx;font-weight:500}.report>view text:last-child{font-size:25rpx;color:#63636b}.upload-actions{display:flex;flex-direction:column;gap:20rpx;margin-top:28rpx}</style>
