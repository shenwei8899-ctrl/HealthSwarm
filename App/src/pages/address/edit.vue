<script setup>
import { ref, getCurrentInstance } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import CommerceAccess from '../../components/CommerceAccess.vue'
import AddressForm from '../../components/AddressForm.vue'
import { isMockMode } from '../../services/config.js'
import { openerChannel, addressBack } from '../../services/address-navigation.js'
const id = ref(''), mode = ref('manage'), routeReady = ref(false), instance = getCurrentInstance()
const commerceReady = ref(false)
let channel
onLoad(options => { id.value = options.id || ''; mode.value = options.mode === 'select' ? 'select' : 'manage'; routeReady.value = true; channel = openerChannel(instance) })
function saved(result) { channel?.emit('addressSaved', result); addressBack(mode.value === 'select' ? 2 : 1) }
function removed(result) { channel?.emit('addressRemoved', result); addressBack() }
</script>
<template><CommerceAccess :enabled="!isMockMode" :page-title="id?'编辑收货地址':'新增收货地址'" loading-text="正在加载收货地址…" unavailable-text="收货地址暂时无法加载" @back="addressBack()" @ready="commerceReady=true" @unavailable="commerceReady=false"><AddressForm v-if="routeReady&&(isMockMode||commerceReady)" :address-id="id" :mode="mode" @saved="saved" @removed="removed"/></CommerceAccess></template>
