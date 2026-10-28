<script setup>
import AppIcon from './AppIcon.vue'
defineProps({prompts:{type:Array,default:()=>[]},disabled:Boolean,compact:Boolean})
defineEmits(['ask','shuffle','today'])
</script>
<template>
 <view class="chat-welcome" :class="{'is-compact':compact}">
  <view class="welcome-intro">
   <view class="welcome-title"><text>每一餐 </text><text class="welcome-accent">都更适合你</text></view>
   <text class="welcome-description">{{'聊聊想吃的、忌口的和家人的需要，\n一起把今天的三餐安排好。'}}</text>
  </view>
  <view class="welcome-hero" aria-hidden="true">
   <view class="hero-halo"/>
   <view class="hero-orbit hero-orbit-family"><AppIcon name="family" :size="37"/><text>家人的需要</text></view>
   <view class="hero-orbit hero-orbit-meals"><AppIcon name="calendar" :size="37"/><text>一日三餐</text></view>
   <view class="hero-assistant"><view class="hero-leaf hero-leaf-left"/><view class="hero-leaf hero-leaf-right"/><view class="hero-face"><view/><view/></view><view class="hero-smile"/></view>
   <view class="hero-caption"><view/><text>家庭营养师</text></view>
  </view>
  <view class="welcome-hint-card">
   <view class="hint-heading"><view><text class="hint-title">从一个问题，开始好好吃饭</text><text class="hint-description">偏好、忌口、就餐人数，都可以慢慢补充。</text></view><button class="welcome-today" :disabled="disabled" @click="$emit('today')"><text>今日安排</text><text aria-hidden="true">→</text></button></view>
   <scroll-view class="welcome-prompt-scroll" scroll-x :show-scrollbar="false"><view class="welcome-prompts"><button v-for="(prompt,index) in prompts" :key="index" :disabled="disabled" @click="$emit('ask',prompt)"><text>{{prompt.text}}</text><text aria-hidden="true">↗</text></button></view></scroll-view><button class="shuffle-prompts" :disabled="disabled" @click="$emit('shuffle')">换一换</button>
  </view>
 </view>
</template>
<style scoped>
.chat-welcome{box-sizing:border-box;display:flex;flex-direction:column;gap:12px;padding:28px 0 12px;color:#2b2c3c}
.welcome-intro{display:flex;flex-direction:column;align-items:center;text-align:center}.welcome-title{display:block;font-size:24px;font-weight:500;line-height:1.5;letter-spacing:.1px}.welcome-accent{color:#6650df}.welcome-description{display:block;margin-top:9px;white-space:pre-line;font-size:13px;line-height:1.8;color:#878799}
.welcome-hero{position:relative;display:flex;align-items:center;justify-content:center;height:180px;flex-shrink:0;margin:1px 0 0}.hero-halo{position:absolute;width:234px;height:166px;border-radius:50%;background:radial-gradient(ellipse,rgba(255,255,255,.85),rgba(198,190,255,.2) 58%,transparent 73%)}.hero-assistant{position:relative;width:104px;height:102px;border-radius:34px 34px 37px 37px;background:linear-gradient(145deg,#bfb0ff 0%,#8970f4 50%,#6849e2 100%);box-shadow:inset 5px 5px 7px rgba(255,255,255,.5),inset -4px -5px 8px rgba(74,43,163,.16),0 13px 23px rgba(111,81,199,.18);transform:rotate(-5deg)}.hero-leaf{position:absolute;top:-20px;width:28px;height:35px;border-radius:5px 28px 7px 28px;background:linear-gradient(135deg,#d9e8ba,#81bead);box-shadow:inset 2px 2px 3px rgba(255,255,255,.6)}.hero-leaf-left{left:32px;transform:rotate(-28deg)}.hero-leaf-right{left:53px;top:-16px;transform:rotate(55deg);width:21px;height:31px}.hero-face{position:absolute;left:24px;right:24px;top:32px;height:20px;display:flex;align-items:center;justify-content:space-between}.hero-face>view{width:9px;height:17px;border-radius:9px;background:#fff;box-shadow:0 1px 2px rgba(67,43,145,.12)}.hero-smile{position:absolute;left:41px;top:59px;width:23px;height:12px;border-bottom:3px solid rgba(255,255,255,.95);border-radius:0 0 20px 20px}
.hero-orbit{position:absolute;display:flex;align-items:center;gap:5px;min-height:36px;padding:6px 10px;border:1px solid rgba(255,255,255,.9);border-radius:11px;background:linear-gradient(130deg,rgba(255,255,255,.86),rgba(255,255,255,.38));color:#716d8f;font-size:11px;line-height:1.4;box-shadow:0 4px 12px rgba(155,148,203,.07)}.hero-orbit-family{left:0;top:38px;transform:rotate(-13deg);color:#8c72ba}.hero-orbit-meals{right:0;top:70px;transform:rotate(10deg);color:#679d97}.hero-caption{position:absolute;left:50%;bottom:1px;transform:translateX(-50%);display:flex;align-items:center;gap:6px;min-height:27px;padding:3px 12px;border:1px solid rgba(255,255,255,.9);border-radius:9px;background:rgba(255,255,255,.72);color:#7f76a1;font-size:11px;line-height:1.5;white-space:nowrap}.hero-caption>view{width:5px;height:5px;border-radius:50%;background:#9a7ce8}
.welcome-hint-card{padding:13px 12px 9px;border:1px solid rgba(255,255,255,.95);border-radius:13px;background:linear-gradient(145deg,rgba(255,255,255,.7),rgba(255,255,255,.9));box-shadow:0 3px 12px rgba(153,150,198,.03)}.hint-heading{display:flex;align-items:center;gap:7px}.hint-heading>view{flex:1;min-width:0}.hint-title,.hint-description{display:block}.hint-title{color:#4e475f;font-size:13px;font-weight:500;line-height:1.6}.hint-description{margin-top:3px;color:#918b9c;font-size:11px;line-height:1.6}.welcome-today{display:flex;flex-shrink:0;align-items:center;justify-content:center;gap:4px;width:auto;min-height:40px;margin:0;padding:6px 9px;border:0;border-radius:7px;background:linear-gradient(130deg,#9871f1,#6238f2);color:#fff;font-size:11px;line-height:1.4}.welcome-today:after{border:0}.welcome-today[disabled]{opacity:.45;color:#fff}
.welcome-prompt-scroll{width:100%;margin-top:10px;white-space:nowrap}.welcome-prompts{display:inline-flex;gap:7px;padding-right:2px}.welcome-prompts button{display:inline-flex;align-items:center;gap:8px;flex-shrink:0;width:auto;min-height:36px;padding:5px 9px;border:1px solid #eeeafa;border-radius:7px;background:rgba(255,255,255,.76);color:#756d89;font-size:11px;line-height:1.5;text-align:left;white-space:nowrap}.welcome-prompts button:after{border:0}.welcome-prompts button>text+text{color:#9887c8}.welcome-prompts button[disabled]{opacity:.45}
@media(max-height:720px){.chat-welcome{padding-top:15px;gap:9px}.welcome-title{font-size:22px}.welcome-description{font-size:12px;margin-top:6px}.welcome-hero{height:148px}.hero-assistant{transform:scale(.9) rotate(-5deg)}.hero-orbit-family{top:25px}.hero-orbit-meals{top:55px}.welcome-hint-card{padding-top:10px}.hint-description{font-size:10px}}
@media(max-width:350px){.welcome-title{font-size:21px}.welcome-description{font-size:12px}.hero-orbit{padding:6px;font-size:10px}.hero-orbit-family{left:-2px}.hero-orbit-meals{right:-2px}.hint-title{font-size:12px}.hint-description{font-size:10px}.welcome-today{font-size:10px;padding-left:7px;padding-right:7px}}
.shuffle-prompts{min-height:40px;margin:4px 0 0 auto;padding:4px 8px;background:transparent;color:#8b7da5;font-size:12px}.shuffle-prompts:after{border:0}.is-compact .welcome-hero{display:none}.chat-welcome.is-compact{padding-top:14px}
</style>
