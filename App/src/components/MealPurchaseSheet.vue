<script setup>
import { ref, watch } from 'vue'
import { detailGesture } from '../services/meal-detail-client.js'
const props = defineProps({ open: Boolean, busy: Boolean, page: Boolean, title: { type: String, default: '购买本餐食材' } })
const emit = defineEmits(['close'])
const expanded = ref(false), scrollTop = ref(0)
let touch = null
watch(() => props.open, value => { if (value) expanded.value = false })
function close() { if (!props.busy) emit('close') }
function start(event) {
  const point = event.touches?.[0]
  if (point) touch = { x: point.clientX, y: point.clientY, top: scrollTop.value }
}
function end(event) {
  const point = event.changedTouches?.[0], origin = touch
  touch = null
  if (!point || !origin || props.busy || Math.abs(point.clientX-origin.x) > Math.abs(point.clientY-origin.y)) return
  const action = detailGesture({ delta: point.clientY-origin.y, expanded: expanded.value, scrollTop: origin.top })
  if (action === 'expand') expanded.value = true
  else if (action === 'collapse') expanded.value = false
  else if (action === 'close') close()
}
defineExpose({ setScrollTop: value => { scrollTop.value = value } })
</script>
<template>
  <view class="mp-sheet-mask" :class="{'is-page':page}" :style="{display:open?'flex':'none'}" @click.self="close">
    <view class="mp-sheet-panel" :class="{'is-expanded':expanded}" role="dialog" aria-modal="true" :aria-label="title" @click.stop @touchstart="start" @touchend="end">
      <button class="mp-sheet-grip" :aria-label="expanded?'收起采购页':'展开采购页'" :aria-expanded="expanded" :disabled="busy" @click="expanded=!expanded"><view/></button>
      <view class="mp-sheet-heading"><text>{{title}}</text><button aria-label="关闭采购页" :disabled="busy" @click="close">×</button></view>
      <view class="mp-sheet-content"><slot/></view>
    </view>
  </view>
</template>
<style scoped>
.mp-sheet-mask{position:absolute;inset:0;z-index:20;display:flex;align-items:flex-end;background:var(--ui-overlay);overflow:hidden;border-radius:inherit}
.mp-sheet-mask.is-page{position:fixed;border-radius:0}.is-page .mp-sheet-panel{max-width:480px;margin:0 auto}
.mp-sheet-panel{display:flex;flex-direction:column;width:100%;height:56vh;height:56dvh;max-height:100%;min-height:0;border-radius:30px 30px 0 0;border:1px solid var(--ui-bubble-line);border-bottom:0;background:var(--meal-surface,var(--ui-canvas-gradient));color:var(--ui-text);box-shadow:0 -8px 32px rgba(48,55,75,.09);overflow:hidden;transition:height 240ms cubic-bezier(.2,.7,.2,1)}
.mp-sheet-panel.is-expanded{height:86vh;height:86dvh}.mp-sheet-grip{display:flex;align-items:center;justify-content:center;width:100%;height:24px;min-height:24px;background:transparent;margin:0;padding:0}.mp-sheet-grip>view{width:32px;height:4px;border-radius:4px;background:#b9bfce}
.mp-sheet-heading{display:flex;align-items:center;justify-content:space-between;padding:0 18px 10px 22px;flex-shrink:0}.mp-sheet-heading>text{font-size:19px;font-weight:600;line-height:1.5}.mp-sheet-heading>button{display:flex;align-items:center;justify-content:center;width:44px;height:44px;margin:0;padding:0;border-radius:50%;background:rgba(255,255,255,.65);font-size:27px;color:var(--ui-muted)}
.mp-sheet-content{display:flex;flex-direction:column;flex:1;height:0;min-height:0}.mp-sheet-panel button:after{border:0}@media(prefers-reduced-motion:reduce){.mp-sheet-panel{transition:none}}
</style>
