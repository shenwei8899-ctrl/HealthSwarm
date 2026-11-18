<script setup>
import {computed,ref,watch,onMounted,onUnmounted} from 'vue'
import {onShow,onHide} from '@dcloudio/uni-app'
const props=defineProps({size:{type:Number,default:180},unit:{type:String,default:'px',validator:v=>['px','rpx'].includes(v)},variant:{type:String,default:'hero',validator:v=>['hero','avatar'].includes(v)},state:{type:String,default:'idle',validator:v=>['idle','thinking','planning','success'].includes(v)},decorative:Boolean,animated:{type:Boolean,default:true}})
const stateLabels={idle:'少年饮食小助手',thinking:'正在认真思考',planning:'正在为你搭配餐单',success:'餐单准备好啦'}
const visualState=computed(()=>Object.prototype.hasOwnProperty.call(stateLabels,props.state)?props.state:'idle')
const frameSize=computed(()=>Number.isFinite(props.size)&&props.size>0?props.size:180)
const frameUnit=computed(()=>props.unit==='rpx'?'rpx':'px')
const frameStyle=computed(()=>({width:frameSize.value+frameUnit.value,height:frameSize.value+frameUnit.value}))
const active=ref(true),visible=ref(true),reducedMotion=ref(false),posterFailed=ref(false),spriteFailed=ref(false)
const loadedLayers=ref([])
const layerNames=['head','blink','body','arm']
const showSprite=computed(()=>props.variant==='hero'&&props.animated&&active.value&&visible.value&&!reducedMotion.value&&!spriteFailed.value)
const spriteReady=computed(()=>layerNames.every(name=>loadedLayers.value.includes(name)))
const posterCovered=computed(()=>showSprite.value&&spriteReady.value)
// Reveal all decoded layers together; the PNG has the identical resting geometry.
watch(showSprite,()=>{loadedLayers.value=[]},{flush:'sync'})
function spriteLoaded(name){if(showSprite.value&&layerNames.includes(name)&&!loadedLayers.value.includes(name))loadedLayers.value=[...loadedLayers.value,name]}
function spriteError(){spriteFailed.value=true;loadedLayers.value=[]}
let motionQuery=null,visibilityTarget=null
function motionPreference(event){reducedMotion.value=event.matches===true}
function pageVisibility(){visible.value=visibilityTarget?.visibilityState!=='hidden'}
onMounted(()=>{
 if(typeof globalThis.matchMedia==='function'){
  motionQuery=globalThis.matchMedia('(prefers-reduced-motion: reduce)');motionPreference(motionQuery)
  motionQuery.addEventListener?.('change',motionPreference)
 }
 visibilityTarget=globalThis.document
 visibilityTarget?.addEventListener?.('visibilitychange',pageVisibility);pageVisibility()
})
onShow(()=>{active.value=true});onHide(()=>{active.value=false})
onUnmounted(()=>{active.value=false;motionQuery?.removeEventListener?.('change',motionPreference);visibilityTarget?.removeEventListener?.('visibilitychange',pageVisibility)})
</script>
<template>
 <view class="nutritionist-character" :class="['character-'+variant,'state-'+visualState,{'motion-off':!showSprite}]" :style="frameStyle" role="img" :aria-hidden="decorative?'true':undefined" :aria-label="decorative?undefined:stateLabels[visualState]">
  <view class="character-portrait" :style="frameStyle">
   <image v-if="!posterFailed" class="character-image character-poster" :class="{'poster-covered':posterCovered}" :style="frameStyle" src="/static/chat/nutrition-boy-v3-poster.png" mode="aspectFit" aria-hidden="true" @error="posterFailed=true"/>
   <view v-else-if="!posterCovered" class="character-fallback" :style="frameStyle" aria-hidden="true"><text>👦</text></view>
   <view v-if="showSprite" class="character-rig" :class="{'is-ready':spriteReady}" aria-hidden="true">
    <view class="character-breath">
     <view class="character-head">
      <image class="character-part character-eyes-open" src="/static/chat/nutrition-boy-v3-head.webp" mode="scaleToFill" @load="spriteLoaded('head')" @error="spriteError"/>
      <image class="character-part character-eyes-closed" src="/static/chat/nutrition-boy-v3-blink.webp" mode="scaleToFill" @load="spriteLoaded('blink')" @error="spriteError"/>
     </view>
     <image class="character-part character-body" src="/static/chat/nutrition-boy-v3-body.webp" mode="scaleToFill" @load="spriteLoaded('body')" @error="spriteError"/>
     <view class="character-arm"><image class="character-part" src="/static/chat/nutrition-boy-v3-arm.webp" mode="scaleToFill" @load="spriteLoaded('arm')" @error="spriteError"/></view>
    </view>
   </view>
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
.character-portrait{position:relative;overflow:hidden}.character-image{display:block}.character-poster{opacity:1}.character-poster.poster-covered{opacity:0}
.character-rig,.character-breath{position:absolute;left:0;top:0;width:100%;height:100%}.character-rig{opacity:0;pointer-events:none}.character-rig.is-ready{opacity:1}
.character-part{position:absolute;display:block;width:100%;height:100%;left:0;top:0}
/* Fractions of the same 320px artboard as the bundled PNG. */
.character-head{position:absolute;left:20.9375%;top:1.25%;width:53.75%;height:58.75%;transform-origin:63% 91%}
.character-body{left:31.875%;top:50.3125%;width:56.875%;height:47.5%}
.character-arm{position:absolute;left:15.9375%;top:43.75%;width:31.875%;height:32.8125%;transform-origin:88% 56%}
.character-eyes-closed{opacity:0}
.is-ready .character-breath{animation:boy-breathe 6.4s ease-in-out infinite}
.is-ready .character-head{animation:boy-attention 6.4s cubic-bezier(.37,0,.3,1) infinite}
.is-ready .character-arm{animation:boy-wave 12s cubic-bezier(.37,0,.3,1) infinite}
.is-ready .character-eyes-open{animation:boy-eyes-open 7.6s step-end infinite}.is-ready .character-eyes-closed{animation:boy-eyes-closed 7.6s step-end infinite}
.state-thinking .is-ready .character-arm,.state-planning .is-ready .character-arm,.state-success .is-ready .character-arm{animation:none}
.state-thinking .is-ready .character-head,.state-planning .is-ready .character-head{animation:boy-consider 5.8s ease-in-out infinite}
.state-success .is-ready .character-head{animation:boy-nod .9s cubic-bezier(.37,0,.3,1) 1}
.character-fallback{display:flex;align-items:center;justify-content:center;border-radius:50%;background:#eaf2eb;line-height:1}.character-fallback>text{font-size:32px}
.character-avatar .character-portrait{border-radius:50%;background:#edf1e9}.character-avatar .character-image{position:absolute;left:-34%;top:-8%;transform:scale(1.85);transform-origin:0 0}
.character-status{position:absolute;z-index:1;left:50%;bottom:0;display:flex;align-items:center;justify-content:center;gap:6px;min-height:26px;padding:3px 10px;border:1px solid rgba(255,255,255,.94);border-radius:18px;background:rgba(255,255,255,.94);box-shadow:0 3px 10px rgba(121,99,170,.1);color:#78658f;transform:translateX(-50%);white-space:nowrap;box-sizing:border-box}
.status-label{flex-shrink:0;white-space:nowrap;font-size:11px;line-height:1.5}.status-check{color:#5d9c83;font-size:14px;font-weight:600;line-height:1}.status-dots{display:flex;align-items:center;justify-content:center;gap:3px;height:12px}.status-dots>view{width:3px;height:3px;border-radius:50%;background:#ab8fd5}
.character-hero .status-dots>view{animation:character-dot 1.6s ease-in-out infinite}.character-hero .status-dots>view:nth-child(2){animation-delay:.2s}.character-hero .status-dots>view:nth-child(3){animation-delay:.4s}
.state-planning .status-dots>view{background:#79ad96}.state-success .character-status{color:#648a77;background:#f4fff8}
.character-avatar .character-status{left:auto;right:-6%;bottom:-12%;min-height:0;width:34%;height:34%;padding:0;border:1px solid #fff;transform:none;box-shadow:none}.character-avatar .status-check{font-size:8px}.character-avatar .status-dots{gap:1px;height:auto}.character-avatar .status-dots>view{width:2px;height:2px}.character-avatar.state-thinking .character-status{background:#e7dcf7}.character-avatar.state-planning .character-status{background:#def1e7}
@keyframes boy-breathe{0%,100%{transform:translateY(0)}50%{transform:translateY(-.7px)}}
@keyframes boy-attention{0%,100%{transform:rotate(0)}35%{transform:rotate(1.2deg)}72%{transform:rotate(-.8deg)}}
@keyframes boy-wave{0%,26%,100%{transform:rotate(0)}4%{transform:rotate(-8deg)}8%{transform:rotate(6deg)}12%{transform:rotate(-6deg)}16%{transform:rotate(4deg)}20%{transform:rotate(-1.5deg)}58%{transform:rotate(.8deg)}76%{transform:rotate(0)}}
@keyframes boy-consider{0%,100%{transform:rotate(0)}45%,60%{transform:rotate(2deg)}}
@keyframes boy-nod{0%,100%{transform:rotate(0) translateY(0)}40%{transform:rotate(2deg) translateY(1px)}70%{transform:rotate(-.6deg) translateY(-.3px)}}
@keyframes boy-eyes-open{0%,38%,80%,100%{opacity:1}36%,78%{opacity:0}}
@keyframes boy-eyes-closed{0%,38%,80%,100%{opacity:0}36%,78%{opacity:1}}
@keyframes character-dot{0%,70%,100%{opacity:.4;transform:translateY(0)}35%{opacity:1;transform:translateY(-1.5px)}}
.motion-off .status-dots>view{animation:none}
@media(prefers-reduced-motion:reduce){.character-rig{display:none}.character-poster.poster-covered{opacity:1}.character-hero .status-dots>view{animation:none}}
</style>
