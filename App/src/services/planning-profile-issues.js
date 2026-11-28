// 只保留补齐资料所需的信息，不缓存任何档案字段原值。
export function planningProfileIssues(value) {
  if (!Array.isArray(value) || value.length > 20) return []
  const sections = ['basic', 'health', 'preferences', 'restrictions']
  return value.filter(row => typeof row?.member_id === 'string' && row.member_id && typeof row.name === 'string' && Array.isArray(row.fields)).map(row => ({
    member_id: row.member_id, name: row.name, version: row.version, can_edit: row.can_edit === true,
    fields: row.fields.slice(0,40).filter(field => typeof field?.field === 'string' && typeof field.label === 'string').map(field => ({
      field: field.field, label: field.label, message: typeof field.message === 'string' ? field.message : '请核对'+field.label,
      reason: field.reason === 'missing' ? 'missing' : 'invalid', section: sections.includes(field.section) ? field.section : 'basic',
    })),
  })).filter(row => row.fields.length)
}

export function profileCompletionUrl(problem) {
  if (!problem?.can_edit || !problem.member_id) return null
  const first=problem.fields[0]
  return '/pages/profile/member?id='+encodeURIComponent(problem.member_id)+'&complete=1&section='+encodeURIComponent(first?.section||'basic')+'&field='+encodeURIComponent(first?.field||'')
}
