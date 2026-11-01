<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import FamilyMemberCard from './FamilyMemberCard.vue'
import { createFamilyCardTransition, memberHealthSummary, restrictionProgress, FAMILY_CARD_DURATION } from '../utils/family-card-transition.js'
const props = defineProps({ members: { type: Array, default: () => [] }, scope: String, selfId: [String, Number], preferredId: [String, Number], canManage: Boolean })
const emit = defineEmits(['open', 'selected', 'manage'])
const motion = ref({ from: null, to: null, busy: false, ticket: 0, direction: 1 })
const transition = createFamilyCardTransition({ changed: value => { motion.value = value }, settled: id => emit('selected', id) })
watch(() => [props.members, props.scope], () => transition.reset(props.members, props.scope, props.preferredId || props.selfId), { immediate: true })
onUnmounted(() => transition.dispose())
const layers = computed(() => (motion.value.busy ? [{ member: motion.value.from, role: 'out' }, { member: motion.value.to, role: 'in' }] : motion.value.to ? [{ member: motion.value.to, role: 'rest' }] : []).map(layer => ({ ...layer, ticket: motion.value.ticket })))
const targetId = computed(() => String(motion.value.to?.id ?? ''))
const selectedIndex = computed(() => props.members.findIndex(m => String(m.id) === targetId.value))
let touch = null, suppressOpenUntil = 0
function choose(id) { transition.select(id) }
function nextMember() { if (!motion.value.busy && props.members.length > 1) choose(props.members[(selectedIndex.value + 1) % props.members.length].id) }
function open(member, section = 'basic') { if (!motion.value.busy && Date.now() >= suppressOpenUntil && String(member.id) === targetId.value) emit('open', member, section) }
function finish(event, ticket, role) {
 const name = event.animationName || event.detail?.animationName || ''
 if (role !== 'in' || event.target?.id !== event.currentTarget?.id || !name.startsWith('family-page-in')) return
 transition.finish(ticket, props.scope)
}
function touchStart(event) { const point = event.touches?.[0]; touch = point ? { x: point.clientX, y: point.clientY } : null }
function cancelTouch() { touch = null }
function touchEnd(event) {
 const point = event.changedTouches?.[0], start = touch; touch = null
 if (!point || !start) return
 const dx = point.clientX - start.x, dy = point.clientY - start.y
 if (Math.abs(dx) < 48 || Math.abs(dx) < Math.abs(dy) * 1.4) return
 suppressOpenUntil = Date.now() + 450
 const member = props.members[selectedIndex.value + (dx < 0 ? 1 : -1)]
 if (member) choose(member.id)
}
function restrictionText(member) { const p = restrictionProgress(member); return p.pending ? p.confirmed + ' 项已确认，' + p.pending + ' 项待确认' : '过敏、不耐受、忌口与医嘱已逐项确认' }
</script>
<template>
 <view class="family-member-deck">
  <scroll-view class="member-scroll" scroll-x :show-scrollbar="false" :scroll-into-view="'family-tab-'+selectedIndex" scroll-with-animation>
   <view class="member-switch-row" role="tablist" aria-label="选择家人档案">
    <button v-for="(member,index) in members" :id="'family-tab-'+index" :key="member.id" class="member-tab" :class="{selected:targetId===String(member.id)}" role="tab" :aria-selected="targetId===String(member.id)" :aria-label="'切换到'+member.name+'的档案'" @click="choose(member.id)"><text>{{String(member.id)===String(selfId)?'我':member.name||'家人'}}</text><view class="tab-dot"/></button>
    <button v-if="canManage" class="member-add" aria-label="管理家庭成员" @click="$emit('manage')">＋</button>
   </view>
  </scroll-view>
  <text class="switch-hint">{{members.length>1?'轻滑卡片，看看每位家人的档案':'一份属于你的健康档案'}}</text>
  <view class="deck-stage" :class="{'is-switching':motion.busy}" :aria-busy="motion.busy" :style="{'--card-direction':motion.direction,'--card-duration':FAMILY_CARD_DURATION+'ms'}" @touchstart="touchStart" @touchend="touchEnd" @touchcancel="cancelTouch">
   <view v-if="motion.to" class="deck-backing"><FamilyMemberCard :member="motion.to" :self-id="selfId" back-only/></view>
   <button v-if="members.length>1" class="deck-switch" :disabled="motion.busy" aria-label="切换下一位家人的档案" @click.stop="nextMember"><image src="/static/chat/nutrition-boy-v1.webp" mode="aspectFit" aria-hidden="true"/><text aria-hidden="true">⇄</text></button>
   <view v-for="layer in layers" :id="'family-page-'+layer.ticket+'-'+layer.role" :key="layer.ticket+'-'+layer.role+'-'+layer.member.id" class="member-page" :class="['page-'+layer.role,motion.direction<0?'direction-back':'direction-forward']" :aria-hidden="motion.busy?'true':'false'" @animationend="finish($event,layer.ticket,layer.role)">
    <FamilyMemberCard :member="layer.member" :self-id="selfId" front-only :disabled="motion.busy" @open="open"/>
   </view>
  </view>
  <view class="member-sections" :class="{'is-switching':motion.busy}" :style="{'--card-duration':FAMILY_CARD_DURATION+'ms'}">
   <view v-for="layer in layers" :key="layer.ticket+'-'+layer.role+'-'+layer.member.id" class="section-page" :class="'section-'+layer.role" :aria-hidden="motion.busy?'true':'false'">
     <button class="member-section" :disabled="motion.busy" :aria-label="'查看'+layer.member.name+'的健康与偏好'" @click="open(layer.member,'health')"><view class="section-copy"><text class="section-title">健康与偏好</text><text class="section-description">{{memberHealthSummary(layer.member)}}</text></view><text class="section-arrow">›</text></button>
     <button class="member-section" :disabled="motion.busy" :aria-label="'查看'+layer.member.name+'的饮食限制'" @click="open(layer.member,'restrictions')"><view class="section-copy"><text class="section-title">饮食限制</text><text class="section-description">{{restrictionText(layer.member)}}</text></view><text class="section-arrow">›</text></button>
   </view>
  </view>
 </view>
</template>
<style scoped>
.family-member-deck{position:relative}.member-scroll{width:100%;white-space:nowrap}.member-switch-row{display:inline-flex;align-items:center;gap:5px;min-width:100%;padding:4px 0}.member-tab{position:relative;flex:none;display:flex;align-items:center;justify-content:center;min-width:64px;max-width:136px;min-height:43px;padding:9px 18px 10px;border-radius:15px;background:transparent;border:1px solid transparent;color:#89808f;font-size:14px;line-height:1.5}.member-tab text{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.member-tab.selected{background:rgba(255,255,255,.92);border-color:#fff;color:#77618e;box-shadow:0 3px 12px rgba(84,68,111,.035)}.member-tab:after,.member-add:after{border:0}.tab-dot{position:absolute;bottom:5px;width:3px;height:3px;background:transparent;border-radius:50%}.selected .tab-dot{background:#b4a1d1}.member-add{display:flex;align-items:center;justify-content:center;flex:none;width:43px;height:43px;margin-left:3px;border-radius:15px;color:#9c8aaf;background:rgba(255,255,255,.46);font-size:21px}.switch-hint{display:block;min-height:23px;padding:7px 0 0 3px;color:#938a9c;font-size:10px;line-height:1.6}
.deck-stage{position:relative;height:416px;margin:0 3px;isolation:isolate}.deck-backing,.member-page{position:absolute;inset:0;width:100%;height:100%}.deck-backing{z-index:0}.member-page{z-index:2;transform-origin:50% 52%;will-change:transform,opacity}.member-sections{position:relative;height:152px;margin:16px 0 22px;border:1px solid rgba(255,255,255,.95);border-radius:23px;background:rgba(255,255,255,.88);box-shadow:0 5px 24px rgba(75,64,104,.025)}.section-page{position:absolute;left:17px;right:17px;top:0}
.member-section{display:flex;align-items:center;gap:11px;box-sizing:border-box;width:100%;height:75px;min-height:75px;padding:8px 0;background:transparent;text-align:left;line-height:1.5}.member-section+.member-section{border-top:1px solid #f0edf5}.member-section:after{border:0}.member-section[disabled]{background:transparent;opacity:1}.section-copy{flex:1;min-width:0}.member-section .section-title{display:block;font-size:14px;line-height:1.5;color:#5a4e66;font-weight:500}.section-description{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-top:4px;color:#8c8098;font-size:10px;line-height:1.6}.section-arrow{color:#b4a5bf;font-size:21px;flex:none}.is-switching .member-page,.is-switching .section-page{pointer-events:none}
.deck-switch{position:absolute;z-index:6;right:-11px;bottom:48px;width:44px;min-height:74px;padding:4px 0;border:0;background:transparent;transform:rotate(-7deg);display:flex;flex-direction:column;align-items:center;gap:4px;color:#9b8bbc;font-size:24px;line-height:1}.deck-switch:after{border:0}.deck-switch[disabled]{background:transparent;opacity:.5}.deck-switch:active{opacity:.7}.deck-switch image{width:25px;height:30px}
/* Reference frames 7–37: planar fan turn, fade through the canvas, then settle. */
.page-out{z-index:3;transform-origin:5% 5%;animation:family-page-out var(--card-duration) linear both}.page-in{z-index:2;transform-origin:5% 5%;animation:family-page-in var(--card-duration) linear both}
.is-switching .deck-backing{animation:family-backing var(--card-duration) linear both;transform-origin:50% 52%}.is-switching .deck-switch{animation:family-indicator var(--card-duration) linear both}
@keyframes family-page-out{
 0%,3%{opacity:1;transform:translate(0,0) rotate(0deg)}
 9%{opacity:.9;transform:translate(-.3%,1px) rotate(1.4deg)}
 15%{opacity:.6;transform:translate(-.8%,2px) rotate(3.2deg)}
 21%{opacity:.32;transform:translate(-1.5%,4px) rotate(5deg)}
 27%{opacity:.08;transform:translate(-2.2%,6px) rotate(6.8deg)}
 33%,100%{opacity:0;transform:translate(-3%,8px) rotate(8deg)}
}
@keyframes family-page-in{
 0%,51%{opacity:0;transform:translate(8%,-10px) rotate(-8.2deg)}
 57%{opacity:.12;transform:translate(7%,-9px) rotate(-7.5deg)}
 64%{opacity:.5;transform:translate(3%,-5px) rotate(-4.5deg)}
 70%{opacity:.86;transform:translate(1%,-1px) rotate(-2deg)}
 76%,100%{opacity:1;transform:translate(0,0) rotate(0deg)}
}
@keyframes family-backing{
 0%,6%{opacity:1;transform:translate(0,0) rotate(0deg)}
 18%{opacity:1;transform:translate(0,0) rotate(-1.5deg)}
 27%{opacity:.65;transform:translate(-6px,6px) rotate(2deg)}
 39%{opacity:.18;transform:translate(-17px,12px) rotate(6deg)}
 46%,61%{opacity:0;transform:translate(-20px,14px) rotate(7deg)}
 76%{opacity:.25;transform:translate(8px,-2px) rotate(-2deg)}
 91%,100%{opacity:1;transform:translate(0,0) rotate(0deg)}
}
@keyframes family-indicator{0%,18%{opacity:1}27%{opacity:.65}39%{opacity:.18}46%,61%{opacity:0}76%{opacity:.25}91%,100%{opacity:1}}
/* The two summary rows stay anchored; their old/new contents only change opacity. */
.section-out{animation:family-sections-out var(--card-duration) ease both}.section-in{animation:family-sections-in var(--card-duration) ease both}
@keyframes family-sections-out{0%{opacity:1}32%,100%{opacity:0}}
@keyframes family-sections-in{0%,51%{opacity:0}100%{opacity:1}}
@media(prefers-reduced-motion:reduce){.page-in,.page-out,.section-in,.section-out,.is-switching .deck-backing,.is-switching .deck-switch{animation-duration:1ms}}
@media(max-width:350px){.member-tab{min-width:58px;padding-left:14px;padding-right:14px}.deck-stage{margin-left:-3px;margin-right:-3px}.section-page{left:12px;right:12px}}

.member-tab.selected{color:#7847d9;font-weight:600}.switch-hint{color:#8186a1}.member-section .section-title{font-weight:600;color:#42455c}.section-description{font-weight:500;color:#7d839c}.section-arrow{color:#a38bc7}
</style>
