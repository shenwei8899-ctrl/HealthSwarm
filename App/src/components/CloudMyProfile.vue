<script setup>
import { ref, computed, onMounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'
import MenuGroup from './MenuGroup.vue'
import { loadCloudProfile } from '../services/cloud-profile.js'
import { getSession } from '../services/session.js'
import { accountSettings } from '../services/account-settings.js'
import { wechatAuth } from '../services/wechat-auth.js'
import { isCommerceEnabled } from '../services/config.js'
const profile=ref(null),busy=ref(false),error=ref(''),avatar=ref(''),accountNickname=ref('')
let avatarEpoch=0
async function loadAvatar(){const mine=++avatarEpoch;try{const result=await accountSettings.profile();if(mine===avatarEpoch){avatar.value=result.avatar;accountNickname.value=result.nickname}}catch{if(mine===avatarEpoch){avatar.value='';accountNickname.value=''}}}
const entering=ref(true)
function finishEntrance(event){if(event.target?.id===event.currentTarget?.id)entering.value=false}
const name=computed(()=>accountNickname.value||getSession()?.accountName||profile.value?.members.find(m=>m.relation==='本人')?.name||'我')
const unavailableFeatures = {

  devices: '健康设备',
}
const dietItems = [
  { icon: 'journal', name: '饮食记录', desc: '', url: '/pages/records/index' },
  { icon: 'chat', name: '饮食反馈', desc: '', url: '/pages/feedback/index' },
]
const planItems = [
  { icon: 'plan', name: 'AI专属计划', desc: '查看当前可用计划与安排', url: '/pages/exclusive-plans/index' },
  { icon: 'menu', name: '我的餐单', desc: '', url: '/pages/health/plans' },
  ...(isCommerceEnabled ? [
    { icon: 'receipt', name: '我的订单', desc: '', url: '/pages/orders/index' },
  ] : []),
]
const profileItems = [
  { icon: 'memory', name: 'AI 记住的事', desc: '', url: '/pages/memories/index' },
  { icon: 'device', name: '健康设备', desc: '设备连接尚未开放', url: 'devices' },
]
const settingItems = [
  { icon: 'shield', name: '隐私与账号', desc: '', url: '/pages/settings/privacy' },
  ...(isCommerceEnabled ? [{ icon: 'pin', name: '收货地址', desc: '', url: '/pages/address/index' }] : []),
  { icon: 'supplier', name: '合作商合作', desc: '填写合作申请', url: '/pages/supplier/index' },
]
let epoch=0
async function load(){if(busy.value)return;const mine=++epoch;profile.value=null;error.value='';busy.value=true;try{const account=await wechatAuth.restore();if(mine!==epoch)return;if(!account){uni.reLaunch({url:'/pages/index/index'});return}const result=await loadCloudProfile({openConsultation:false,readConfiguration:false});if(mine===epoch)profile.value=result}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch)busy.value=false}}
function discard(){epoch++;busy.value=false;profile.value=null;error.value=''}
onMounted(load);onShow(()=>{void load();void loadAvatar()});onHide(()=>{avatarEpoch++;avatar.value='';accountNickname.value='';entering.value=false;discard()})
function go(url){if(Object.hasOwn(unavailableFeatures,url)){unavailable(unavailableFeatures[url]);return}uni.navigateTo({url})}
function unavailable(name){uni.showModal({title:name,content:'这项功能的正式服务尚未接入，开通后可在这里使用。',showCancel:false})}
function logout(){uni.showModal({title:'退出账号？',content:'已保存的云端家庭资料不会删除。',success:r=>{if(r.confirm){discard();wechatAuth.logout();uni.reLaunch({url:'/pages/index/index'})}}})}

// Reuse the existing entries and commerce visibility; only their presentation changes.
const quickItems=[planItems[0],planItems[1],dietItems[0],profileItems[0]]
const commerceItems=isCommerceEnabled?[...planItems.slice(2),settingItems.find(item=>item.url==='/pages/address/index')]:[]
const serviceItems=[dietItems[1],profileItems[1],settingItems.find(item=>item.url==='/pages/supplier/index')]
</script>
<template>
  <view id="my-page" class="screen cloud-my" :class="{'is-entering':entering}" @animationend="finishEntrance">
    <AppNavBar title="我的"><template #left><button class="icon-button" aria-label="返回" @click="uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/chat/index'})})">‹</button></template></AppNavBar>
    <view class="profile-heading">
      <view class="profile-avatar"><image v-if="avatar" class="personal-avatar" :src="avatar" mode="aspectFill" @error="avatar=''"/><AppIcon v-else name="user" :size="56"/></view>
      <view class="profile-identity"><text class="profile-name">{{name}}</text><text class="profile-caption">照顾自己，也照顾家人的每一餐</text></view>
      <button class="settings-button" aria-label="设置" @click="go('/pages/settings/index')"><image src="/static/my/settings.svg" mode="aspectFit" class="settings-icon"/></button>
    </view>
    <view v-if="error" class="error-state"><text class="inline-error">{{error}}</text><button class="secondary-button" @click="load">重新读取</button></view>
    <button class="family-card my-surface" @click="go('/pages/profile/index')">
      <view class="family-copy"><text class="family-title">家庭档案</text><text class="family-caption">{{profile ? profile.members.length+' 位成员 · 家庭健康档案' : '查看与管理家庭健康档案'}}</text></view>
      <view class="family-cta"><text>管理档案</text><text class="cta-arrow">›</text></view>
    </button>
    <view class="mode-row"><text>使用方式</text><view v-if="profile"><text>{{profile.usageMode}}</text><button @click="go('/pages/onboarding/index')">更改 <text>›</text></button></view><text v-else class="mode-loading" role="status">{{busy?'正在读取云端资料…':'—'}}</text></view>
    <view class="quick-section my-surface">
      <view class="quick-grid">
        <button v-for="item in quickItems" :key="item.url" class="quick-item" hover-class="feature-pressed" :hover-start-time="0" :hover-stay-time="60" :aria-label="item.name" @click="go(item.url)"><view class="feature-icon-wrap" aria-hidden="true"><view class="feature-symbol" :class="'symbol-'+item.icon"><view class="feature-icon" :class="'feature-'+item.icon"/></view></view><text>{{item.name}}</text></button>
      </view>
    </view>
    <view v-if="commerceItems.length" class="commerce-section my-surface">
      <view class="section-heading"><text>订单与配送</text></view>
      <view class="commerce-grid"><button v-for="item in commerceItems" :key="item.url" class="commerce-item" hover-class="feature-pressed" :hover-start-time="0" :hover-stay-time="60" :aria-label="item.name" @click="go(item.url)"><view class="feature-icon-wrap" aria-hidden="true"><view class="feature-symbol" :class="'symbol-'+item.icon"><view class="feature-icon" :class="'feature-'+item.icon"/></view></view><text>{{item.name}}</text></button></view>
    </view>
    <view class="service-section"><text class="service-title">其他服务</text>
      <button v-for="item in serviceItems" :key="item.url" class="service-row" @click="go(item.url)"><text>{{item.name}}</text><view><text v-if="item.desc" class="service-hint">{{item.desc}}</text><text class="row-arrow">›</text></view></button>
    </view>
  </view>
</template>
<style scoped>
.cloud-my{background:#f5f6fa;background-image:radial-gradient(ellipse at 0% 0%,rgba(125,174,255,.44),transparent 70%),radial-gradient(ellipse at 100% 0%,rgba(206,178,245,.38),transparent 76%);background-size:100% 410rpx;background-repeat:no-repeat;color:var(--ui-text);padding-left:36rpx;padding-right:36rpx;padding-bottom:calc(env(safe-area-inset-bottom) + 48rpx)}
/* Clear the class on completion/hide: display:none can restart retained CSS animations. */
.cloud-my.is-entering{animation:my-page-appear 260ms ease-out both}
@keyframes my-page-appear{from{opacity:0}to{opacity:1}}
.profile-heading{display:flex;align-items:center;gap:22rpx;margin:36rpx 0 40rpx}
.profile-avatar{display:flex;align-items:center;justify-content:center;width:124rpx;height:124rpx;flex:none;background:rgba(255,255,255,.78);color:#686371;border-radius:50%;box-shadow:inset 0 1px 0 #fff}
.personal-avatar{display:block;width:100%;height:100%;border-radius:50%}
.profile-identity{flex:1;min-width:0;display:flex;flex-direction:column;gap:12rpx}.profile-name{font-size:20px;font-weight:500;line-height:1.4;overflow-wrap:anywhere}.profile-caption{font-size:12px;color:var(--ui-muted);line-height:1.6}
.settings-button{width:84rpx;min-width:44px;height:88rpx;min-height:44px;display:flex;align-items:center;justify-content:center;flex:none}.settings-icon{width:42rpx;height:42rpx;opacity:.68}
/* Match the chat composer's frame; keep this treatment local to the three My cards. */
.my-surface{box-sizing:border-box;background:linear-gradient(180deg,rgba(255,255,255,.30),rgba(255,255,255,.96));border:1px solid rgba(255,255,255,.88);border-radius:19px;box-shadow:inset 0 1px 0 #fff}
.family-card{display:flex;align-items:center;justify-content:space-between;gap:24rpx;width:100%;min-height:180rpx;padding:32rpx;color:var(--ui-text);text-align:left}
.family-copy{display:flex;flex-direction:column;gap:14rpx;min-width:0}.family-title{font-size:18px;font-weight:500;line-height:1.4;overflow-wrap:anywhere}.family-caption{font-size:12px;color:var(--ui-muted);line-height:1.6}
.family-cta{display:flex;align-items:center;justify-content:center;gap:12rpx;flex:none;min-height:68rpx;padding:0 22rpx;border-radius:10rpx;background:#eef0f8;color:#5e596e;font-size:13px}.cta-arrow{font-size:32rpx}
.mode-row{display:flex;align-items:center;justify-content:space-between;gap:12rpx;min-height:88rpx;font-size:12px;color:var(--ui-muted)}.mode-row>view{display:flex;align-items:center;gap:20rpx}.mode-row button{display:flex;align-items:center;gap:12rpx;min-height:44px;color:var(--ui-text);font-size:12px}.mode-loading{font-size:12px;color:var(--ui-muted)}
.quick-section{padding:18px 6px 10px}.quick-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:2px}.quick-item{display:flex;flex-direction:column;align-items:center;justify-content:flex-start;gap:6px;min-height:80px;padding:0;color:#686371;font-size:12px;line-height:1.5;text-align:center}.quick-item text{max-width:100%;min-height:36px;overflow-wrap:anywhere}
.commerce-section{margin-top:16px;padding:18px 16px 16px}.section-heading{font-size:16px;font-weight:500}.commerce-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding-top:18px}.commerce-item{display:flex;flex-direction:column;align-items:center;gap:6px;font-size:13px;line-height:1.5;min-height:72px;color:#686371}
.service-section{padding-top:32rpx}.service-title{display:block;font-size:16px;font-weight:500;margin-bottom:8rpx}.service-row{width:100%;display:flex;align-items:center;justify-content:space-between;gap:20rpx;min-height:56px;border-bottom:1px solid rgba(255,255,255,.65);text-align:left;font-size:16px}.service-row:last-child{border-bottom:0}.service-row>view{display:flex;align-items:center;gap:18rpx;flex-shrink:1;min-width:0}.service-hint{font-size:12px;color:var(--ui-muted);text-align:right}.row-arrow{font-size:38rpx;color:#928e9e;flex:none}
.error-state{padding:16rpx 0 24rpx}.quick-item:active,.commerce-item:active,.service-row:active,.settings-button:active{opacity:.6}.family-card:active{background:#f1f2f9}
@media(max-width:350px){.profile-heading{gap:16rpx}.profile-caption{font-size:12px}.family-card{padding:28rpx 24rpx;gap:16rpx}.family-cta{padding:0 18rpx}.quick-item{font-size:11px}.commerce-item{font-size:12px}.service-hint{max-width:230rpx}}
.icon-button{min-width:44px;min-height:44px}

/* Lucide-derived icons share one transparent sprite; no runtime requests. */
.feature-icon-wrap{display:flex;align-items:center;justify-content:center;flex:none;width:40px;height:40px}
/* Preserve the existing glyph sprite; recolor only its rendered pixels to white. */
.feature-symbol{--symbol-start:#c3a4ff;--symbol-end:#8557ed;--symbol-shadow:rgba(123,84,216,.2);--symbol-tilt:-4deg;--symbol-turn:4deg;display:flex;align-items:center;justify-content:center;flex:none;width:34px;height:34px;border-radius:10px;color:#fff;background:linear-gradient(140deg,var(--symbol-start),var(--symbol-end));box-shadow:inset 1px 1px 1px rgba(255,255,255,.7),0 4px 7px var(--symbol-shadow);transform:rotate(var(--symbol-tilt));transition:transform 160ms cubic-bezier(.2,.8,.2,1.2),box-shadow 160ms ease-out}
.symbol-menu{--symbol-start:#a0e5d1;--symbol-end:#46b69f;--symbol-shadow:rgba(66,167,144,.18)}
.symbol-menu{--symbol-tilt:4deg;--symbol-turn:-4deg}
.symbol-journal{--symbol-start:#ffcb91;--symbol-end:#f27350;--symbol-shadow:rgba(232,136,76,.18)}
.symbol-pin{--symbol-start:#9bd3fa;--symbol-end:#599bdc;--symbol-shadow:rgba(76,142,202,.18)}
.symbol-memory{--symbol-start:#b7c2ff;--symbol-end:#7e84dc;--symbol-shadow:rgba(115,119,198,.18)}
.symbol-receipt{--symbol-start:#ffbe95;--symbol-end:#ed886c;--symbol-shadow:rgba(220,128,96,.18);--symbol-tilt:4deg;--symbol-turn:-4deg}
.feature-icon{display:block;width:24px;height:24px;flex:none;background-image:url("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAYAAAAAwAQMAAAAitD89AAAABlBMVEVTW2BTW2Ahn79hAAAAAnRSTlMA/1uRIrUAAANVSURBVHjatZWxihxHEIa/rh12Giy0E25wul2MQwcXSuZ8OzZ+D2+o8JwZs2Z7weDLfLHAID+CX+AYibN1gYN7AjMnXaCwTyhoi2HKQc/Mzs4eBhvcwcB0V1X/VX/V3/BfVvYvbAXgU8bjMeSwru+1Ko8OxkBaNP/HpJOU1GNU3T32JtTrmYvhhJk6sFhs32ZKqlq2f6lxJRhnHMKS/EsAjkAgjyafMIVpH3ceTwVHg2wBBy+Sxy3KOSRAngDl1W0FyZ09QgyMNg7gO1hCGh0ceYz8/CPg9rOfn4I9/2DBFEzUTyYTvEeLkcY0PafwEPApjAoYFcwgIALZWxttTIwNiMeBAePp6vYIvkIA39XmclFdApCU91T3GF7HAkwDQInUcOEAbEuRlFW+x/Q7rrcbMYesxZEUzNujb427QwBd542ruobp2TbCtln8w9PgZBfmpvk/aTes0wyMBjBktiHxYpCdZzVs0QQo50mFDEsxchhrQvs7gbPu7MnH7Ds8WCKJ+N3NmgogeHIB+KM/TBmJbGk4hEtQ06KP30Boyglzi/2lo4HjPghnQDDqAN+C+NyRnZ5vGh5mP6q+CEPicqi6cq8umYWvpaF3DrHLgRqnFAIU4zYrMAFOquFk90ZXAAzqmnvFV6zqqpt+gKqdRJuBoMZZOG+kJilzE7RDfbv5ZiJXbT1e/bnPgy2c+J5Q5W0/FUBZJXsO2SYMZ0FAjXEoPtBrvpioit+SMAz27twiGK071YDDpMw2zrh+lDaAU6cIxFFuVmULlVy6KVv8dNeVzEIWxyaCcc2s1Ri3x0PZ3tRL+jlAPqNC8j3JziLjhwhqGqcbgHDC22Gy7X2vG73cWenurOnNk0cWanzMdYU0+Bqs5dm2NXuZqJlH/QrIzgMkGded4XgZz7pnIDjjB8oHLu9Snk4HcKtcykEOtf91C2Q5Bs7oZhHmSezW+Rbr/Lp9UTDff+EgffWmA1BntthXjW5D3l/nUPSkT23m9h22euPDUe+NK4AfZpDUbFHutpr5oHAF72H6+8H0N3h58hJhodqhXKh2rRaF+S9jMpg/PkiAmxUk2hNojZEvAOUZPBvc7APAWjXABPCsVet/eNjTEmCm6mEM5Mx6kPprOX2Q7jbL/7j+BnzwMCRkX0FhAAAAAElFTkSuQmCC");background-size:192px 24px;background-repeat:no-repeat}
.feature-plan{background-position:0 0}.feature-menu{background-position:-24px 0}.feature-journal{background-position:-48px 0}.feature-memory{background-position:-96px 0}.feature-receipt{background-position:-144px 0}.feature-pin{background-position:-168px 0}
.feature-symbol .feature-icon{filter:brightness(0) invert(1);transform:rotate(var(--symbol-turn)) scale(.916667)}
.quick-item:active,.commerce-item:active,.quick-item.feature-pressed,.commerce-item.feature-pressed{opacity:1}
.quick-item:active .feature-symbol,.commerce-item:active .feature-symbol,.feature-pressed .feature-symbol{transform:translateY(1px) rotate(var(--symbol-tilt)) scale(.94);box-shadow:inset 1px 1px 1px rgba(255,255,255,.7),0 2px 4px var(--symbol-shadow)}
.quick-item:focus-visible,.commerce-item:focus-visible{outline:2px solid #8c9992;outline-offset:2px;border-radius:12px}

@media(prefers-reduced-motion:reduce){.cloud-my.is-entering{animation:none}.feature-symbol{transition:none}}
</style>
