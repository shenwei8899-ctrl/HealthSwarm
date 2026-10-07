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
  preferences: '口味偏好'
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
  }
}
export const conditionLabels = { fasting: '空腹', after_meal_2h: '餐后2小时', random: '随机' }
export const sexLabels = { female: '女', male: '男', unspecified: '不填写' }
export const activityLabels = {
  sedentary: '久坐',
  light: '轻度活动',
  moderate: '中度活动',
  high: '高活动量'
}

export function profileChanges(draft, allowed) {
  return Object.fromEntries(Object.entries(draft).filter(([key]) => allowed.includes(key)))
}

export function profileStatus(member) {
  if (!member.claimed) return '待本人认领'
  if (!member.allowed_fields?.length) return '待授权'
  if (member.missing_fields?.length) return '待补充'
  if (member.ready) return '档案就绪'
  if (member.confirmed === false) return '待本人确认'
  return '部分字段可见'
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
