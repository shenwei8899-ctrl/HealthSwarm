import { birthDateError } from './member-age.js'
import { restrictionFields } from './health.js'

const answered = values => Array.isArray(values) && values.length > 0 && values.every(value =>
  typeof value === 'string' && value.trim() && !['其他', '自定义'].includes(value.trim()))

export function onboardingIssue(member, throughStep = 2) {
  const basics = basicProfileIssue(member)
  if (basics) return basics
  if (throughStep < 1) return null
  if (!['none', 'set'].includes(member.healthStatus)) return { step: 1, message: '请选择是否有已知基础病' }
  if (member.healthStatus === 'set' && (!member.conditions?.length || member.conditions.some(value => !value.trim()) ||
    member.conditions.includes('其他') && !member.otherCondition?.trim())) return { step: 1, message: '请补充具体基础病' }
  for (const [field, label] of [['goals', '饮食目标'], ['tastePreferences', '口味偏好']]) {
    if (!answered(member[field])) return { step: 1, message: '请选择或补充' + label }
  }
  if (member.cuisines?.length && !answered(member.cuisines)) return { step: 1, message: '请补充具体菜系偏好' }
  if (throughStep < 2) return null
  for(const type of [...Object.keys(restrictionFields),'doctor']){const issue=restrictionIssue(member,type);if(issue)return issue}
  return null
}

export function basicProfileIssue(member) {
  if (!member.name?.trim()) return { step: 0, message: '请填写姓名／称呼' }
  const dateError = member.birthDate ? birthDateError(member.birthDate) : '请选择出生日期'
  if (dateError) return { step: 0, message: dateError }
  if (!['女', '男'].includes(member.gender)) return { step: 0, message: '请选择性别' }
  for (const [key, label, limit] of [['height', '身高', 300], ['weight', '体重', 1000]]) {
    const value = member[key]
    if (value == null || String(value).trim() === '') return { step: 0, message: '请填写' + label }
    const amount = typeof value === 'number' || typeof value === 'string' ? Number(value) : NaN
    if (!Number.isFinite(amount) || amount <= 0 || amount > limit) return { step: 0, message: '请填写有效的' + label + '数值' }
  }
  return null
}

export function restrictionIssue(member,type){
  if(type==='doctor'){
    if(!['none','set'].includes(member.doctorStatus))return {step:2,message:'请选择医生饮食要求状态'}
    if(member.doctorStatus==='set'&&!member.clinicianGuidance?.trim())return {step:2,message:'请填写具体医生饮食要求'}
    return null
  }
  const cfg=restrictionFields[type]
  if(!cfg)return null
  if(!['none','set'].includes(member[cfg.status]))return {step:2,message:'请选择'+cfg.title+'状态'}
  if(member[cfg.status]==='set'&&!answered(member[cfg.field]))return {step:2,message:'请补充具体'+cfg.title+'内容'}
  return null
}
