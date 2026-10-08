<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { computed, ref,watch } from 'vue'
import { onLoad,onShow } from '@dcloudio/uni-app'
import MemberFields from '../../components/MemberFields.vue'
import { backHome, getProfile, newMember, normalizeMember, saveProfile } from '../../utils/profile.js'
import { dataWarnings } from '../../utils/health.js'
const profile=ref(JSON.parse(JSON.stringify(getProfile()))), step=ref(0), memberIndex=ref(0), invited=ref(false), accepted=ref(false)
const current=computed(()=>profile.value.members[memberIndex.value])
onLoad(options=>{if(!options.member){const progress=uni.getStorageSync('frontend-onboarding-progress-v1');if(progress){profile.value=progress.profile;step.value=progress.step;memberIndex.value=progress.memberIndex}}if(options.member){invited.value=true;step.value=1;memberIndex.value=Math.max(0,profile.value.members.findIndex(m=>String(m.id)===options.member))}})
watch([profile,step,memberIndex],()=>{if(!invited.value)uni.setStorageSync('frontend-onboarding-progress-v1',{profile:profile.value,step:step.value,memberIndex:memberIndex.value})},{deep:true})
onShow(()=>{const fresh=getProfile();for(const m of profile.value.members){const updated=fresh.members.find(n=>n.id===m.id);if(updated){m.reports=updated.reports;m.reportStatus=updated.reportStatus}}})
const copy=[
['你想为谁安排饮食？','人数不会自动创建家庭档案。'],
['先认识每位成员','身高和体重可以稍后补充。'],
['饮食目标与基础健康','正在填写的成员资料独立保存。'],
['重要的限制，分开记录','未填写不等于没有，记录过敏、不耐受、忌口和医嘱。']]
function mode(value){profile.value.usageMode=value;if(value==='家庭使用'&&profile.value.sharedDinerCount<2)profile.value.sharedDinerCount=2}
function add(){profile.value.members.push(normalizeMember(newMember(profile.value.members.length)));memberIndex.value=profile.value.members.length-1}
function commit(){
 if(!current.value.name.trim())return uni.showToast({title:'请填写姓名／称呼',icon:'none'})
 if(current.value.healthStatus==='set'&&(!current.value.conditions.length || current.value.conditions.includes('其他')&&!current.value.otherCondition.trim()))return uni.showToast({title:'请补充具体基础病',icon:'none'})
 saveProfile(profile.value)
 if(step.value<3){step.value++;return}
 uni.setStorageSync('frontend-onboarded-v1',true);uni.setStorageSync('frontend-onboarding-progress-v1',null)
 uni.redirectTo({url:invited.value?'/pages/profile/index':'/pages/chat/index?from=onboarding'})
}
function next(){const warning=dataWarnings(current.value);if(warning.length&&!accepted.value){uni.showModal({title:'请复核档案信息',content:warning.join('；')+'。此提示不是医疗诊断。',cancelText:'返回修改',confirmText:'继续保存',success:r=>{if(r.confirm){accepted.value=true;commit()}}});return}accepted.value=false;commit()}
</script>
<template><view class="screen onboarding-screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="step>(invited?1:0)?step--:backHome()">‹</button><text class="nav-title">{{invited?'受邀成员建档':'家庭建档'}}</text><text class="pill">{{step+1}} / 4</text></view></AppNavBar><view class="progress"><view :style="{width:(step+1)*25+'%'}"></view></view><view class="question-head"><text class="demo-label">测试数据 · 请勿输入真实病历</text><text class="eyebrow">{{step+1}} / 4</text><text class="display-title">{{copy[step][0]}}</text><text class="helper">{{copy[step][1]}}</text></view><template v-if="step===0"><text class="label">使用方式</text><view class="mode-grid"><button v-for="value in ['个人使用','家庭使用']" :key="value" :class="{active:profile.usageMode===value}" @click="mode(value)">{{value}}</button></view><template v-if="profile.usageMode==='家庭使用'"><text class="label">平时几个人一起吃饭？</text><view class="mode-grid"><button v-for="n in [2,3,4]" :key="n" :class="{active:profile.sharedDinerCount===n}" @click="profile.sharedDinerCount=n">{{n===4?'4 人+':n+' 人'}}</button></view></template><text class="helper">不会自动新增家人记录。建档不收集收货地址和电话。</text></template><template v-else><text class="eyebrow current">正在填写：{{current.name}}</text><view v-if="!invited" class="member-tabs"><button v-for="(m,i) in profile.members" :key="m.id" :class="{active:memberIndex===i}" @click="memberIndex=i">{{m.name}}</button><button v-if="profile.usageMode==='家庭使用'" @click="add">＋ 添加家人</button></view><MemberFields :member="current" :sections="step===1?['basic']:step===2?['disease','preferences']:['restrictions','reports']"/></template><button class="primary-button next" @click="next">{{step===3?(invited?'保存，进入家庭':'完成建档，进入首页'):'保存并继续'}} →</button><button v-if="step===3" class="secondary-button" @click="next">稍后补充未填写的信息</button></view></template>
<style scoped>.onboarding-screen{padding-bottom:50rpx}.progress{height:6rpx;background:#dce7d4;margin:22rpx 0;border-radius:99rpx}.progress view{height:100%;background:#246b50}.question-head{display:flex;flex-direction:column;gap:16rpx;margin:38rpx 0}.question-head .display-title{font-size:48rpx}.helper{font-size:22rpx;line-height:1.7;color:#6b7a72;display:block;margin:22rpx 0}.mode-grid,.member-tabs{display:flex;flex-wrap:wrap;gap:14rpx;margin:20rpx 0}.mode-grid button,.member-tabs button{padding:20rpx 26rpx;background:#edf0e5;border-radius:20rpx;font-size:25rpx;color:#547060}.active{background:#246b50!important;color:#fff!important}.current{display:block;margin-bottom:16rpx}.next{margin-top:30rpx}.secondary-button{margin-top:16rpx}</style>
