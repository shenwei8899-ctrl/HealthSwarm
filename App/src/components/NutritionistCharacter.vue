<script setup>
import {computed} from 'vue'

const props=defineProps({
 size:{type:Number,default:180},
 unit:{type:String,default:'px',validator:value=>['px','rpx'].includes(value)},
 variant:{type:String,default:'hero',validator:value=>['hero','avatar'].includes(value)},
 state:{type:String,default:'idle',validator:value=>['idle','thinking','planning','success'].includes(value)},
 decorative:Boolean
})
const stateLabels={idle:'少年饮食小助手',thinking:'正在认真思考',planning:'正在为你搭配餐单',success:'餐单准备好啦'}
const visualState=computed(()=>Object.prototype.hasOwnProperty.call(stateLabels,props.state)?props.state:'idle')
const frameStyle=computed(()=>({width:props.size+props.unit,height:props.size+props.unit}))
</script>
<template>
 <view class="nutritionist-character" :class="['character-'+variant,'state-'+visualState]" :style="frameStyle" role="img" :aria-hidden="decorative?'true':undefined" :aria-label="decorative?undefined:stateLabels[visualState]">
  <view class="character-portrait"><image class="character-image" src="/static/chat/nutrition-boy-v1.png" mode="aspectFit" aria-hidden="true"/></view>
  <view v-if="visualState!=='idle'" class="character-status" aria-hidden="true">
   <text v-if="visualState==='success'" class="status-check">✓</text>
   <view v-else class="status-dots"><view/><view/><view/></view>
   <text v-if="variant==='hero'" class="status-label">{{stateLabels[visualState]}}</text>
  </view>
 </view>
</template>
<style scoped>
.nutritionist-character{position:relative;display:inline-block;flex:none;box-sizing:border-box;vertical-align:middle}
.character-portrait{position:relative;width:100%;height:100%;transform-origin:50% 80%}.character-image{display:block;width:100%;height:100%}
.character-hero.state-idle .character-portrait{animation:character-welcome 1.6s ease-in-out 1}
.character-hero.state-thinking .character-portrait{animation:character-consider 2.4s ease-in-out 2}
.character-hero.state-planning .character-portrait{animation:character-breathe 3.6s ease-in-out 2}
.character-hero.state-success .character-portrait{animation:character-acknowledge .75s ease-out 1}
.character-avatar .character-portrait{overflow:hidden;border-radius:50%;background:#f0e9fb}.character-avatar .character-image{position:absolute;left:-40%;top:-20%;width:175%;height:175%}
.character-status{position:absolute;z-index:1;left:50%;bottom:0;display:flex;align-items:center;justify-content:center;gap:6px;min-height:26px;padding:3px 10px;border:1px solid rgba(255,255,255,.94);border-radius:18px;background:rgba(255,255,255,.94);box-shadow:0 3px 10px rgba(121,99,170,.1);color:#78658f;transform:translateX(-50%);white-space:nowrap;box-sizing:border-box}
.status-label{font-size:11px;line-height:1.5}.status-check{color:#5d9c83;font-size:14px;font-weight:600;line-height:1}.status-dots{display:flex;align-items:center;justify-content:center;gap:3px;height:12px}.status-dots>view{width:3px;height:3px;border-radius:50%;background:#ab8fd5}
.character-hero .status-dots>view{animation:character-dot 1.2s ease-in-out infinite}.character-hero .status-dots>view:nth-child(2){animation-delay:.15s}.character-hero .status-dots>view:nth-child(3){animation-delay:.3s}
.state-planning .status-dots>view{background:#79ad96}.state-success .character-status{color:#648a77;background:#f4fff8}
.character-avatar .character-status{left:auto;right:-6%;bottom:-12%;min-height:0;width:34%;height:34%;padding:0;border:1px solid #fff;transform:none;box-shadow:none}.character-avatar .status-check{font-size:8px}.character-avatar .status-dots{gap:1px;height:auto}.character-avatar .status-dots>view{width:2px;height:2px}.character-avatar.state-thinking .character-status{background:#e7dcf7}.character-avatar.state-planning .character-status{background:#def1e7}
@keyframes character-welcome{0%,100%{transform:translateY(0) rotate(0)}28%{transform:translateY(-2px) rotate(-1.5deg)}58%{transform:translateY(-1px) rotate(1deg)}80%{transform:translateY(0) rotate(-.4deg)}}
@keyframes character-consider{0%,100%{transform:translateY(0) rotate(0)}40%{transform:translateY(1px) rotate(1deg)}70%{transform:translateY(0) rotate(-.4deg)}}
@keyframes character-breathe{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-1px) scale(1.01)}}
@keyframes character-acknowledge{0%,100%{transform:translateY(0) rotate(0)}38%{transform:translateY(-3px) rotate(-1deg)}72%{transform:translateY(-1px) rotate(.4deg)}}
@keyframes character-dot{0%,70%,100%{opacity:.4;transform:translateY(0)}35%{opacity:1;transform:translateY(-2px)}}
@media(prefers-reduced-motion:reduce){.character-hero .character-portrait,.character-hero .status-dots>view{animation:none}}
</style>
