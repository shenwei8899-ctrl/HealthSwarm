import { birthDateError } from './member-age.js'
import { restrictionFields } from './health.js'

const answered = values => Array.isArray(values) && values.length > 0 && values.every(value =>
  typeof value === 'string' && value.trim() && !['其他', '自定义'].includes(value.trim()))

export function onboardingIssue(member, throughStep = 2) {
  if (!member.name?.trim()) return { step: 0, message: '请填写姓名／称呼' }
  const dateError = member.birthDate ? birthDateError(member.birthDate) : '请选择出生日期'
  if (dateError) return { step: 0, message: dateError }
  if (throughStep < 1) return null
  if (!['none', 'set'].includes(member.healthStatus)) return { step: 1, message: '请选择是否有已知基础病' }
  if (member.healthStatus === 'set' && (!member.conditions?.length || member.conditions.some(value => !value.trim()) ||
    member.conditions.includes('其他') && !member.otherCondition?.trim())) return { step: 1, message: '请补充具体基础病' }
  for (const [field, label] of [['goals', '饮食目标'], ['tastePreferences', '口味偏好']]) {
    if (!answered(member[field])) return { step: 1, message: '请选择或补充' + label }
  }
  if (member.cuisines?.length && !answered(member.cuisines)) return { step: 1, message: '请补充具体菜系偏好' }
  if (throughStep < 2) return null
  for (const cfg of Object.values(restrictionFields)) {
    if (!['none', 'set'].includes(member[cfg.status])) return { step: 2, message: '请选择' + cfg.title + '状态' }
    if (member[cfg.status] === 'set' && !answered(member[cfg.field])) return { step: 2, message: '请补充具体' + cfg.title + '内容' }
  }
  if (!['none', 'set'].includes(member.doctorStatus)) return { step: 2, message: '请选择医生饮食要求状态' }
  if (member.doctorStatus === 'set' && !member.clinicianGuidance?.trim()) return { step: 2, message: '请填写具体医生饮食要求' }
  return null
}
