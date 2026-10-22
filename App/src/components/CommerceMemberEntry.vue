<script setup>
// 旧引用保留为统一入口提示，不再提供商城凭据表单。
defineProps({ disabled: Boolean })
</script>
<template><view class="card"><text>请先微信登录并完成本人建档，再从 AI 首页选择餐单或食材包。</text><button :disabled="disabled" @click="uni.reLaunch({url:'/pages/index/index'})">返回微信登录</button></view></template>
