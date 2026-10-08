// Interaction fixtures only. Production safety rules and AI services are not connected.
export const diseaseOptions = ['糖尿病','高血压','高血脂','高尿酸／痛风','肾脏疾病','其他']
export const preferenceGroups = {
  goals: { title: '饮食目标', items: ['控糖','控压','控脂','低嘌呤','减脂','增肌','补充蛋白质','饮食均衡','改善蔬菜摄入','其他'] },
  tastePreferences: { title: '口味偏好', items: ['清淡','少油','少盐','偏甜','酸甜','咸鲜','微辣','香辣','麻辣','不吃辣','无特别要求','自定义'] },
  cuisines: { title: '菜系偏好', items: ['家常菜','粤菜','川菜','湘菜','鲁菜','苏菜','徽菜','快手菜','无特别要求','自定义'] },
}
export const restrictionFields = {
  allergy: { title: '食物过敏', status: 'allergyStatus', field: 'allergies', items: ['麸质谷物','含坚果','含乳','含大豆','含花生','含蛋','鱼类','含甲壳类'] },
  intolerance: { title: '食物不耐受', status: 'intoleranceStatus', field: 'intolerances', items: ['乳糖不耐受','麸质不耐受','大豆不耐受','鸡蛋不耐受','自定义'] },
  avoidance: { title: '饮食忌口', status: 'avoidanceStatus', field: 'avoidances', items: ['坚果','面筋','豆制品','鸡蛋','葱蒜','香菜','乳制品','牛羊肉','海鲜','辛辣'] },
}
export function diseaseSummary(member) {
  if (member.healthStatus === 'unknown') return '基础健康信息尚未填写，系统暂时只能提供通用饮食建议。'
  if (member.healthStatus === 'none') return '没有已知基础病，后续结合饮食目标与限制生成建议。'
  const summaries = { 糖尿病:'关注主食分配和添加糖，保持规律进餐', 高血压:'重点控制钠，减少高盐调味品、腌制和高钠加工食品', 高血脂:'控制饱和脂肪，优先清蒸、炖煮', '高尿酸／痛风':'关注嘌呤及酒精摄入', '高尿酸或痛风':'关注嘌呤及酒精摄入', 肾脏疾病:'蛋白质、钾、磷及液体要求需结合具体情况与医嘱', 其他:'结合填写的情况进行分析' }
  return (member.conditions || []).map(c => summaries[c] || c).join('；') + '。医生饮食要求优先；此为饮食管理参考，不代替医嘱。'
}
export function restrictionSummary(member, type) {
  const cfg = restrictionFields[type]
  return member[cfg.status] === 'none' ? '确认没有' : member[cfg.status] === 'set' ? (member[cfg.field] || []).join('、') || '请补充具体内容' : '未填写'
}
const aliases = { '鱼类':/鱼|鲈/, '含鱼类':/鱼|鲈/, '海鲜':/鱼|鲈|虾|蟹/, '含甲壳类':/虾|蟹/, '含蛋':/鸡蛋|炒蛋|煮蛋|蛋羹/, '鸡蛋不耐受':/鸡蛋|炒蛋|煮蛋|蛋羹/, '鸡蛋':/鸡蛋|炒蛋|煮蛋|蛋羹/, '含大豆':/豆腐|大豆|豆制品/, '豆制品':/豆腐|大豆|豆制品/, '大豆不耐受':/豆腐|大豆|豆制品/, '含乳':/牛奶|奶油|乳制品/, '乳制品':/牛奶|奶油|乳制品/, '乳糖不耐受':/牛奶|奶油|乳制品/, '麸质谷物':/全麦|小麦|面粉|面筋/, '麸质不耐受':/全麦|小麦|面粉|面筋/, '面筋':/面筋|全麦|小麦/, '含花生':/花生/, '含坚果':/坚果|核桃|杏仁/, '坚果':/坚果|核桃|杏仁/, '牛羊肉':/牛肉|羊肉/, '葱蒜':/葱|蒜/, '辛辣':/辣|椒/, '香菜':/香菜/ }
export function ingredientConflicts(members, ingredients) {
  const text = Array.isArray(ingredients) ? ingredients.join('、') : String(ingredients)
  return members.flatMap(m => {
    const restrictions = Object.values(restrictionFields).flatMap(cfg => m[cfg.status] === 'set' ? m[cfg.field] || [] : [])
    const doctor = m.doctorStatus === 'set' ? (m.clinicianGuidance.match(/(?:不吃|避免|禁止|不能吃)([^，。；]+)/g) || []).map(t => t.replace(/^(不吃|避免|禁止|不能吃)/,'')) : []
    return [...restrictions,...doctor].filter(value => (aliases[value] || { test: t => t.includes(value) }).test(text)).map(value => `${m.name}：${value}`)
  })
}
export function unknownRestrictions(members) {
  return members.some(m => ['healthStatus','allergyStatus','intoleranceStatus','avoidanceStatus','doctorStatus'].some(k => !m[k] || m[k] === 'unknown'))
}
export function unresolvedHealth(members) {
  return members.flatMap(m => {
    if (m.healthStatus !== 'set') return []
    if (!(m.conditions || []).length) return [`${m.name}请补充基础病情况`]
    if (m.conditions.includes('其他')) return [`${m.name}填写的“${m.otherCondition || '其他'}”尚无可用演示规则，请补充资料；正式版由 AI 分析`]
    if (m.conditions.includes('肾脏疾病') && (m.doctorStatus!=='set'||!m.clinicianGuidance)) return [`${m.name}请补充肾脏相关饮食要求，以便确定蛋白质等限制`]
    if (/高蛋白|增加蛋白/.test(m.clinicianGuidance) && /低蛋白|限制蛋白/.test(m.clinicianGuidance)) return [`${m.name}饮食要求存在矛盾，请复核`]
    return []
  })
}
export function memberNotes(member) {
  const notes = []
  if (member.healthStatus === 'set') notes.push(diseaseSummary(member))
  if (member.doctorStatus === 'set' && member.clinicianGuidance) notes.push('医生要求：' + member.clinicianGuidance)
  if (member.intoleranceStatus === 'set') notes.push('避开不耐受成分：' + member.intolerances.join('、'))
  return notes
}
export function dataWarnings(member) {
  const height = Number(member.height), weight = Number(member.weight)
  const warnings = []
  if (height && (height < 80 || height > 230)) warnings.push('身高数值可能有误')
  if (weight && (weight < 20 || weight > 250)) warnings.push('体重数值可能有误')
  if (height && weight && (weight / (height / 100) ** 2 < 15 || weight / (height / 100) ** 2 > 35)) warnings.push('BMI 超出常见范围')
  if ((member.goals || []).includes('增肌') && /限制蛋白|低蛋白/.test(member.clinicianGuidance)) warnings.push('饮食目标与填写的医嘱可能不一致')
  if (member.reportFlag) warnings.push('报告信息待复核')
  return warnings
}
