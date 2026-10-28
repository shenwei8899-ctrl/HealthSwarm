import {validateDailyArrangement} from './daily-arrangement-client.js'

// 与服务端业务日期一致，不能由设备所在时区决定是否放行。
export function preparationDate() { return new Date(Date.now()+8*60*60*1000).toISOString().slice(0,10) }
export function preparationReady(value,date=preparationDate()) {
  if(value?.status!=='ready'||!value.id||!value.thread_id||value.date!==date)return false
  try { validateDailyArrangement(value.arrangement,date);return true } catch { return false }
}
