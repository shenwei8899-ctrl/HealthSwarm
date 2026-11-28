import { getSession, setSession } from './session.js'

export const isServiceNoticeError = error => ['SERVICE_NOTICE_REQUIRED','SERVICE_NOTICE_CHANGED'].includes(error?.businessCode)
const presenters = []
let pending = null
const owner = () => { const account=getSession(); return JSON.stringify([account?.accountId,account?.token]) }
const validStatus = status => typeof status?.version==='string' && /^[a-f0-9]{64}$/.test(status?.content_hash||'') && typeof status.acknowledged==='boolean'
const cancelled = () => Object.assign(new Error('请阅读并确认服务声明后再使用 AI 建议，原内容已保留。'),{code:'SERVICE_NOTICE_DECLINED'})
const changed = () => Object.assign(new Error('账号已变化，请重新操作'),{code:'SESSION_CHANGED'})

export function installNoticePresenter(show) {
  const entry={show};presenters.push(entry)
  return () => { const index=presenters.indexOf(entry);if(index>=0)presenters.splice(index,1) }
}
export function validNotice(document) {
  return typeof document?.version==='string' && /^[a-f0-9]{64}$/.test(document?.content_hash||'') &&
    typeof document.title==='string' && typeof document.checkbox_text==='string' &&
    Array.isArray(document.sections) && document.sections.length===3 &&
    document.sections.every(section=>typeof section.title==='string'&&typeof section.text==='string')
}
export async function readServiceNotice(send) {
  const {data}=await send({path:'/api/service-notice',authenticated:false})
  if(!validNotice(data))throw new Error('服务声明暂时无法读取，请稍后重试')
  return data
}
async function present(document,mode,status=null) {
  const presenter=presenters.at(-1)?.show
  if(!presenter)throw new Error('服务声明窗口尚未准备好，请重试')
  return presenter({document,mode,status})
}
export async function viewNoticeDocument(document) {
  await present(document,'read')
}
export async function viewServiceNotice(send) {
  const identity=owner(),document=await readServiceNotice(send)
  let status=null
  if(getSession()?.token)status=(await send({path:'/api/account/service-notice'})).data
  if(identity!==owner())throw changed()
  await present(document,'read',status)
}
export async function acknowledgeReadNotice(send, receipt) {
  const identity=owner()
  if(!getSession()?.token)throw changed()
  const current=()=>{if(identity!==owner())throw changed()}
  let status
  try {
    status=(await send({path:'/api/account/service-notice',method:'POST',data:{
      version:receipt.version,content_hash:receipt.content_hash,acknowledged:true,
    }})).data
  }catch(error){
    current()
    if(error.code!=='NETWORK_ERROR')throw error
    status=(await send({path:'/api/account/service-notice'})).data
    if(status?.version!==receipt.version||status?.content_hash!==receipt.content_hash||status?.acknowledged!==true)throw error
  }
  current()
  if(!validStatus(status)||status.version!==receipt.version||status.content_hash!==receipt.content_hash||!status.acknowledged)
    throw new Error('声明确认尚未保存或版本已更新，请重新阅读并确认')
  setSession({...getSession(),serviceNotice:status},{preserveRevision:true})
  return status
}
export function ensureServiceNotice(send) {
  const identity=owner()
  if(pending?.identity===identity)return pending.promise
  const flight={identity}
  flight.promise=(async()=>{
    if(!getSession()?.token)throw changed()
    const current=()=>{if(identity!==owner())throw changed()}
    const status=(await send({path:'/api/account/service-notice'})).data
    current()
    if(!validStatus(status))throw new Error('声明确认状态暂时无法读取，请重试')
    if(!status.acknowledged){
      const document=await readServiceNotice(send);current()
      if(!await present(document,'confirm',status))throw cancelled()
      current()
      return acknowledgeReadNotice(send,document)
    }
    setSession({...getSession(),serviceNotice:status},{preserveRevision:true})
    return status
  })().finally(()=>{if(pending===flight)pending=null})
  pending=flight
  return flight.promise
}
