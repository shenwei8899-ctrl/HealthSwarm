export function selfMember(family) {
  if (!family || typeof family.id !== 'string' || !Array.isArray(family.members)) throw new Error('家庭档案返回的数据不完整')
  const member = family.members.find(m => m.is_self === true && m.is_active === true)
  if (!member) return null
  if (typeof member.id !== 'string' || !Number.isSafeInteger(member.version) || !member.profile || typeof member.ready !== 'boolean') throw new Error('本人档案状态不完整')
  return { id: member.id, version: member.version, ready: member.ready, confirmed: member.confirmed === true,
    profile: { sex: member.profile.sex ?? null, birth_date: member.profile.birth_date ?? null,
      height_cm: member.profile.height_cm ?? null, activity_level: member.profile.activity_level ?? null, goal: member.profile.goal ?? null },
  }
}

export function basicProfileInput(form) {
  const height = form.height_cm === '' || form.height_cm == null ? null : Number(form.height_cm)
  if (height !== null && (!Number.isFinite(height) || height <= 0 || height > 300)) throw new Error('请填写有效的身高')
  if (form.birth_date && !/^\d{4}-\d{2}-\d{2}$/.test(form.birth_date)) throw new Error('生日格式为 YYYY-MM-DD')
  if (!['female', 'male', 'unspecified', null, ''].includes(form.sex ?? null)) throw new Error('请选择性别')
  if (!['sedentary', 'light', 'moderate', 'high', null, ''].includes(form.activity_level ?? null)) throw new Error('请选择活动量')
  return { sex: form.sex || null, birth_date: form.birth_date || null, height_cm: height,
    activity_level: form.activity_level || null, goal: form.goal?.trim() || null }
}
