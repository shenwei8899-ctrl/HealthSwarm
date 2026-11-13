import { request } from './request.js'

export function pickVisionFiles(kind, document, success, fail) {
  const meal = kind === 'meal'
  const extensions = meal ? ['jpg', 'jpeg', 'png', 'webp'] : ['pdf', 'jpg', 'jpeg', 'png', 'webp']
  if (!document) return uni.chooseImage({ count: meal ? 3 : 9, sourceType: ['camera', 'album'], sizeType: ['original'], success, fail })
  const count = meal ? 3 : 20
  if (typeof uni.chooseMessageFile === 'function') return uni.chooseMessageFile({ count, type: 'file', extension: extensions, success, fail })
  if (typeof uni.chooseFile === 'function') return uni.chooseFile({ count, type: 'all', extension: extensions.map(ext => '.' + ext), success, fail })
  fail({ errMsg: '当前环境不支持导入文件，请使用相册或拍照。', unsupported: true })
}

export function resolveOnboardingReports(selections, members, memberRefs) {
  const reports = []
  for (const [clientRef, files] of selections) {
    if (!files.length) continue
    const id = memberRefs && Object.hasOwn(memberRefs, clientRef) ? memberRefs[clientRef] : clientRef
    const member = members.find(row => String(row.id) === id)
    if (member?.healthMemberId) reports.push({ memberId: member.healthMemberId, files })
  }
  return reports
}

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
