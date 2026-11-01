<script setup>
import { computed } from 'vue'
import { ageLabel } from '../utils/member-age.js'
import { memberGoalSummary, restrictionProgress } from '../utils/family-card-transition.js'
const props = defineProps({ member: Object, selfId: [String, Number], disabled: Boolean, frontOnly: Boolean, backOnly: Boolean })
defineEmits(['open'])
const progress = computed(() => restrictionProgress(props.member))
const name = computed(() => props.member?.name || '家人')
const relation = computed(() => String(props.member.id) === String(props.selfId) ? '本人' : props.member.relation || '家庭成员')
const age = computed(() => ageLabel(props.member) === '0 个月' ? '未满1个月' : ageLabel(props.member))
</script>
<template>
 <view class="member-card-object" :class="{'front-only':frontOnly}">
  <view v-if="!frontOnly" class="card-backplate" aria-hidden="true"><view class="backplate-ribbon"/></view>
  <view v-if="!backOnly" class="card-face">
   <view class="card-slot" aria-hidden="true"/>
   <view class="card-identity"><view class="card-avatar" aria-hidden="true"><view class="avatar-halo"/><text>{{name.slice(0,1)}}</text></view><view class="card-person"><text class="card-relation">{{relation}} · {{age}}</text><text class="card-name">{{name}}</text></view></view>
   <view class="card-facts"><view><text class="fact-label">性别</text><text class="fact-value">{{member.gender||'未填写'}}</text></view><view><text class="fact-label">身高</text><text class="fact-value">{{member.height?member.height+' cm':'待补充'}}</text></view><view><text class="fact-label">体重</text><text class="fact-value">{{member.weight?member.weight+' kg':'待补充'}}</text></view></view>
   <view class="card-goal"><text class="fact-label">饮食目标</text><text class="goal-value">{{memberGoalSummary(member)}}</text></view>
   <view class="card-watermark" aria-hidden="true"><view/><view/><view/></view>
   <view class="card-restrictions"><view class="restriction-dot"/><text>饮食限制</text><text class="restriction-value">{{progress.pending?'待确认 '+progress.pending+' 项':'4 项已确认'}}</text></view>
   <button class="card-open" :disabled="disabled" :aria-label="'查看'+name+'的完整健康档案'" @click="$emit('open',member)"><text>查看完整档案</text><text class="open-arrow">↗</text></button>
  </view>
 </view>
</template>
<style scoped>
.member-card-object{position:relative;width:100%;height:100%;perspective:1000px;isolation:isolate}
.card-backplate{position:absolute;inset:18px 3px 22px 27px;border:1px solid rgba(255,255,255,.92);border-radius:30px;background:linear-gradient(145deg,rgba(255,255,255,.76),rgba(233,230,246,.65));transform:translateX(8px) rotate(-7deg);transform-origin:50% 50%;overflow:hidden;box-shadow:0 8px 22px rgba(82,73,111,.035)}
.backplate-ribbon{position:absolute;left:44%;top:-20px;width:15px;height:65px;background:linear-gradient(90deg,rgba(255,255,255,.1),rgba(255,255,255,.8));transform:rotate(-25deg)}
.card-face{position:absolute;inset:20px 25px 8px 3px;display:flex;flex-direction:column;box-sizing:border-box;padding:38px 22px 7px;border:1px solid rgba(255,255,255,.96);border-radius:29px;background:linear-gradient(145deg,rgba(255,255,255,.98),rgba(248,247,253,.97));box-shadow:0 14px 30px rgba(77,66,111,.055),inset 0 1px 0 #fff;transform:rotate(1.2deg);transform-origin:50% 50%;overflow:hidden}
.card-slot{position:absolute;top:13px;left:50%;width:45px;height:5px;border-radius:99px;background:linear-gradient(180deg,#aaa0bf,#e8e4f1);transform:translateX(-50%);box-shadow:0 1px 0 #fff}
.card-identity{display:flex;align-items:center;gap:14px;min-height:60px;z-index:1;flex-shrink:0}.card-avatar{position:relative;display:flex;align-items:center;justify-content:center;flex:none;width:60px;height:60px;border-radius:50%;color:#9680b4;background:linear-gradient(150deg,#ded7f2,#f6f3fc);font-size:24px;font-weight:500}.avatar-halo{position:absolute;inset:5px;border:1px solid rgba(255,255,255,.6);border-radius:50%}.card-person{min-width:0;flex:1}.card-relation{display:block;font-size:11px;line-height:1.7;color:#888092;overflow-wrap:anywhere}.card-name{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;word-break:break-all;margin-top:3px;font-size:22px;line-height:1.35;color:var(--ui-text);font-weight:600}
.card-facts{display:grid;grid-template-columns:.85fr 1.15fr 1.15fr;gap:8px;flex-shrink:0;margin-top:24px;z-index:1}.fact-label{display:block;font-size:11px;line-height:1.6;color:#8b8496}.fact-value{display:block;margin-top:5px;font-size:14px;line-height:1.5;color:#494252;font-weight:500;overflow-wrap:anywhere}.card-goal{position:relative;z-index:1;margin-top:22px;min-height:43px;flex:1}.goal-value{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-top:4px;font-size:14px;line-height:1.6;color:#51475d}
.card-watermark{position:absolute;right:12px;top:47%;width:75px;height:62px;transform:rotate(-16deg);opacity:.27;pointer-events:none}.card-watermark view{position:absolute;inset:0;border:1px solid #d8d0e8;border-radius:50%}.card-watermark view:nth-child(2){inset:9px -9px -9px 9px}.card-watermark view:nth-child(3){inset:18px -18px -18px 18px}
.card-restrictions{position:relative;z-index:1;display:flex;align-items:center;gap:6px;flex-shrink:0;min-height:33px;margin-top:14px;padding:6px 8px;border-radius:11px;background:#f0ecf8;font-size:10px;line-height:1.6;color:#7a6c91}.restriction-dot{width:4px;height:4px;flex:none;border-radius:50%;background:#ab94c9}.restriction-value{margin-left:auto;color:#6d597e;font-size:11px;white-space:nowrap}.card-open{position:relative;z-index:1;display:flex;align-items:center;justify-content:center;gap:12px;flex-shrink:0;width:100%;min-height:45px;padding:6px 0;background:transparent;color:#7f6a9b;font-size:12px;line-height:1.5}.card-open:after{border:0}.card-open[disabled]{opacity:.65;color:#7f6a9b;background:transparent}.open-arrow{font-size:17px}
@media(max-width:350px){.card-face{padding-left:17px;padding-right:17px}.card-avatar{width:52px;height:52px}.card-name{font-size:20px}.card-identity{gap:11px}.card-facts{margin-top:19px}.card-goal{margin-top:18px}}

.card-relation,.fact-label{color:#747a94;font-size:12px;font-weight:500}.fact-value{font-weight:600;color:#41445c}.goal-value{font-weight:500;font-size:15px;color:#45465e}.card-name{font-weight:600;color:#303448}.card-avatar{color:#8264ce;background:linear-gradient(145deg,#d8d9ff,#edeaff)}.card-restrictions{background:#ede8ff;color:#7964a5;font-weight:600}.restriction-value{color:#7250b1;font-weight:600}.card-open{color:#6539b4;font-weight:600}
.front-only .card-face{background:linear-gradient(145deg,#fff,#f8f7fd)}
</style>
