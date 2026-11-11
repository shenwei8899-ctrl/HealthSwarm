<script setup>
import { ref, computed, getCurrentInstance, nextTick, onMounted, onUpdated, onUnmounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { standardNavGeometry } from '../services/nav-layout.js'
const props = defineProps({ title: { type: String, default: undefined }, titleStyle: Object, belowCapsule: Boolean, capsuleAligned: Boolean, centered: Boolean })
const standard = computed(() => props.title !== undefined)
const layout = ref({ paddingTop: '0px', paddingRight: '0px' })
const geometry = ref(null)
const instance = getCurrentInstance()
let viewportWidth = 375, capsuleLeft, alive = true, scheduled = false
const geometryStyle = computed(() => geometry.value ? {
  '--nav-title-width': `${geometry.value.width}px`,
  '--nav-action-inset': `${geometry.value.rightInset}px`,
} : {})
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
  viewportWidth = Number(info.windowWidth) || 375
  capsuleLeft = Number.isFinite(capsule?.left) && capsule.left > 100 ? capsule.left : viewportWidth - 97
  layout.value = props.capsuleAligned ? alignedLayout(info, capsule) : {
    paddingTop: `${props.belowCapsule ? capsule.bottom + 8 : (info.statusBarHeight || 24)}px`,
    paddingRight: `${standard.value || props.belowCapsule || props.centered ? 0 : Math.max(0, info.windowWidth - capsule.left - 16)}px`,
  }
} catch {
  viewportWidth = Number(info.windowWidth) || 375
  capsuleLeft = viewportWidth - 97
  layout.value = props.capsuleAligned ? alignedLayout(info, null) : { paddingTop: props.belowCapsule ? '72px' : '28px', paddingRight: standard.value || props.belowCapsule || props.centered ? '0px' : '90px' }
}
// #endif
function measure() {
  if (!standard.value || scheduled || !alive) return
  scheduled = true
  nextTick(() => {
    if (!alive) return
    const query = uni.createSelectorQuery().in(instance.proxy)
    query.select('.app-nav-standard').boundingClientRect()
    query.select('.app-nav-left').boundingClientRect()
    query.select('.app-nav-right').boundingClientRect()
    query.exec(([row, left, right]) => {
      scheduled = false
      if (!alive || !row?.width) return
      // #ifdef H5
      viewportWidth = window.innerWidth
      // #endif
      // Standard pages use symmetric insets. Ignore transient horizontal offsets
      // from page-entry animations when measuring the permanent title position.
      const stableRow = { ...row, left: (viewportWidth - row.width) / 2, right: (viewportWidth + row.width) / 2 }
      const next = standardNavGeometry({ viewportWidth, row: stableRow, leftWidth: left?.width || 0, rightWidth: right?.width || 0,
        capsuleLeft: props.belowCapsule ? undefined : capsuleLeft, title: props.title, fontSize: Math.min(viewportWidth, 480) * 34 / 750 })
      if (JSON.stringify(next) !== JSON.stringify(geometry.value)) geometry.value = next
    })
  })
}
function resize(event) {
  viewportWidth = Number(event?.size?.windowWidth) || viewportWidth
  // #ifdef MP-WEIXIN
  try { capsuleLeft = uni.getMenuButtonBoundingClientRect().left } catch { capsuleLeft = viewportWidth - 97 }
  // #endif
  measure()
}
onMounted(() => { measure(); uni.onWindowResize?.(resize) })
onShow(() => { nextTick(measure) })
onUpdated(measure)
onUnmounted(() => { alive = false; uni.offWindowResize?.(resize) })
</script>
<template>
  <view class="app-nav" :style="layout">
    <view v-if="standard" class="app-nav-standard" :class="{'app-nav-actions-below': geometry?.actionsBelow}" :style="geometryStyle">
      <view class="app-nav-left"><slot name="left" /></view>
      <text class="app-nav-title" :style="titleStyle">{{title}}</text>
      <view class="app-nav-right"><slot name="right" /></view>
    </view>
    <slot v-else />
  </view>
</template>
<style scoped>
.app-nav{flex-shrink:0;min-width:0;padding-bottom:12rpx}
.app-nav-standard{position:relative;min-width:0;height:44px;box-sizing:content-box}
.app-nav-left,.app-nav-right{position:absolute;top:0;min-height:44px;display:flex;align-items:center;gap:8px;max-width:100%;z-index:1}
.app-nav-left{left:0}.app-nav-right{right:var(--nav-action-inset,0px)}
.app-nav-title{position:absolute;top:22px;left:50%;transform:translate(-50%,-50%);width:var(--nav-title-width,calc(100% - 104px));min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:center;font-size:34rpx;font-weight:500;line-height:1.4;pointer-events:none}
.app-nav-actions-below{padding-bottom:44px}.app-nav-actions-below .app-nav-right{top:44px;right:0}
/* #ifdef MP-WEIXIN */
.app-nav-title{width:var(--nav-title-width,calc(100% - 208px))}
/* #endif */
/* Custom home, history and onboarding headers retain their own layout. */
:deep(.nav-row){position:relative;min-height:88rpx;gap:12rpx}
:deep(.nav-title){position:absolute;left:50%;transform:translateX(-50%);max-width:55%;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:30rpx;font-weight:500}
:deep(.pill){display:none}
</style>
