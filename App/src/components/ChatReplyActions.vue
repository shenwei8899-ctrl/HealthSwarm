<script setup>
import { computed, ref, watch } from 'vue'
import { parseAiAnswer } from '../utils/ai-answer.js'

const props=defineProps({text:{type:String,default:''},messageId:{type:[String,Number],default:null},canQuote:{type:Boolean,default:true}})
const emit=defineEmits(['quote'])
const error=ref('')
watch(()=>props.messageId,()=>{error.value=''})
const plainText=computed(()=>{
  const segments=items=>(items||[]).map(item=>item.text).join('')
  return parseAiAnswer(props.text).blocks.map(block=>block.segments?segments(block.segments):block.items?block.items.map(item=>segments(item.segments)).join('\n'):block.rows?[block.headers,...block.rows].map(row=>row.map(segments).join(' · ')).join('\n'):block.text||'').filter(Boolean).join('\n\n')
})
function copy(){if(!plainText.value)return;uni.setClipboardData({data:plainText.value,fail(){error.value='复制未完成，请重试'}})}
</script>
<template>
 <view class="answer-tools">
  <view class="answer-tool-row" aria-label="回复操作">
   <view class="utility-actions">
    <button class="tool-button tool-with-label" aria-label="复制回复" :disabled="!plainText" @click="copy"><image class="tool-icon" src="/static/chat/reply-copy-v2.png" mode="aspectFit" aria-hidden="true"/><text class="tool-label">复制</text></button>
    <button class="tool-button tool-with-label" aria-label="引用回复" :disabled="!canQuote||!plainText" @click="emit('quote',plainText)"><image class="tool-icon" src="/static/chat/reply-quote-v2.png" mode="aspectFit" aria-hidden="true"/><text class="tool-label">引用</text></button>
   </view>
  </view>
  <text v-if="error" class="tool-error" role="alert">{{error}}</text>
 </view>
</template>
<style scoped>
.answer-tools{margin:10px 0 0}
.answer-tool-row{display:flex;align-items:center;gap:10px;min-height:44px}
.utility-actions{display:flex;align-items:center;gap:5px}
.tool-button{display:inline-flex;align-items:center;justify-content:center;flex:none;box-sizing:border-box;min-height:44px;height:44px;margin:0;padding:0;border:0;border-radius:12px;background:transparent;color:var(--ui-secondary,#6c6872);font-weight:400;line-height:1;transition:background-color .15s ease,transform .15s ease}
.tool-button:after{border:0}
.tool-with-label{gap:5px;min-width:68px;padding:0 10px;background:rgba(70,62,79,.045)}
.tool-icon{display:block;flex:none;width:18px;height:18px}
.tool-label{font-size:12px;line-height:1;letter-spacing:.2px}
.tool-button[disabled] .tool-icon,.tool-button[disabled] .tool-label{opacity:.4}
.tool-button:not([disabled]):active{background:rgba(70,62,79,.1);transform:scale(.96)}
.tool-button:focus-visible{outline:2px solid var(--ui-accent,#536b60);outline-offset:2px}
.tool-error{display:block;margin:4px 0 0 3px;font-size:11px;line-height:1.5;color:#98696b}
@media(prefers-reduced-motion:reduce){.tool-button{transition:none}.tool-button:not([disabled]):active{transform:none}}
</style>
