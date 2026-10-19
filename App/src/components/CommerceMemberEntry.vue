<script setup>
import { ref } from 'vue'
import { onHide, onUnload } from '@dcloudio/uni-app'
import CommerceAccess from './CommerceAccess.vue'

defineProps({ disabled: Boolean })
const open = ref(false)
function close() { open.value = false }
function entered() {
  close()
  uni.navigateTo({ url: '/pages/shop/index?commerce=1' })
}
onHide(close)
onUnload(close)
</script>

<template>
  <view class="member-entry">
    <button class="secondary-button member-entry-button" :disabled="disabled" @click="open = true">商城账号登录</button>
    <view v-if="open" class="sheet-mask" @click="close">
      <view class="sheet member-login-sheet" @click.stop>
        <view class="sheet-head"><text class="section-title">商城账号登录</text><button aria-label="关闭商城登录" @click="close">×</button></view>
        <CommerceAccess entry member-entry @ready="entered" />
      </view>
    </view>
  </view>
</template>

<style scoped>
.member-entry{margin-top:20rpx}.member-entry-button{width:100%}.member-login-sheet{max-height:85vh}.member-login-sheet .section-title{font-size:32rpx}
</style>
