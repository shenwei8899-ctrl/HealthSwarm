import { localDate } from './meal-state.js'
// Fixture classification for frontend review, not a professional nutrition rule.
const vegetablePattern=/青菜|西兰花|黄瓜|番茄|时蔬|菠菜|上海青|白菜|胡萝卜|生菜|芹菜/
export function confirmedFor(records,scope='all') {
  if(scope==='all')return records
  return records.flatMap(record=>{
    const intake=record.memberIntake?.find(p=>String(p.memberId)===String(scope))
    if(intake)return [{...record,dishes:intake.dishes||[],portion:intake.portion,memberName:intake.memberName}]
    if(!record.memberIntake?.length&&String(record.memberId)===String(scope)&&record.captureScope!=='家庭共享桌菜')return [record]
    return []
  })
}
export function recordsOn(records,date){return records.filter(r=>(r.createdAt?localDate(new Date(r.createdAt)):String(r.date||'').slice(0,10))===date)}
export function vegetableTrend(records,days=7,end=new Date()) {
  return Array.from({length:days},(_,i)=>{
    const date=new Date(end);date.setDate(date.getDate()-(days-1-i));const key=localDate(date),daily=recordsOn(records,key)
    const meals=[...new Set(daily.map(r=>r.meal))]
    const vegetables=[...new Set(daily.filter(r=>(r.dishes||[]).some(d=>vegetablePattern.test(d))).map(r=>r.meal))]
    return {date:key,recorded:meals.length,vegetables:vegetables.length,ratio:meals.length?vegetables.length/meals.length:null}
  })
}
