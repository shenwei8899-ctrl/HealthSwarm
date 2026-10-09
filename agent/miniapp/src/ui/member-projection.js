export function familyChoices(rows) {
  return (Array.isArray(rows) ? rows : []).filter(row => row && typeof row.id === 'string').map(row => ({
    id: row.id, name: typeof row.name === 'string' ? row.name : '家庭', is_owner: row.is_owner === true,
  }))
}

export function familyMemberChoices(family) {
  return (Array.isArray(family?.members) ? family.members : []).filter(row => row && typeof row.id === 'string').map(row => ({
    id: row.id,
    name: typeof row.name === 'string' ? row.name : '家庭成员',
    relationship: typeof row.relationship === 'string' ? row.relationship : '未填写关系',
    is_self: row.is_self === true,
    is_active: row.is_active === true,
  }))
}

export function eligibleHealthMembers(rows) {
  return (Array.isArray(rows) ? rows : []).filter(row => row && typeof row.id === 'string'
    && row.is_owner === true && row.relationship_label === '本人' && Array.isArray(row.scopes)
    && row.scopes.includes('profile_view') && row.scopes.includes('profile_edit')).map(row => ({
    id: row.id, display_name: typeof row.display_name === 'string' ? row.display_name : '本人健康成员',
  }))
}

export function profileLinkSummary(value) {
  if (!value || typeof value.member_id !== 'string') throw new Error('服务未返回可核对的成员关联')
  return {
    member_id: value.member_id,
    source_member_id: typeof value.source_member_id === 'string' ? value.source_member_id : null,
    family_id: typeof value.family_id === 'string' ? value.family_id : null,
    linked_at: typeof value.linked_at === 'string' ? value.linked_at : null,
  }
}

export function basicProfileSummary(value) {
  if (!value || typeof value.status !== 'string') throw new Error('服务未返回基础档案状态')
  const descriptions = {
    profile_not_linked: '尚未关联家庭档案',
    profile_unconfirmed: '基础档案当前版本待本人确认，请在后台核对',
    profile_incomplete: '基础档案尚待补充，请在后台完善',
    self_confirmed_profile: '已确认的基础档案可读取',
  }
  return {
    ready: value.status === 'ready' && value.profile_available === true,
    description: descriptions[value.code] || '基础档案暂不可读取，请在后台核对',
    confirmed_version: Number.isInteger(value.confirmed_version) ? value.confirmed_version : null,
  }
}
