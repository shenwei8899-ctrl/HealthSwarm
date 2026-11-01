<script setup>
import { computed } from 'vue'
const props=defineProps({ field: Object, modelValue: [String, Number], disabled: Boolean, archive: Boolean, readOnly:Boolean })
const displayValue=computed(()=>(props.modelValue==null||String(props.modelValue).trim()==='')?'未填写':props.field.type==='select'?(props.field.options.find(o=>o[0]===props.modelValue)?.[1]||String(props.modelValue)):String(props.modelValue))
defineEmits(['update:modelValue'])
</script>
<template><view class="archive-field" :class="{'archive-appearance':archive}"><text>{{field.label}}</text>
  <view v-if="readOnly" class="field-input field-value" :aria-label="field.label">{{displayValue}}</view>
  <picker v-else-if="field.type==='select'" :disabled="disabled" :range="['未填写',...field.options.map(o=>o[1])]" @change="$emit('update:modelValue',Number($event.detail.value)?field.options[Number($event.detail.value)-1][0]:'')"><view class="field-input">{{field.options.find(o=>o[0]===modelValue)?.[1]||'未填写'}} ▾</view></picker>
  <input v-else-if="['number','date'].includes(field.type)" :aria-label="field.label" :disabled="disabled" class="field-input" :type="field.type==='number'?'digit':'text'" :placeholder="field.type==='date'?'YYYY-MM-DD':'未填写'" :value="modelValue??''" @input="$emit('update:modelValue',$event.detail.value)"/>
  <textarea v-else :aria-label="field.label" :disabled="disabled" class="text-area" :maxlength="2000" auto-height placeholder="未填写" :value="modelValue??''" @input="$emit('update:modelValue',$event.detail.value)"/>
</view></template>
<style scoped>.archive-field{margin:22rpx 0}.archive-field>text{display:block;font-size:26rpx;margin-bottom:10rpx;color:#6e6e78}.text-area{min-height:88rpx;width:100%;box-sizing:border-box}
.field-value{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8}
.archive-appearance>text{font-size:14px;font-weight:600;color:#494658}.archive-appearance .field-input,.archive-appearance .text-area{box-sizing:border-box;width:100%;min-height:47px;padding:12px 14px;border:1px solid #eeedf5;border-radius:12px;background:#f7f7fc;color:#373447;font-size:16px;font-weight:500}.archive-appearance input.field-input{padding-top:0;padding-bottom:0}
</style>
