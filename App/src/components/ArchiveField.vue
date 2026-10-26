<script setup>
defineProps({ field: Object, modelValue: [String, Number], disabled: Boolean })
defineEmits(['update:modelValue'])
</script>
<template><view class="archive-field"><text>{{field.label}}</text>
  <picker v-if="field.type==='select'" :disabled="disabled" :range="['未填写',...field.options.map(o=>o[1])]" @change="$emit('update:modelValue',Number($event.detail.value)?field.options[Number($event.detail.value)-1][0]:'')"><view class="field-input">{{field.options.find(o=>o[0]===modelValue)?.[1]||'未填写'}} ▾</view></picker>
  <input v-else-if="['number','date'].includes(field.type)" :aria-label="field.label" :disabled="disabled" class="field-input" :type="field.type==='number'?'digit':'text'" :placeholder="field.type==='date'?'YYYY-MM-DD':'未填写'" :value="modelValue??''" @input="$emit('update:modelValue',$event.detail.value)"/>
  <textarea v-else :aria-label="field.label" :disabled="disabled" class="text-area" :maxlength="2000" auto-height placeholder="未填写" :value="modelValue??''" @input="$emit('update:modelValue',$event.detail.value)"/>
</view></template>
<style scoped>.archive-field{margin:22rpx 0}.archive-field>text{display:block;font-size:26rpx;margin-bottom:10rpx;color:#6e6e78}.text-area{min-height:88rpx;width:100%;box-sizing:border-box}</style>
