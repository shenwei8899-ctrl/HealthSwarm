<script setup>
import { ref, getCurrentInstance } from 'vue'
import { onLoad, onUnload } from '@dcloudio/uni-app'
import CommerceAccess from '../../components/CommerceAccess.vue'
import CommerceAddresses from '../../components/CommerceAddresses.vue'
import { isMockMode } from '../../services/config.js'
import { storageContext } from '../../services/storage.js'
import { openerChannel, addressBack } from '../../services/address-navigation.js'
const mode = ref('manage'), selectedId = ref(''), instance = getCurrentInstance()
// Native mini-program slots can mount their children before slot visibility.
// Gate the address component itself until the commerce identity is restored.
const commerceReady = ref(false)
const owner = storageContext()
let alive = true, returning = false, channel
onLoad(options => { mode.value = options.mode === 'select' ? 'select' : 'manage'; selectedId.value = options.selectedId || ''; channel = openerChannel(instance) })
onUnload(() => { alive = false })
function finish(id, navigate = true) {
  if (returning || !alive || owner !== storageContext()) return
  returning = true
  channel?.emit('addressSelected', { id: String(id) })
  if (navigate) addressBack()
}
// The editor performs one two-page return; avoid two racing navigateBack calls.
function select(id, fromEditor = false) { finish(id, !fromEditor) }
</script>
<template><CommerceAccess :enabled="!isMockMode" :page-title="mode==='select'?'选择收货地址':'收货地址'" loading-text="正在加载收货地址…" unavailable-text="收货地址暂时无法加载" @back="addressBack()" @ready="commerceReady=true" @unavailable="commerceReady=false"><CommerceAddresses v-if="isMockMode||commerceReady" :mode="mode" :selected-id="selectedId" @select="select"/></CommerceAccess></template>
