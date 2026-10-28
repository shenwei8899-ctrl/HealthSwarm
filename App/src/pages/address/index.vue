<script setup>
import { ref, getCurrentInstance } from 'vue'
import { onLoad, onUnload } from '@dcloudio/uni-app'
import CommerceAccess from '../../components/CommerceAccess.vue'
import CommerceAddresses from '../../components/CommerceAddresses.vue'
import { isMockMode } from '../../services/config.js'
import { storageContext } from '../../services/storage.js'
import { openerChannel, addressBack } from '../../services/address-navigation.js'
const mode = ref('manage'), selectedId = ref(''), instance = getCurrentInstance()
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
<template><CommerceAccess :enabled="!isMockMode"><CommerceAddresses :mode="mode" :selected-id="selectedId" @select="select"/></CommerceAccess></template>
