const text = (key, label, type = 'text', options) => ({ key, label, type, options })
const common = [text('description', '内容'), text('source', '来源'), text('recorded_on', '记录日期', 'date'), text('reviewed_on', '复核日期', 'date')]
export const profileFields = [
  text('sex', '性别', 'select', [['female', '女'], ['male', '男'], ['unspecified', '未指定']]),
  text('birth_date', '出生日期', 'date'), text('height_cm', '身高（cm）', 'number'),
  text('activity_level', '活动量', 'select', [['sedentary', '久坐'], ['light', '轻度'], ['moderate', '中等'], ['high', '较高']]),
  text('goal', '饮食目标'), text('medical_history', '既往情况'), text('medications', '用药说明'),
  text('doctor_instructions', '医嘱说明'), text('allergens', '过敏原（每行一项）', 'lines'),
  text('avoidances', '忌口（每行一项）', 'lines'), text('preferences', '饮食偏好'),
]
export const recordGroups = [
  { key: 'health_goals', label: '健康目标', fields: [...common, text('start_date', '开始日期', 'date'), text('review_date', '复盘日期', 'date'), text('status', '状态', 'select', [['active', '进行中'], ['completed', '已完成'], ['paused', '暂停']])] },
  { key: 'condition_records', label: '健康情况记录', fields: [...common, text('status', '状态', 'select', [['symptom', '自述症状'], ['diagnosed', '已有确诊资料'], ['resolved', '已缓解'], ['unknown', '不明确']])] },
  { key: 'medication_records', label: '用药记录', fields: [...common, text('dose', '剂量'), text('frequency', '频次'), text('start_date', '开始日期', 'date'), text('status', '状态', 'select', [['current', '当前使用'], ['stopped', '已停止'], ['unknown', '不明确']])] },
  { key: 'instruction_records', label: '医嘱记录', fields: [...common, text('valid_until', '有效至', 'date')] },
  { key: 'allergy_records', label: '过敏记录', fields: [...common, text('reaction', '反应'), text('status', '状态', 'select', [['reported', '自述'], ['confirmed', '已确认'], ['unknown', '不明确']])] },
]
export const objectGroups = [
  { key: 'meal_habits', label: '用餐习惯', fields: [text('weekday', '工作日'), text('weekend', '周末'), text('chewing_swallowing', '咀嚼与吞咽情况')] },
  { key: 'lifestyle', label: '生活安排', fields: [text('activity_schedule', '活动安排'), text('sleep_schedule', '作息'), text('special_stage', '特殊阶段')] },
]
export const metricKinds = [
  { key: 'weight', label: '体重', unit: 'kg', fields: [['weight', '体重']] },
  { key: 'height', label: '身高', unit: 'cm', fields: [['height', '身高']] },
  { key: 'blood_pressure', label: '血压', unit: 'mmHg', fields: [['systolic', '收缩压'], ['diastolic', '舒张压']] },
  { key: 'blood_glucose', label: '血糖', unit: 'mmol/L', fields: [['glucose', '血糖']] },
  { key: 'blood_lipids', label: '血脂', unit: 'mmol/L', fields: [['tc', '总胆固醇'], ['tg', '甘油三酯'], ['hdl', '高密度脂蛋白'], ['ldl', '低密度脂蛋白']] },
]
export function profileDraft(profile) {
  const draft = JSON.parse(JSON.stringify(profile || {}))
  for (const f of profileFields) draft[f.key] = f.type === 'lines' ? (profile?.[f.key] || []).join('\n') : profile?.[f.key] ?? ''
  for (const g of recordGroups) draft[g.key] ||= []
  for (const g of objectGroups) draft[g.key] ||= {}
  return draft
}
export function measurementTimestamp(value) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) throw new Error('测量时间格式：YYYY-MM-DDTHH:mm')
  const parts = value.split(/[-T:]/).map(Number), date = new Date(value)
  const actual = [date.getFullYear(), date.getMonth()+1, date.getDate(), date.getHours(), date.getMinutes()]
  if (parts.some((part, index) => part !== actual[index])) throw new Error('测量日期或时间不存在，请核对后填写')
  return date.toISOString()
}
export function profileChanges(draft, member) {
  const changes = {}, original = profileDraft(member.profile)
  for (const field of [...profileFields, ...recordGroups, ...objectGroups]) {
    if (JSON.stringify(draft[field.key]) === JSON.stringify(original[field.key])) continue
    if (!member.editable_fields.includes(field.key)) throw new Error('当前字段不可修改')
    let value = draft[field.key]
    if (field.type === 'lines') value = String(value).split(/\r?\n/).map(x => x.trim()).filter(Boolean)
    else if (field.type === 'number') {
      value = value === '' || value == null ? null : Number(value)
      if (value !== null && (!Number.isFinite(value) || value <= 0 || value > 300)) throw new Error('请填写有效身高')
    } else if (Array.isArray(value)) {
      value = value.map(row => Object.fromEntries(Object.entries(row).map(([k, v]) => [k, v === '' ? null : v])))
      if (value.some(row => !row.description?.trim())) throw new Error('每项记录需要填写内容')
    } else if (value && typeof value === 'object') value = Object.fromEntries(Object.entries(value).map(([k, v]) => [k, v === '' ? null : v]))
    else value = value === '' ? null : value
    changes[field.key] = value
  }
  return changes
}
