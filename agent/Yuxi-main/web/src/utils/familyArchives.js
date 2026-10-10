/** 家庭档案的字段标签、缺失与统计展示。 */
export const profileLabels = {
  sex: '性别',
  birth_date: '出生日期',
  height_cm: '身高（cm）',
  activity_level: '活动水平',
  goal: '健康目标',
  medical_history: '已知病史',
  medications: '用药信息',
  doctor_instructions: '医嘱',
  allergens: '过敏原',
  avoidances: '忌口',
  preferences: '口味偏好',
  health_goals: '行为目标与复盘',
  condition_records: '病史与症状记录',
  medication_records: '结构化用药记录',
  instruction_records: '医嘱来源与有效期',
  allergy_records: '过敏反应与来源',
  meal_habits: '用餐安排',
  lifestyle: '活动与生活阶段'
}
export const metricDefinitions = {
  weight: { label: '体重', unit: 'kg', fields: { weight: '体重' } },
  blood_pressure: {
    label: '血压',
    unit: 'mmHg',
    fields: { systolic: '收缩压', diastolic: '舒张压' }
  },
  blood_glucose: { label: '血糖', unit: 'mmol/L', fields: { glucose: '血糖' } },
  blood_lipids: {
    label: '血脂四项',
    unit: 'mmol/L',
    fields: { tc: '总胆固醇', tg: '甘油三酯', hdl: '高密度脂蛋白', ldl: '低密度脂蛋白' }
  },
  height: { label: '身高', unit: 'cm', fields: { height: '身高' } }
}
export const conditionLabels = { fasting: '空腹', after_meal_2h: '餐后2小时', random: '随机' }
export const sexLabels = { female: '女', male: '男', unspecified: '不填写' }
export const activityLabels = {
  sedentary: '久坐',
  light: '轻度活动',
  moderate: '中度活动',
  high: '高活动量'
}

const factFields = [
  { key: 'description', label: '内容', type: 'text' },
  { key: 'source', label: '资料来源', type: 'text' },
  { key: 'recorded_on', label: '记录日期', type: 'date' },
  { key: 'reviewed_on', label: '最近核对日期', type: 'date' }
]
export const structuredDefinitions = {
  health_goals: {
    array: true,
    fields: [
      ...factFields,
      { key: 'start_date', label: '开始日期', type: 'date' },
      { key: 'review_date', label: '复盘日期', type: 'date' },
      {
        key: 'status',
        label: '状态',
        options: { active: '进行中', completed: '已完成', paused: '已暂停' }
      }
    ]
  },
  condition_records: {
    array: true,
    fields: [
      ...factFields,
      {
        key: 'status',
        label: '状态',
        options: {
          symptom: '自述症状',
          diagnosed: '已有确诊资料',
          resolved: '已结束',
          unknown: '待核对'
        }
      }
    ]
  },
  medication_records: {
    array: true,
    fields: [
      ...factFields,
      { key: 'dose', label: '剂量', type: 'text' },
      { key: 'frequency', label: '频次', type: 'text' },
      { key: 'start_date', label: '开始日期', type: 'date' },
      {
        key: 'status',
        label: '状态',
        options: { current: '正在使用', stopped: '已停用', unknown: '待核对' }
      }
    ]
  },
  instruction_records: {
    array: true,
    fields: [...factFields, { key: 'valid_until', label: '有效期至', type: 'date' }]
  },
  allergy_records: {
    array: true,
    fields: [
      ...factFields,
      { key: 'reaction', label: '反应描述', type: 'text' },
      {
        key: 'status',
        label: '确认情况',
        options: { reported: '本人自述', confirmed: '已有确认资料', unknown: '待核对' }
      }
    ]
  },
  meal_habits: {
    fields: [
      { key: 'weekday', label: '工作日 / 上学日用餐', type: 'text' },
      { key: 'weekend', label: '周末用餐', type: 'text' },
      { key: 'chewing_swallowing', label: '咀嚼和吞咽情况', type: 'text' }
    ]
  },
  lifestyle: {
    fields: [
      { key: 'activity_schedule', label: '活动与训练安排', type: 'text' },
      { key: 'sleep_schedule', label: '作息安排', type: 'text' },
      { key: 'special_stage', label: '特殊生活阶段（如妊娠、哺乳）', type: 'text' }
    ]
  }
}

/** 结构化事实使用字段标签展示，不把对象隐式转成字符串。 */
export function structuredText(key, value) {
  if (value === null || value === undefined) return '未填写'
  const definition = structuredDefinitions[key]
  const records = definition.array ? value : [value]
  if (!records.length) return '已确认无'
  return (
    records
      .map((record) =>
        definition.fields
          .filter(
            (field) =>
              record[field.key] !== null &&
              record[field.key] !== undefined &&
              record[field.key] !== ''
          )
          .map(
            (field) => `${field.label}：${field.options?.[record[field.key]] || record[field.key]}`
          )
          .join('；')
      )
      .join('\n') || '未填写'
  )
}

export function profileChanges(draft, allowed) {
  return Object.fromEntries(Object.entries(draft).filter(([key]) => allowed.includes(key)))
}

export function profileStatus(member) {
  if (!member.claimed) return '待本人认领'
  if (!member.allowed_fields?.length) return '待授权'
  if (member.missing_fields?.length) return '待补充'
  if (member.ready) return '基础档案已确认'
  if (member.confirmed === false) return member.is_guardian ? '待本人或监护人确认' : '待本人确认'
  return '部分字段可见'
}

/** 出生日期仅从当前授权投影读取，年龄按北京时间计算。 */
export function memberAge(member, now = Date.now()) {
  const born = member.profile?.birth_date
  if (!born) return null
  const today = shanghaiDate(now),
    age =
      Number(today.slice(0, 4)) -
      Number(born.slice(0, 4)) -
      (today.slice(5) < born.slice(5) ? 1 : 0)
  return age >= 0 ? age : null
}

export function shanghaiDate(value) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(new Date(value))
}

export function formatTime(value) {
  return value
    ? new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      }).format(new Date(value))
    : '未记录'
}

export function buildMetricSeries(records, key, dates) {
  const byDate = new Map()
  for (const record of [...records].sort(
    (a, b) => Date.parse(a.measured_at) - Date.parse(b.measured_at)
  )) {
    byDate.set(shanghaiDate(record.measured_at), record.values[key] ?? null)
  }
  return dates.map((date) => byDate.get(date) ?? null)
}

/** 三态列表：空编辑框仍为未知，只有明确选择无才形成空数组。 */
export function listState(value) {
  return !Array.isArray(value) ? 'unknown' : value.length ? 'known' : 'none'
}

/** 捕获编辑时版本与原值，刷新不得悄悄替换写入依据。 */
export function profileDraft(member, keys) {
  return {
    version: member.version,
    profile: Object.fromEntries(
      keys.map((key) => [key, JSON.parse(JSON.stringify(member.profile[key] ?? null))])
    )
  }
}

/** 只提交仍有代维护权限的实际改动；未修改字段不覆盖并发更新。 */
export function changedProfile(draft, original, editable) {
  return Object.fromEntries(
    editable
      .map((key) => [key, draft[key] === '' || draft[key] === undefined ? null : draft[key]])
      .filter(([key, value]) => JSON.stringify(value) !== JSON.stringify(original[key] ?? null))
  )
}

/** 权限缩减时立即移除草稿内失去授权的健康字段。 */
export function scrubProfileDraft(draft, editable) {
  for (const key of Object.keys(draft)) if (!editable.includes(key)) delete draft[key]
}

/** 未修改时间时保留原始秒与微秒，避免表单精度造成隐式更正。 */
export function measurementCorrection(draft, record, initialTime) {
  const payload = {
    expected_version: record.version,
    values: draft.values,
    note: draft.note,
    source: draft.source,
    condition: draft.condition
  }
  if (draft.measured_at !== initialTime)
    payload.measured_at = new Date(draft.measured_at + '+08:00').toISOString()
  return payload
}

/** 仅清理失效成员的授权投影，保留本人及其他成员的编辑上下文。 */
export function scrubFamilyAccess(family, now = Date.now(), unknownAccess = false) {
  if (!family) return family
  return {
    ...family,
    members: family.members.map((member) => {
      const expired = Date.parse(member.authorization?.expires_at) <= now
      if (member.is_self || (!unknownAccess && !expired) || !member.allowed_fields.length)
        return member
      return {
        ...member,
        profile: {},
        allowed_fields: [],
        editable_fields: [],
        missing_fields: [],
        unknown_fields: [],
        confirmed: null,
        confirmed_at: null,
        ready: false,
        is_guardian: false,
        authorization: member.authorization
          ? { ...member.authorization, fields: [], edit_fields: [] }
          : null
      }
    })
  }
}

/** 导出仅来自刚完成服务端授权校验的响应。 */
export function downloadFamilyJson(data, filename) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  )
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
