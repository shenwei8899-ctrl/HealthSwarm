<script setup>
defineProps({
  current: {
    type: Number,
    default: 1,
  },
})

const steps = ['输入资料', '模型分析', '菜单推荐', '下单配送', '制作烹饪', '吃完拍照']
</script>

<template>
  <scroll-view class="flow-ribbon" scroll-x :show-scrollbar="false" :scroll-into-view="'flow-step-' + current">
    <view class="flow-ribbon-steps">
    <template v-for="(step, index) in steps" :key="step">
      <text :id="'flow-step-' + (index + 1)" :class="index + 1 < current ? 'done' : index + 1 === current ? 'current' : ''">
        {{ index + 1 < current ? '✓ ' : '' }}{{ step }}
      </text>
      <text v-if="index < steps.length - 1">→</text>
    </template>
    </view>
  </scroll-view>
</template>

