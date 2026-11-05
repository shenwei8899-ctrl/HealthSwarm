import { request } from './request.js'

export async function readCloudReportStatus(memberId, send=request) {
  const {data:members}=await send({path:'/api/health/v1/members'})
  if(!Array.isArray(members))throw new Error('报告权限返回异常，请重新读取')
  const member=members.find(row=>row.id===memberId)
  if(!member)return 'unavailable'
  if(!member.scopes?.includes('report_view'))return 'restricted'
  try {
    const [observations,vision]=await Promise.all([
      send({path:`/api/health/v1/members/${encodeURIComponent(memberId)}/observations`}),
      send({path:`/api/health/v1/members/${encodeURIComponent(memberId)}/vision/page?kind=report&jobs_limit=1&drafts_limit=20`}),
    ])
    if(!Array.isArray(observations.data)||!Array.isArray(vision.data.drafts))throw new Error('报告状态返回不完整，请重新读取')
    return observations.data.length?'done':vision.data.drafts.some(d=>d.review_status==='pending_confirmation')?'review':'empty'
  } catch(error) {
    if([403,404,410].includes(Number(error.code)))return 'restricted'
    throw error
  }
}
