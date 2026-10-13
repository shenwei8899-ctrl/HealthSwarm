const dateParts = value => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day ? { year, month, day, time: date.getTime() } : null
}

export function shanghaiDate(date = new Date()) {
  return new Date(date.getTime() + 8 * 3600000).toISOString().slice(0, 10)
}

export function memberAge(member, onDate = shanghaiDate()) {
  const birth = dateParts(member.birthDate), current = dateParts(onDate)
  if (member.birthDate) {
    if (!birth || !current || birth.time > current.time) return { years: null, months: null }
    const months = (current.year - birth.year) * 12 + current.month - birth.month - Number(current.day < birth.day)
    return { years: Math.floor(months / 12), months }
  }
  // Old drafts supplied a default 30 without a birthday. Its origin is unknown.
  const age = member.age
  const known = age !== '' && age !== null && age !== undefined && Number.isFinite(Number(age)) && Number(age) >= 0 && Number(age) <= 130 && (Number(age) !== 30 || member.ageSource === 'self_reported')
  return { years: known ? Number(age) : null, months: null }
}

export function birthDateError(value, onDate = shanghaiDate()) {
  if (!value) return ''
  const birth = dateParts(value), current = dateParts(onDate)
  if (!birth) return '出生日期无效，请重新选择'
  if (!current || birth.time > current.time) return '出生日期不能晚于今天'
  return ''
}

export function ageLabel(member, onDate = shanghaiDate()) {
  const age = memberAge(member, onDate)
  return age.years === null ? '年龄未填写' : age.years < 2 && age.months !== null ? `${age.months} 个月` : `${age.years} 岁`
}
