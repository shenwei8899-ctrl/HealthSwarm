<script setup>
defineProps({active:{type:Boolean,default:true}})
</script>
<template>
 <view class="ml-art" :class="{'ml-paused':!active}" aria-hidden="true">
  <view class="ml-shadow-plane"><view class="ml-shadow ml-animated"/></view>
  <view class="ml-enter ml-animated">
   <view class="ml-float ml-animated">
    <view class="ml-tilt">
     <view class="ml-plate"/><view class="ml-well"/>
     <view class="ml-food ml-greens"><view class="ml-food-enter ml-animated"><view class="ml-food-bob ml-animated"><view class="ml-leaf"/><view class="ml-leaf second"/></view></view></view>
     <view class="ml-food ml-egg"><view class="ml-food-enter ml-animated"><view class="ml-food-bob ml-animated"><view class="ml-egg-white"><view class="ml-yolk"/></view></view></view></view>
     <view class="ml-food ml-tomato"><view class="ml-food-enter ml-animated"><view class="ml-food-bob ml-animated"><view class="ml-tomato-shape"/></view></view></view>
    </view>
   </view>
  </view>
  <view class="ml-steam"><view class="ml-strand ml-animated"/><view class="ml-strand ml-animated"/><view class="ml-strand ml-animated"/></view>
  <text class="ml-spark first ml-animated">✦</text><text class="ml-spark second ml-animated">·</text>
 </view>
</template>
<style>
/* ml- is private to this illustration. Entry, tilt and float use separate transforms. */
.ml-art{position:relative;width:165px;height:117px;margin:0 auto 18px;pointer-events:none}
.ml-shadow-plane{position:absolute;left:9px;top:65px;width:146px;height:41px;transform:rotate(-12deg)}
.ml-shadow{width:100%;height:100%;border-radius:50%;background:rgba(144,165,220,.17);opacity:.7;animation:ml-shadow 3s ease-in-out infinite}
.ml-enter{position:absolute;left:24px;top:36px;width:119px;height:69px;opacity:1;animation:ml-arrive .55s cubic-bezier(.2,.75,.3,1) both}
.ml-float{width:100%;height:100%;animation:ml-float 3s ease-in-out infinite}
.ml-tilt{position:relative;width:100%;height:100%;transform:rotate(-12deg)}
.ml-plate{position:absolute;inset:0;border-radius:50%;border:1px solid #fff;background:#fff;box-shadow:inset 0 -6px 0 #e3e8f6}
.ml-well{position:absolute;left:14px;right:14px;top:11px;bottom:15px;border:1px solid #dce1f5;border-radius:50%;background:#f0f3fc}
.ml-food{position:absolute}.ml-greens{left:32px;top:17px;width:35px;height:28px}.ml-egg{left:64px;top:23px;width:33px;height:24px}.ml-tomato{left:58px;top:42px;width:15px;height:13px}
.ml-food-enter{width:100%;height:100%;opacity:1;animation:ml-ingredient .55s cubic-bezier(.2,.75,.3,1) .15s both}.ml-egg .ml-food-enter{animation-delay:.32s}.ml-tomato .ml-food-enter{animation-delay:.5s}
.ml-food-bob{position:relative;width:100%;height:100%;animation:ml-food 3s ease-in-out infinite}.ml-egg .ml-food-bob{animation-delay:-1s}.ml-tomato .ml-food-bob{animation-delay:-2s}
.ml-leaf{position:absolute;left:0;top:10px;width:24px;height:13px;border-radius:3px 14px 3px 14px;background:#98bdb0;transform:rotate(20deg)}.ml-leaf.second{left:9px;top:4px;background:#afcdb9;transform:rotate(-45deg)}
.ml-egg-white{position:relative;width:33px;height:24px;border-radius:50%;background:#fff;transform:rotate(-20deg)}.ml-yolk{position:absolute;left:9px;top:6px;width:15px;height:12px;border-radius:50%;background:#ecc98a}.ml-tomato-shape{width:15px;height:13px;border-radius:50%;background:#dfa099}
.ml-steam{position:absolute;left:65px;top:4px;display:flex;gap:9px}.ml-strand{width:5px;height:27px;border-left:2px solid #a2acd5;border-radius:50%;opacity:.45;animation:ml-steam 3s linear infinite}.ml-strand:nth-child(2){height:30px;animation-delay:-1s}.ml-strand:nth-child(3){animation-delay:-2s}
.ml-spark{position:absolute;color:#b0b4df;line-height:1;opacity:.6;animation:ml-spark 3s ease-in-out infinite}.ml-spark.first{left:1px;top:23px;font-size:19px}.ml-spark.second{right:0;top:64px;font-size:30px;animation-delay:-1.5s}
.ml-paused .ml-animated{animation-play-state:paused}
@keyframes ml-arrive{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:translateY(0)}}
@keyframes ml-ingredient{0%{opacity:0;transform:translateY(-22px) scale(.8)}70%{opacity:1;transform:translateY(2px) scale(1.04)}100%{opacity:1;transform:translateY(0) scale(1)}}
@keyframes ml-float{0%,100%{transform:translateY(2.5px) rotate(-2deg)}50%{transform:translateY(-2.5px) rotate(2deg)}}
@keyframes ml-shadow{0%,100%{opacity:.7;transform:scale(1)}50%{opacity:.4;transform:scale(.88)}}
@keyframes ml-food{0%,100%{transform:translateY(.8px)}50%{transform:translateY(-.8px)}}
@keyframes ml-steam{0%{opacity:0;transform:translateY(4px)}25%{opacity:.65}75%{opacity:.25}100%{opacity:0;transform:translateY(-12px)}}
@keyframes ml-spark{0%,100%{opacity:.3}50%{opacity:.9}}
@media(max-height:480px){.ml-art{margin-bottom:3px;transform:scale(.8);height:95px}}
@media(prefers-reduced-motion:reduce){.ml-art .ml-animated{animation:none}.ml-strand{opacity:.45}.ml-spark{opacity:.6}}
</style>
