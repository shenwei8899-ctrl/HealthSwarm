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
   <button aria-label="复制回复" :disabled="!plainText" @click="copy"><view class="tool-copy"/></button>
   <button aria-label="引用回复" :disabled="!canQuote||!plainText" @click="emit('quote',plainText)"><view class="tool-quote"/></button>
   <button aria-label="赞同回复" :aria-pressed="rating==='like'" :class="{selected:rating==='like'}" :disabled="busy||!!rating||!replyMessageId(messageId)" @click="vote('like')"><view class="tool-thumb"/></button>
   <button aria-label="不赞同回复" :aria-pressed="rating==='dislike'" :class="{selected:rating==='dislike'}" :disabled="busy||!!rating||!replyMessageId(messageId)" @click="vote('dislike')"><view class="tool-thumb down"/></button>
  </view>
  <text v-if="error" class="tool-error" role="alert">{{error}}</text>
  <text v-else-if="rating" class="tool-confirmation">评价已保存</text>
 </view>
</template>
<style scoped>
.answer-tools{margin:7px 0 0}.answer-tool-row{display:flex;gap:5px}.answer-tool-row button{display:flex;align-items:center;justify-content:center;margin:0;width:36px;min-width:36px;height:36px;padding:0;border-radius:8px;background:rgba(255,255,255,.78);color:#7e7e99;line-height:1}.answer-tool-row button:after{border:0}.answer-tool-row button[disabled]{opacity:.45}.answer-tool-row button.selected{color:#5c3cf7;background:#e4ddff;opacity:1}.tool-copy{position:relative;width:10px;height:13px;border:1.4px solid currentColor;border-radius:2px}.tool-copy:before{content:'';position:absolute;width:9px;height:11px;left:-5px;top:-5px;border:1.4px solid currentColor;border-radius:2px;background:inherit}.tool-quote{position:relative;width:14px;height:13px;border:1.4px solid currentColor;border-radius:3px}.tool-quote:before{content:'';position:absolute;width:9px;height:1.4px;background:currentColor;right:-3px;top:0;transform:rotate(-42deg);box-shadow:0 -3px 0 2px #fff}.tool-quote:after{content:'';position:absolute;right:-3px;top:-4px;width:5px;height:5px;border-top:1.4px solid currentColor;border-right:1.4px solid currentColor}.tool-thumb{position:relative;width:11px;height:10px;margin-left:4px;margin-top:4px;border:1.4px solid currentColor;border-radius:1px 3px 3px 1px}.tool-thumb:before{content:'';position:absolute;left:-5px;top:-1px;width:2px;height:11px;border:1.4px solid currentColor;border-radius:1px}.tool-thumb:after{content:'';position:absolute;left:0;top:-7px;width:5px;height:7px;border:1.4px solid currentColor;border-bottom:0;border-radius:3px 3px 0 0;transform:skew(-12deg);background:inherit}.tool-thumb.down{transform:rotate(180deg);margin-top:-4px;margin-left:-3px}.tool-error,.tool-confirmation{display:block;margin-top:4px;font-size:11px;line-height:1.5;color:#85656e}.tool-confirmation{color:#82778e}
</style>
