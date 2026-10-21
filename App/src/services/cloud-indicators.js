import { request } from './request.js'
export const indicatorFields={weight:['weight'],blood_glucose:['glucose'],blood_pressure:['systolic','diastolic'],blood_lipids:['tc','tg','hdl','ldl']}
export function summarizeMeasurements(records,kind){
  if(!indicatorFields[kind])throw new Error('请选择有效指标')
  const groups=new Map()
  for(const row of records){
    const condition=kind==='blood_glucose'?row.condition:'same_observation',unit=row.unit||''
    const key=condition+':'+unit
    if(!groups.has(key))groups.set(key,{condition,unit,statistics:{}})
    const group=groups.get(key)
    for(const field of indicatorFields[kind]){const value=row[field];if(typeof value!=='number'||!Number.isFinite(value)||value<=0)continue;const stat=group.statistics[field]||{count:0,sum:0,minimum:value,maximum:value};stat.count++;stat.sum+=value;stat.minimum=Math.min(value,stat.minimum);stat.maximum=Math.max(value,stat.maximum);stat.mean=Math.round(stat.sum/stat.count*100)/100;group.statistics[field]=stat}
  }
  return [...groups.values()]
}
export async function readMeasurements(familyId,memberId,kind,start,end,send=request){
  if(!familyId||!memberId||!indicatorFields[kind])throw new Error('请先选择成员和指标')
  const from=Date.parse(start+'T00:00:00+08:00'),to=Date.parse(end+'T00:00:00+08:00')
  if(!Number.isFinite(from)||!Number.isFinite(to)||to<from||to-from>365*86400000)throw new Error('请选择最多366天的有效日期范围')
  const {data}=await send({path:`/api/family/${encodeURIComponent(familyId)}/members/${encodeURIComponent(memberId)}/measurements?kind=${kind}&from_date=${start}&to_date=${end}&limit=500&offset=0&include_voided=false`})
  if(!Array.isArray(data.items))throw new Error('指标记录返回不完整，请重试')
  const records=data.items.filter(r=>!r.voided_at&&r.kind===kind).map(r=>({record_id:r.id,version:r.version,measured_at:r.measured_at,source:r.source,condition:r.condition,unit:r.unit,...r.values}))
  return {records,total:data.total,truncated:data.total>data.items.length,review:{groups:summarizeMeasurements(records,kind),questions:[]},source_member_id:memberId}
}
