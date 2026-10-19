<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import DailyPurchase from '../../components/DailyPurchase.vue'
import AdoptedPlanPurchase from '../../components/AdoptedPlanPurchase.vue'
const daily = ref(false)
onLoad(options => { daily.value = options.source === 'daily' })
</script>
<template><DailyPurchase v-if="daily"/><AdoptedPlanPurchase v-else/></template>
