<script setup>
import {reactive,watch,onUnmounted} from 'vue'
import {onShow,onHide} from '@dcloudio/uni-app'
import {createChatFollowups} from '../services/chat-followups.js'

const props=defineProps({threadId:String,messageId:Number,saved:Array,disabled:Boolean})
const emit=defineEmits(['ask','ready'])
const state=reactive({items:[],status:'idle'})
const client=createChatFollowups({state})
let visible=true,pressed=false
function load(){pressed=false;if(visible&&!props.disabled)void client.load({threadId:props.threadId,messageId:props.messageId,saved:props.saved})}
watch(()=>[props.threadId,props.messageId,props.disabled],()=>{client.clear();load()},{immediate:true})
watch(()=>state.items.length,count=>{if(count&&visible)emit('ready')},{flush:'post'})
onShow(()=>{visible=true;if(state.status==='idle')load()})
onHide(()=>{visible=false;client.clear()})
onUnmounted(client.clear)
function ask(item){if(pressed||props.disabled||!visible)return;pressed=true;emit('ask',{question:item.question,messageId:props.messageId,threadId:props.threadId})}
</script>

<template>
 <view v-if="state.items.length" class="context-followups" role="group" aria-label="继续问营养师">
  <button v-for="item in state.items" :key="item.question" :disabled="disabled" @click="ask(item)"><text>{{item.label}}</text><text class="followup-arrow" aria-hidden="true">›</text></button>
 </view>
</template>

<style scoped>
.context-followups{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:8px 2px 20px;white-space:normal}
.context-followups button{display:flex;align-items:center;justify-content:space-between;gap:10px;max-width:100%;min-height:44px;margin:0;padding:8px 12px;box-sizing:border-box;border:1px solid #e6dcf2;border-radius:14px;background:rgba(255,255,255,.8);color:#9b86af;font-size:12px;line-height:1.5;text-align:left;white-space:normal;overflow-wrap:anywhere}
.context-followups button:after{border:0}.context-followups button:active{background:#faf7fe}.context-followups button[disabled]{opacity:.45}
.followup-arrow{flex:none;font-size:18px;line-height:1}
</style>
