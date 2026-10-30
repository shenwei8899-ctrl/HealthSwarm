<script setup>
import {ref,watch,onUnmounted} from 'vue'
const props=defineProps({open:Boolean,standalone:Boolean})
const emit=defineEmits(['close','closed'])
const rendered=ref(false),leaving=ref(false)
let timer
watch(()=>props.open,value=>{clearTimeout(timer);if(value){rendered.value=true;leaving.value=false}else if(rendered.value){leaving.value=true;timer=setTimeout(()=>{rendered.value=false;emit('closed')},260)}},{immediate:true})
function nativeClosed(){clearTimeout(timer);rendered.value=false;emit('closed')}
onUnmounted(()=>clearTimeout(timer))
</script>
<template>
 <view v-if="standalone" class="standalone-detail"><slot/></view>
 <!-- #ifdef MP-WEIXIN -->
 <page-container v-if="!standalone&&rendered" :show="open" position="bottom" :duration="240" :z-index="120" :overlay="true" :close-on-slide-down="false" custom-style="background:transparent" overlay-style="background:rgba(15,20,25,.35)" @clickoverlay="$emit('close')" @beforeleave="$emit('close',true)" @afterleave="nativeClosed"><slot/></page-container>
 <!-- #endif -->
 <!-- #ifndef MP-WEIXIN -->
 <view v-if="!standalone&&rendered" class="detail-overlay" :class="{'is-leaving':leaving}" @click.self="$emit('close')"><view class="detail-overlay-content"><slot/></view></view>
 <!-- #endif -->
</template>
<style scoped>
.detail-overlay{position:fixed;z-index:120;inset:0;background:var(--ui-overlay);display:flex;align-items:flex-end;justify-content:center;animation:detail-mask-in 240ms ease both}.detail-overlay-content{width:100%;max-width:480px;animation:detail-panel-in 240ms cubic-bezier(.2,.7,.2,1) both}.is-leaving{animation:detail-mask-out 240ms ease both}.is-leaving .detail-overlay-content{animation:detail-panel-out 240ms ease both}@keyframes detail-mask-in{from{background:transparent}}@keyframes detail-mask-out{to{background:transparent}}@keyframes detail-panel-in{from{transform:translateY(100%)}}@keyframes detail-panel-out{to{transform:translateY(100%)}}@media(prefers-reduced-motion:reduce){.detail-overlay,.detail-overlay-content{animation-duration:1ms}}
</style>
