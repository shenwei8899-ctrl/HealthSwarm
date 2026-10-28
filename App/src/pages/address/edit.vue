<script setup>
import { ref, getCurrentInstance } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import CommerceAccess from '../../components/CommerceAccess.vue'
import AddressForm from '../../components/AddressForm.vue'
import { isMockMode } from '../../services/config.js'
import { openerChannel, addressBack } from '../../services/address-navigation.js'
const id = ref(''), mode = ref('manage'), routeReady = ref(false), instance = getCurrentInstance()
let channel
onLoad(options => { id.value = options.id || ''; mode.value = options.mode === 'select' ? 'select' : 'manage'; routeReady.value = true; channel = openerChannel(instance) })
function saved(result) { channel?.emit('addressSaved', result); addressBack(mode.value === 'select' ? 2 : 1) }
function removed(result) { channel?.emit('addressRemoved', result); addressBack() }
</script>
<template><CommerceAccess :enabled="!isMockMode"><AddressForm v-if="routeReady" :address-id="id" :mode="mode" @saved="saved" @removed="removed"/></CommerceAccess></template>
