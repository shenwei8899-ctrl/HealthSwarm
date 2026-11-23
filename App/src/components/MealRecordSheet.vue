<script setup>
// Keep the scroll editor adjacent to the sheet flex container in WeChat.
defineOptions({options:{virtualHost:true}})
import { ref, computed, watch, onUnmounted } from 'vue'
import CloudMealCapture from './CloudMealCapture.vue'
const props = defineProps({ entry: { type: Object, required: true }, availableHeight: Number })
const emit = defineEmits(['close'])
const capture = ref(null)
const isBusy = computed(() => !!capture.value?.isBusy)
const panelHeight = ref(80), dragging = ref(false), dragArea = ref(null)
let gesture = null, suppressMaskUntil = 0
const clampHeight = value => Math.max(42, Math.min(94, value))
// Only the header changes height. The editor's scroll-view owns body gestures.
function startDrag(event) {
 // #ifdef H5
 if (event.target?.closest?.('[aria-label="关闭记一餐"]')) return
 // #endif
 if ((event.touches && event.touches.length !== 1) || (event.button != null && event.button !== 0)) return
 const point = event.touches?.[0] || event
 const y = point.clientY ?? point.pageY
 const height = props.availableHeight || uni.getWindowInfo().windowHeight
 if (!Number.isFinite(y) || !(height > 0)) return
 gesture = {y, height, initial:panelHeight.value, id:point.identifier, moved:false}
 dragging.value = true
 // #ifdef H5
 if (!event.touches) {
  event.preventDefault()
  document.addEventListener('mousemove', moveDrag)
  document.addEventListener('mouseup', stopDrag)
 }
 // #endif
}
function moveDrag(event) {
 if (!gesture) return
 if (event.touches && event.touches.length !== 1) { stopDrag(); return }
 const point = event.touches?.[0] || event
 if (gesture.id != null && point.identifier !== gesture.id) return
 const delta = gesture.y - (point.clientY ?? point.pageY)
 if (!Number.isFinite(delta) || (!gesture.moved && Math.abs(delta) < 4)) return
 gesture.moved = true
 panelHeight.value = clampHeight(gesture.initial + delta / gesture.height * 100)
}
function stopDrag() {
 if (gesture?.moved) suppressMaskUntil = Date.now() + 350
 gesture = null
 dragging.value = false
 // #ifdef H5
 document.removeEventListener('mousemove', moveDrag)
 document.removeEventListener('mouseup', stopDrag)
 // #endif
}
function close() {
 if (isBusy.value || dragging.value) return
 if (!capture.value?.handleBack()) emit('close')
}
function closeMask() {
 // A touch released after resizing must not become a backdrop dismissal.
 if (Date.now() >= suppressMaskUntil) close()
}
watch(() => props.availableHeight, stopDrag)
// #ifdef H5
let mouseArea = null
watch(dragArea, value => {
 mouseArea?.removeEventListener('mousedown', startDrag)
 mouseArea = value?.$el || value
 mouseArea?.addEventListener('mousedown', startDrag)
}, {flush:'post'})
// #endif
onUnmounted(() => {
 stopDrag()
 // #ifdef H5
 mouseArea?.removeEventListener('mousedown', startDrag)
 // #endif
})
defineExpose({ isBusy, handleBack: close })
</script>
<template>
 <view class="record-mask" @click="closeMask" @touchmove.stop>
  <view class="record-panel" :class="{'is-dragging':dragging}" :style="{height:panelHeight+'%'}" @click.stop role="dialog" aria-modal="true" aria-label="记一餐">
   <view ref="dragArea" class="record-drag-area" @touchstart.stop="startDrag" @touchmove.stop.prevent="moveDrag" @touchend.stop="stopDrag" @touchcancel.stop="stopDrag">
   <view class="record-grip"/>
   <view class="record-heading"><view><text>记一餐</text><text class="record-caption">确认这次实际吃过的内容</text></view><button aria-label="关闭记一餐" :disabled="isBusy" @touchstart.stop @mousedown.stop @click.stop="close">×</button></view>
   </view>
   <CloudMealCapture ref="capture" embedded :entry="entry"/>
  </view>
 </view>
</template>
<style scoped>
.record-mask{position:absolute;inset:0;z-index:40;display:flex;align-items:flex-end;background:rgba(57,65,99,.19)}
.record-panel{display:flex;flex-direction:column;width:100%;min-height:0;overflow:hidden;box-sizing:border-box;border:1px solid rgba(255,255,255,.95);border-bottom:0;border-radius:28px 28px 0 0;background:linear-gradient(135deg,#e3edff,#eee6fb 48%,#f4f5fc 85%);box-shadow:0 -8px 36px rgba(100,113,162,.12)}
.record-drag-area{display:flex;flex-direction:column;flex:none;touch-action:none;user-select:none;cursor:ns-resize}.is-dragging{transition:none}.record-grip{flex:none;width:34px;height:4px;margin:10px auto 0;border-radius:4px;background:#bfb2df}
.record-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 18px 14px;flex:none;color:#42516c}
.record-heading>view>text:first-child{display:block;font-size:23px;font-weight:600;line-height:1.5}.record-caption{display:block;font-size:12px;color:#7b7492;margin-top:4px}
.record-heading button{margin:0 -8px 0 0;padding:0;width:44px;min-height:44px;background:transparent;color:#7b8fb5;font-size:28px;border:0}.record-heading button:after{border:0}
</style>
