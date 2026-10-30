<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { parseAiAnswer } from '../utils/ai-answer.js'
import { replyMessageId, saveReplyFeedback } from '../services/chat-reply-feedback.js'
import { sessionRevision } from '../services/session.js'

const props=defineProps({text:{type:String,default:''},messageId:{type:[String,Number],default:null},canQuote:{type:Boolean,default:true}})
const emit=defineEmits(['quote'])
const busy=ref(false),rating=ref(''),error=ref('')
let version=0,disposed=false
watch(()=>props.messageId,()=>{version++;busy.value=false;rating.value='';error.value=''})
onUnmounted(()=>{disposed=true;version++})
const plainText=computed(()=>{
  const segments=items=>(items||[]).map(item=>item.text).join('')
  return parseAiAnswer(props.text).blocks.map(block=>block.segments?segments(block.segments):block.items?block.items.map(item=>segments(item.segments)).join('\n'):block.rows?[block.headers,...block.rows].map(row=>row.map(segments).join(' · ')).join('\n'):block.text||'').filter(Boolean).join('\n\n')
})
function copy(){if(!plainText.value)return;uni.setClipboardData({data:plainText.value,fail(){error.value='复制未完成，请重试'}})}
async function vote(value){
  if(busy.value||rating.value||!replyMessageId(props.messageId))return
  const mine=++version,revision=sessionRevision()
  const current=()=>!disposed&&mine===version&&revision===sessionRevision()
  busy.value=true;error.value=''
  try{const saved=await saveReplyFeedback(props.messageId,value,{isCurrent:current});if(current())rating.value=saved}
  catch(e){if(current())error.value=e.message||'评价未完成，请重试'}
  finally{if(current())busy.value=false}
}
</script>
<template>
 <view class="answer-tools">
  <view class="answer-tool-row" aria-label="回复操作">
   <view class="utility-actions">
    <button class="tool-button tool-with-label" aria-label="复制回复" :disabled="!plainText" @click="copy"><image class="tool-icon" src="/static/chat/reply-copy-v2.png" mode="aspectFit" aria-hidden="true"/><text class="tool-label">复制</text></button>
    <button class="tool-button tool-with-label" aria-label="引用回复" :disabled="!canQuote||!plainText" @click="emit('quote',plainText)"><image class="tool-icon" src="/static/chat/reply-quote-v2.png" mode="aspectFit" aria-hidden="true"/><text class="tool-label">引用</text></button>
   </view>
   <view class="feedback-actions">
    <button class="tool-button tool-feedback" aria-label="赞同回复" :aria-pressed="rating==='like'" :class="{selected:rating==='like'}" :disabled="busy||!!rating||!replyMessageId(messageId)" @click="vote('like')"><image class="tool-icon" src="/static/chat/reply-like-v2.png" mode="aspectFit" aria-hidden="true"/></button>
    <button class="tool-button tool-feedback" aria-label="不赞同回复" :aria-pressed="rating==='dislike'" :class="{selected:rating==='dislike'}" :disabled="busy||!!rating||!replyMessageId(messageId)" @click="vote('dislike')"><image class="tool-icon" src="/static/chat/reply-dislike-v2.png" mode="aspectFit" aria-hidden="true"/></button>
   </view>
  </view>
  <text v-if="error" class="tool-error" role="alert">{{error}}</text>
  <text v-else-if="rating" class="tool-confirmation">评价已保存</text>
 </view>
</template>
<style scoped>
.answer-tools{margin:10px 0 0}
.answer-tool-row{display:flex;align-items:center;gap:10px;min-height:44px}
.utility-actions,.feedback-actions{display:flex;align-items:center;gap:5px}
.feedback-actions{position:relative;gap:0;padding-left:8px}
.feedback-actions:before{content:'';position:absolute;left:0;top:15px;width:1px;height:14px;background:var(--ui-border,#e7e5ea)}
.tool-button{display:inline-flex;align-items:center;justify-content:center;flex:none;box-sizing:border-box;min-height:44px;height:44px;margin:0;padding:0;border:0;border-radius:12px;background:transparent;color:var(--ui-secondary,#6c6872);font-weight:400;line-height:1;transition:background-color .15s ease,transform .15s ease}
.tool-button:after{border:0}
.tool-with-label{gap:5px;min-width:68px;padding:0 10px;background:rgba(70,62,79,.045)}
.tool-feedback{width:44px;min-width:44px}
.tool-icon{display:block;flex:none;width:18px;height:18px}
.tool-label{font-size:12px;line-height:1;letter-spacing:.2px}
.tool-button[disabled] .tool-icon,.tool-button[disabled] .tool-label{opacity:.4}
.tool-button.selected{background:var(--ui-accent-soft,#eaf1ed)}
.tool-button.selected .tool-icon{opacity:1}
.tool-button:not([disabled]):active{background:rgba(70,62,79,.1);transform:scale(.96)}
.tool-button:focus-visible{outline:2px solid var(--ui-accent,#536b60);outline-offset:2px}
.tool-error,.tool-confirmation{display:block;margin:4px 0 0 3px;font-size:11px;line-height:1.5;color:#98696b}
.tool-confirmation{color:var(--ui-muted,#8d8993)}
@media(prefers-reduced-motion:reduce){.tool-button{transition:none}.tool-button:not([disabled]):active{transform:none}}
</style>
