<script setup>
import {computed,ref,watch,onMounted,onUnmounted} from 'vue'
import {onShow,onHide} from '@dcloudio/uni-app'

const props=defineProps({
 size:{type:Number,default:180},
 unit:{type:String,default:'px',validator:value=>['px','rpx'].includes(value)},
 variant:{type:String,default:'hero',validator:value=>['hero','avatar'].includes(value)},
 state:{type:String,default:'idle',validator:value=>['idle','thinking','planning','success'].includes(value)},
 decorative:Boolean,
 animated:{type:Boolean,default:true}
})
const stateLabels={idle:'少年饮食小助手',thinking:'正在认真思考',planning:'正在为你搭配餐单',success:'餐单准备好啦'}
const visualState=computed(()=>Object.prototype.hasOwnProperty.call(stateLabels,props.state)?props.state:'idle')
const frameSize=computed(()=>Number.isFinite(props.size)&&props.size>0?props.size:180)
const frameUnit=computed(()=>props.unit==='rpx'?'rpx':'px')
const frameStyle=computed(()=>({width:frameSize.value+frameUnit.value,height:frameSize.value+frameUnit.value}))
const spriteStyle=computed(()=>({width:frameSize.value*2+frameUnit.value,height:frameSize.value*2+frameUnit.value}))
const active=ref(true),reducedMotion=ref(false),posterFailed=ref(false),spriteFailed=ref(false),spriteReady=ref(false)
const showSprite=computed(()=>props.variant==='hero'&&props.animated&&active.value&&!reducedMotion.value&&!spriteFailed.value)
const posterCovered=computed(()=>showSprite.value&&spriteReady.value)
watch(showSprite,()=>{spriteReady.value=false},{flush:'sync'})
function spriteLoaded(){if(showSprite.value)spriteReady.value=true}
function spriteError(){spriteFailed.value=true;spriteReady.value=false}
let motionQuery=null
function motionPreference(event){reducedMotion.value=event.matches===true}
onMounted(()=>{
 if(typeof globalThis.matchMedia==='function'){
  motionQuery=globalThis.matchMedia('(prefers-reduced-motion: reduce)');motionPreference(motionQuery)
  motionQuery.addEventListener?.('change',motionPreference)
 }
})
onShow(()=>{active.value=true});onHide(()=>{active.value=false;spriteReady.value=false})
onUnmounted(()=>{active.value=false;motionQuery?.removeEventListener?.('change',motionPreference)})
</script>
<template>
 <view class="nutritionist-character" :class="['character-'+variant,'state-'+visualState,{'motion-off':!showSprite}]" :style="frameStyle" role="img" :aria-hidden="decorative?'true':undefined" :aria-label="decorative?undefined:stateLabels[visualState]">
  <view class="character-portrait" :style="frameStyle">
   <image v-if="!posterFailed" class="character-image character-poster" :class="{'poster-covered':posterCovered}" :style="frameStyle" src="/static/chat/nutrition-boy-v2-poster.png" mode="aspectFit" aria-hidden="true" @error="posterFailed=true"/>
   <view v-else-if="!posterCovered" class="character-fallback" :style="frameStyle" aria-hidden="true"><text>👦</text></view>
   <image v-if="showSprite" class="character-sprite" :class="{'is-ready':spriteReady}" :style="spriteStyle" src="/static/chat/nutrition-boy-v2-sprite.webp" mode="scaleToFill" aria-hidden="true" @load="spriteLoaded" @error="spriteError"/>
  </view>
  <view v-if="visualState!=='idle'" class="character-status" aria-hidden="true">
   <text v-if="visualState==='success'" class="status-check">✓</text>
   <view v-else class="status-dots"><view/><view/><view/></view>
   <text v-if="variant==='hero'" class="status-label">{{stateLabels[visualState]}}</text>
  </view>
 </view>
</template>
<style scoped>
.nutritionist-character{position:relative;display:inline-block;flex:none;box-sizing:border-box;vertical-align:middle;line-height:0}
.character-portrait{position:relative;overflow:hidden;transform-origin:50% 80%}.character-image{display:block}.character-poster{opacity:1}.character-poster.poster-covered{opacity:0}
.character-sprite{position:absolute;left:0;top:0;display:block;max-width:none;opacity:0;pointer-events:none;animation:boy-greeting 8.4s step-end infinite}.character-sprite.is-ready{opacity:1}
.character-fallback{display:flex;align-items:center;justify-content:center;border-radius:50%;background:#eaf2eb;line-height:1}.character-fallback>text{font-size:32px}
.character-hero.state-idle .character-portrait{animation:character-breathe 5s ease-in-out infinite}
.character-hero.state-thinking .character-sprite,.character-hero.state-planning .character-sprite{animation:boy-blink 6s step-end infinite}
.character-hero.state-planning .character-portrait{animation:character-breathe 3.6s ease-in-out infinite}
.character-hero.state-success .character-portrait{animation:character-acknowledge .75s ease-out 1}
.character-avatar .character-portrait{border-radius:50%;background:#f0e9fb}.character-avatar .character-image{position:absolute;left:-40%;top:-20%;transform:scale(1.75);transform-origin:0 0}
.character-status{position:absolute;z-index:1;left:50%;bottom:0;display:flex;align-items:center;justify-content:center;gap:6px;min-height:26px;padding:3px 10px;border:1px solid rgba(255,255,255,.94);border-radius:18px;background:rgba(255,255,255,.94);box-shadow:0 3px 10px rgba(121,99,170,.1);color:#78658f;transform:translateX(-50%);white-space:nowrap;box-sizing:border-box}
.status-label{font-size:11px;line-height:1.5}.status-check{color:#5d9c83;font-size:14px;font-weight:600;line-height:1}.status-dots{display:flex;align-items:center;justify-content:center;gap:3px;height:12px}.status-dots>view{width:3px;height:3px;border-radius:50%;background:#ab8fd5}
.character-hero .status-dots>view{animation:character-dot 1.2s ease-in-out infinite}.character-hero .status-dots>view:nth-child(2){animation-delay:.15s}.character-hero .status-dots>view:nth-child(3){animation-delay:.3s}
.state-planning .status-dots>view{background:#79ad96}.state-success .character-status{color:#648a77;background:#f4fff8}
.character-avatar .character-status{left:auto;right:-6%;bottom:-12%;min-height:0;width:34%;height:34%;padding:0;border:1px solid #fff;transform:none;box-shadow:none}.character-avatar .status-check{font-size:8px}.character-avatar .status-dots{gap:1px;height:auto}.character-avatar .status-dots>view{width:2px;height:2px}.character-avatar.state-thinking .character-status{background:#e7dcf7}.character-avatar.state-planning .character-status{background:#def1e7}
@keyframes boy-greeting{0%{transform:translate(0,0)}3%{transform:translate(-50%,0)}5.5%{transform:translate(-50%,-50%)}8%{transform:translate(-50%,0)}10.5%{transform:translate(-50%,-50%)}13%{transform:translate(0,0)}60%{transform:translate(0,-50%)}61.5%,100%{transform:translate(0,0)}}
@keyframes boy-blink{0%,56%,59%,100%{transform:translate(0,0)}57%{transform:translate(0,-50%)}}
@keyframes character-breathe{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-1px) scale(1.01)}}
@keyframes character-acknowledge{0%,100%{transform:translateY(0) rotate(0)}38%{transform:translateY(-3px) rotate(-1deg)}72%{transform:translateY(-1px) rotate(.4deg)}}
@keyframes character-dot{0%,70%,100%{opacity:.4;transform:translateY(0)}35%{opacity:1;transform:translateY(-2px)}}
.nutritionist-character.motion-off .character-portrait,.motion-off .status-dots>view{animation:none}
@media(prefers-reduced-motion:reduce){.nutritionist-character.character-hero .character-portrait,.character-hero .status-dots>view{animation:none}.character-sprite{display:none;animation:none}.character-poster.poster-covered{opacity:1}}
</style>
