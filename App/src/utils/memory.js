import { getProfile,saveProfile } from './profile.js'
import { diseaseOptions } from './health.js'
export function remember(text,memberId=null) {
  const p=getProfile()
  const named=p.members.filter(m=>text.includes(m.name))
  const direct=named.filter(m=>text.includes(m.name+'有')||text.includes(m.name+'患')||text.includes(m.name+'以后')||text.includes(m.name+'喜欢'))
  const member=p.members.find(m=>m.id===memberId) || (direct.length===1?direct[0]:named.length===1?named[0]:/^我/.test(text)?p.members.find(m=>m.relation==='本人'):p.usageMode==='个人使用'?p.members[0]:null)
  if(!member)return {question:'这条长期信息是关于哪位成员？请加上成员称呼再告诉我。'}
  let field='',value=''
  const avoid=text.match(/(?:以后|长期|一直).*?(?:不吃|不要吃|避免吃)([^，。！？]+)/)
  const preference=text.match(/(?:喜欢|偏好|以后都吃|长期).*?(清淡|少盐|少油|不吃辣|微辣)/)
  const disease=diseaseOptions.find(d=>d!=='其他'&&text.includes(d))
  if(avoid){field='avoidances';value=avoid[1].trim()}
  else if(preference){field='tastePreferences';value=preference[1]}
  else if(disease&&/有|患|得了/.test(text)&&!/(没有|未患|没得|不是).*?(糖尿病|高血压|高血脂|肾脏疾病)/.test(text)){field='conditions';value=disease}
  else return {question:'请说明具体长期偏好、忌口或基础病情况，临时感受不会写入长期记忆。'}
  const status=field==='avoidances'?'avoidanceStatus':field==='conditions'?'healthStatus':null
  member.memoryBase ||= {}
  if(!member.memoryBase[field])member.memoryBase[field]={values:[...(member[field]||[])],status:status?member[status]:null}
  const provider=p.members.find(m=>m.claimedBy===(p.viewerAccount||'creator'))||p.members.find(m=>m.relation==='本人')
  const sourceKind=provider?.id===member.id?'本人提供':'家人提供'
  const entry={providerId:provider?.id||null,providerName:provider?.name||'家人',sourceKind,createdAt:new Date().toISOString(),id:Date.now()+Math.random(),memberId:member.id,member:member.name,text,field,value,source:'今日对话 · '+sourceKind+' · 用户自述',active:true}
  p.memories.push(entry);applyMemories(p,member,field);saveProfile(p);return {entry}
}
function applyMemories(p,member,field){const base=member.memoryBase?.[field];if(!base)return;const active=p.memories.filter(m=>m.memberId===member.id&&m.field===field);member[field]=[...new Set([...base.values,...active.map(m=>m.value)])];const status=field==='avoidances'?'avoidanceStatus':field==='conditions'?'healthStatus':null;if(status)member[status]=member[field].length?'set':base.status;if(field==='conditions')member.health=member[field].length?'用户自述':'一般成人'}
export function forget(id){const p=getProfile(),entry=p.memories.find(m=>m.id===id);if(!entry)return;p.memories=p.memories.filter(m=>m.id!==id);const member=p.members.find(m=>m.id===entry.memberId);if(member)applyMemories(p,member,entry.field);saveProfile(p)}
export function editMemory(id,text){const p=getProfile(),entry=p.memories.find(m=>m.id===id);if(!entry)return {question:'记忆不存在'};const created=remember(text,entry.memberId);if(created.entry)forget(id);return created}
