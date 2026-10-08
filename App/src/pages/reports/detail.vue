<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { computed,ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getProfile,backHome } from '../../utils/profile.js'
import { mockService } from '../../services/mock.js'
const id=ref(''),memberId=ref(''),profile=ref(getProfile()),shared=ref(false),busy=ref(false)
const member=computed(()=>profile.value.members.find(m=>String(m.id)===memberId.value)),report=computed(()=>member.value?.reports?.find(r=>r.id===id.value))
const canShare=computed(()=>member.value?.claimedBy&&(member.value.claimedBy===profile.value.viewerAccount||member.value.relation==='本人'&&(!profile.value.viewerAccount||profile.value.viewerAccount==='creator')))
onLoad(o=>{id.value=o.id;memberId.value=String(o.member);shared.value=Boolean(report.value?.shared)})
async function confirm(){if(busy.value||!report.value)return;busy.value=true;try{await mockService.confirmReport(memberId.value,id.value,canShare.value?shared.value:report.value.shared);profile.value=getProfile();uni.showToast({title:'核对状态已保存',icon:'success'})}catch(error){uni.showToast({title:error.message||'保存失败，请重试',icon:'none'})}finally{busy.value=false}}
</script>
<template><view class="screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">报告核对</text><text></text></view></AppNavBar><template v-if="report"><view class="page-heading"><text class="display-title">{{report.name}}</text><text class="subtitle">归属：{{member.name}} · {{report.status==='done'?'已核对':'待核对'}}</text></view><view class="list-card card"><text class="section-title">示例识别内容</text><text>这是一份用于前端评审的虚构报告，不包含真实检验数值。</text><text>识别内容不会自动变成确诊结果，也不会自动写入基础病。</text></view><view class="list-card card"><text class="section-title">家庭共享</text><template v-if="canShare"><text>由本人决定是否向家庭成员开放此报告。</text><switch :checked="shared" color="#246b50" @change="shared=$event.detail.value"/></template><text v-else>共享授权需由本人设置，家人代管资料不自动开放报告。</text></view><button class="primary-button" :disabled="busy" @click="confirm">{{busy?'正在保存…':'已核对，保存状态'}}</button><text class="demo-label">测试数据 · 本次核对不输出医疗诊断</text></template><text v-else class="inline-error">报告不存在或已不可访问。</text></view></template>
