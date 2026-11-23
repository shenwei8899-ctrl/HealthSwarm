<script setup>
import {ref,onMounted,onUnmounted} from 'vue'
import {onShow,onHide} from '@dcloudio/uni-app'
import ServiceNoticeSheet from './ServiceNoticeSheet.vue'
import {installNoticePresenter} from '../services/service-notice.js'
const open=ref(false),document=ref(null),mode=ref('read'),status=ref(null)
let release=null,settle=null
function finish(accepted=false){open.value=false;const resolve=settle;settle=null;resolve?.(accepted)}
function show(options){finish();document.value=options.document;mode.value=options.mode;status.value=options.status;open.value=true;return new Promise(resolve=>{settle=resolve})}
function activate(){release?.();release=installNoticePresenter(show)}
function deactivate(){release?.();release=null;finish()}
onMounted(activate);onShow(activate);onHide(deactivate);onUnmounted(deactivate)
</script>
<template><ServiceNoticeSheet :open="open" :document="document" :mode="mode" :status="status" @confirm="finish(true)" @close="finish(false)"/></template>
