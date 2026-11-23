import { request } from './request.js'
import { storageContext } from './storage.js'

export function normalizeFollowups(value) {
 if(!Array.isArray(value)||value.length>2)return []
 const seen=new Set(),items=[]
 for(const row of value){
  if(typeof row?.label!=='string'||typeof row?.question!=='string'||/[\x00-\x1f]/.test(row.label+row.question))return []
  const label=row.label.trim(),question=row.question.trim()
  if(!label||label.length>24||!question||question.length>160||/[\x00-\x1f]/.test(label+question)||seen.has(question))return []
  seen.add(question);items.push({label,question})
 }
 return items
}

export function followupMessageId(value){
 const text=String(value??'')
 return /^[1-9]\d*$/.test(text)&&Number.isSafeInteger(Number(text))?Number(text):null
}

export function createChatFollowups({state,send=request,context=storageContext,schedule=setTimeout,cancel=clearTimeout}){
 let generation=0,timer=null
 function clear(){generation++;cancel(timer);timer=null;state.items=[];state.status='idle'}
 async function load({threadId,messageId,saved=[]}){
  clear()
  if(!threadId||!followupMessageId(messageId))return
  const mine=generation,scope=context(),current=()=>mine===generation&&scope===context()
  state.items=normalizeFollowups(saved)
  if(state.items.length){state.status='ready';return}
  state.status='loading'
  const path=`/api/health/v1/consultations/${encodeURIComponent(threadId)}/messages/${messageId}/followups`
  async function read(method='GET',poll=0){
   try{
    const {data}=await send({path,method,timeout:20000})
    if(!current())return
    if(data?.message_id!==Number(messageId)||!['absent','pending','ready','unavailable'].includes(data.status))throw Error('追问来源不匹配')
    if(data.status==='absent'&&method==='GET'&&poll===0)return read('POST')
    if(data.status==='pending'&&poll<20){timer=schedule(()=>{timer=null;void read('GET',poll+1)},1000);return}
    state.items=data.status==='ready'?normalizeFollowups(data.followups):[]
    state.status=state.items.length?'ready':'unavailable'
   }catch{if(current()){state.items=[];state.status='unavailable'}}
  }
  await read()
 }
 return {load,clear}
}
