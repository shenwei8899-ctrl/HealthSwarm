<script setup>
defineProps({position:Object,dragging:Boolean})
const emit=defineEmits(['close','quote','drag','dragEnd'])
const at=event=>{const p=event.touches?.[0]||event;return{x:p.clientX??p.pageX,y:p.clientY??p.pageY}}
</script>
<template>
 <view v-if="position" class="selection-overlay">

  <view v-if="position.first" class="selection-handle start" :style="{left:(position.first.left-18)+'px',top:(position.first.top-22)+'px'}" @touchstart.stop.prevent="emit('drag',{edge:'start',point:at($event)})" @touchmove.stop.prevent="emit('drag',{edge:'start',point:at($event)})" @touchend.stop="emit('dragEnd')" @touchcancel.stop="emit('dragEnd')"><view/></view>
  <view v-if="position.last" class="selection-handle end" :style="{left:(position.last.right-18)+'px',top:(position.last.bottom-18)+'px'}" @touchstart.stop.prevent="emit('drag',{edge:'end',point:at($event)})" @touchmove.stop.prevent="emit('drag',{edge:'end',point:at($event)})" @touchend.stop="emit('dragEnd')" @touchcancel.stop="emit('dragEnd')"><view/></view>
  <view v-if="!dragging && !position.scrolling" class="selection-tools" :style="{left:position.left+'px',top:position.top+'px'}" @click.stop><button aria-label="引用选中文字" @click.stop="emit('quote')"><text>❝</text>引用选中文字</button><button class="selection-cancel" aria-label="取消文字选取" @click.stop="emit('close')">×</button></view>
 </view>
</template>
<style scoped>
.selection-tools{position:fixed;z-index:83;display:flex;align-items:center;min-height:44px;border:1px solid #eee9f4;background:#fff;border-radius:13px;box-shadow:0 4px 18px rgba(67,53,83,.13);color:#554a68}.selection-tools button{margin:0;min-height:44px;padding:0 12px;background:transparent;font-size:13px;color:inherit;display:flex;align-items:center;gap:7px}.selection-tools button:after{border:0}.selection-tools .selection-cancel{font-size:22px;color:#9a8da9;border-left:1px solid #eee9f4;padding:0 10px}.selection-handle{position:fixed;z-index:82;width:36px;height:44px;display:flex;justify-content:center;align-items:center;touch-action:none}.selection-handle>view{width:11px;height:11px;border-radius:50%;background:#9a73c5}.selection-handle.start>view:after,.selection-handle.end>view:after{content:'';display:block;width:2px;height:15px;background:#9a73c5;margin:8px 0 0 5px}.selection-handle.end>view:after{margin:-12px 0 0 5px}
</style>
