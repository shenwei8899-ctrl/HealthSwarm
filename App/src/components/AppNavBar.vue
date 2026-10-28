<script setup>
import { ref } from 'vue'
const props = defineProps({ belowCapsule: Boolean, capsuleAligned: Boolean })
const layout = ref({ paddingTop: '0px', paddingRight: '0px' })
// #ifdef MP-WEIXIN
function alignedLayout(info, capsule) {
  const width = Number(info.windowWidth) || 375;
  const status = Number(info.statusBarHeight) || 28;
  const valid = capsule && Number.isFinite(capsule.top) && Number.isFinite(capsule.left)
    && capsule.left > 100 && Number.isFinite(capsule.height) && capsule.height > 0;
  const rect = valid ? capsule : {top: status + 4, height: 32, left: width - 97};
  const inset = width <= 350 ? 16 : 20;
  const gap = 4;
  const profileLeft = rect.left - gap - 44;
  const fontSize = width < 360 ? 16 : 18;
  const titleWidth = fontSize * 5 + 2;
  const historyRight = inset - 10 + 44;
  const titleCenter = Math.max(historyRight + 6 + titleWidth / 2,
    Math.min(width / 2, profileLeft - 6 - titleWidth / 2));
  return {
    paddingTop: Math.max(0, rect.top + rect.height / 2 - 22) + "px",
    paddingRight: "0px",
    "--chat-profile-right": (width - inset - rect.left + gap) + "px",
    "--chat-title-left": (titleCenter - inset) + "px",
    "--chat-title-font": fontSize + "px"
  };
}
let info = {}
try {
  info = uni.getWindowInfo ? uni.getWindowInfo() : uni.getSystemInfoSync()
  const capsule = uni.getMenuButtonBoundingClientRect()
  layout.value = props.capsuleAligned ? alignedLayout(info, capsule) : {
    paddingTop: `${props.belowCapsule ? capsule.bottom + 8 : (info.statusBarHeight || 24)}px`,
    paddingRight: `${props.belowCapsule ? 0 : Math.max(0, info.windowWidth - capsule.left - 16)}px`,
  }
} catch { layout.value = props.capsuleAligned ? alignedLayout(info, null) : { paddingTop: props.belowCapsule ? '72px' : '28px', paddingRight: props.belowCapsule ? '0px' : '90px' } }
// #endif
</script>
<template><view class="app-nav" :style="layout"><slot /></view></template>
<style scoped>.app-nav{flex-shrink:0;min-width:0;padding-bottom:12rpx}:deep(.nav-row){position:relative;min-height:88rpx;gap:12rpx}:deep(.nav-title){position:absolute;left:50%;transform:translateX(-50%);max-width:55%;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:30rpx;font-weight:500}:deep(.pill){display:none}</style>
