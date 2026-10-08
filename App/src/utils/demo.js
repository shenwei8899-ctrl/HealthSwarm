// Fixed examples for interaction review, not medical or image inference.
import { ingredientConflicts, unresolvedHealth, unknownRestrictions, memberNotes } from './health.js'
export function getMealMembers(profile) {
  if(profile.usageMode==='个人使用'&&!profile.mealScoped)return [profile.members.find(m=>m.relation==='本人')||profile.members[0]].filter(Boolean)
  const ids = profile.defaultDiners || profile.members.map(member => member.id)
  const selected = profile.members.filter(member => ids.includes(member.id))
  return selected.length ? selected : profile.members
}

export function reviewReasons(profile) {
  const reasons = []
  if(getMealMembers(profile).some(m=>Number(m.age)<18))reasons.push('原型暂不支持儿童个体化配餐，请补充适用成员资料')
  reasons.push(...unresolvedHealth(getMealMembers(profile)))
  return reasons
}

export function createPlan(profile, meal = '晚餐') {
  const breakfast = meal === '早餐'
  const lunch = meal === '午餐'
  const members = getMealMembers(profile)
  const count = members.length
  const ingredients = breakfast ? [
    { id: 11, icon: '🌾', name: '原味燕麦', perPerson: 40, unit: 'g', pack: 500, priceCents: 1690 },
    { id: 12, icon: '🥚', name: '鸡蛋', perPerson: 1, unit: '个', pack: 6, priceCents: 990 },
    { id: 13, icon: '🥒', name: '黄瓜', perPerson: 100, unit: 'g', pack: 300, priceCents: 590 },
  ] : lunch ? [
    { id: 12, icon: '🥚', name: '鸡蛋', perPerson: 1, unit: '个', pack: 6, priceCents: 990 },
    { id: 2, icon: '🥬', name: '上海青', perPerson: 120, unit: 'g', pack: 500, priceCents: 890 },
    { id: 3, icon: '🍄', name: '鲜香菇', perPerson: 40, unit: 'g', pack: 150, priceCents: 690 },
    { id: 4, icon: '🍅', name: '番茄', perPerson: 120, unit: 'g', pack: 500, priceCents: 790 },
    { id: 5, icon: '◻', name: '嫩豆腐', perPerson: 100, unit: 'g', pack: 300, priceCents: 480 },
    { id: 6, icon: '🌾', name: '杂粮米', perPerson: 50, unit: 'g', pack: 500, priceCents: 1290 },
  ] : [
    { id: 1, icon: '🐟', name: '鲜鲈鱼', perPerson: 150, unit: 'g', pack: 500, priceCents: 3280 },
    { id: 2, icon: '🥬', name: '上海青', perPerson: 120, unit: 'g', pack: 500, priceCents: 890 },
    { id: 3, icon: '🍄', name: '鲜香菇', perPerson: 40, unit: 'g', pack: 150, priceCents: 690 },
    { id: 4, icon: '🍅', name: '番茄', perPerson: 100, unit: 'g', pack: 500, priceCents: 790 },
    { id: 5, icon: '◻', name: '嫩豆腐', perPerson: 100, unit: 'g', pack: 300, priceCents: 480 },
    { id: 6, icon: '🌾', name: '杂粮米', perPerson: 50, unit: 'g', pack: 500, priceCents: 1290 },
  ]
  const dishes = breakfast ? [
    { icon: '🥣', name: '原味燕麦粥', detail: `燕麦 ${40 * count}g · 清水煮熟`, color: '#f1e6d1', kcal: 150 },
    { icon: '🥚', name: '水煮蛋', detail: `鸡蛋 ${count} 个 · 煮熟后食用`, color: '#f4ead0', kcal: 75 },
    { icon: '🥒', name: '清爽黄瓜', detail: `黄瓜 ${100 * count}g · 清洗切片`, color: '#e4f0d3', kcal: 25 },
  ] : lunch ? [
    { icon: '🍅', name: '番茄炒蛋', detail: `番茄 ${120 * count}g · 鸡蛋 ${count} 个`, color: '#f8ded2', kcal: 170 },
    { icon: '🥬', name: '香菇青菜', detail: `上海青 ${120 * count}g · 香菇 ${40 * count}g`, color: '#e4f0d3', kcal: 95 },
    { icon: '◻', name: '清炖豆腐', detail: `嫩豆腐 ${100 * count}g · 清水炖熟`, color: '#f1e6d1', kcal: 110 },
    { icon: '🍚', name: '杂粮饭', detail: `生米 ${50 * count}g · 加水煮熟`, color: '#f1e6d1', kcal: 220 },
  ] : [
    { icon: '🐟', name: '清蒸鲈鱼', detail: `鲈鱼 ${150 * count}g · 姜葱蒸熟`, color: '#dcebe6', kcal: 180 },
    { icon: '🥬', name: '香菇青菜', detail: `上海青 ${120 * count}g · 香菇 ${40 * count}g`, color: '#e4f0d3', kcal: 95 },
    { icon: '🍅', name: '番茄豆腐汤', detail: `番茄 ${100 * count}g · 豆腐 ${100 * count}g`, color: '#f8ded2', kcal: 125 },
    { icon: '🍚', name: '杂粮饭', detail: `生米 ${50 * count}g · 加水煮熟`, color: '#f1e6d1', kcal: 220 },
  ]
  const raw = { meal, count, members, blocked: reviewReasons(profile), dishes, minutes: breakfast ? 15 : lunch ? 30 : 35,
    products: ingredients.map(p => ({ ...p, need: p.perPerson * count, quantity: Math.ceil(p.perPerson * count / p.pack) })),
    steps: breakfast ? ['先煮燕麦粥，同时把鸡蛋煮熟。', '清洗黄瓜、切片，分别装盘。', '按实际食量分餐，吃完拍照记录。'] : lunch ? ['先煮杂粮饭，清洗番茄、上海青和香菇。', '鸡蛋炒至熟透后加入番茄，少量调味。', '炒熟香菇青菜，同时将豆腐清炖至热透。', '按家庭成员实际食量分餐，吃完拍照记录。'] : ['先煮杂粮饭，再清洗切配蔬菜和鱼。', '锅内水沸后蒸鱼，至鱼肉熟透。', '煮番茄豆腐汤，同时炒香菇青菜。', '调味和蘸汁分开放，按实际食量分餐。'],
  }
  // Replace known conflicts in the actual fixture recipe and procurement, never just a flag.
  const replacements = [
    { pattern:/鱼|鲈|虾/, ids:[1,7], name:'清蒸鸡肉', icon:'🍗', product:{id:20,name:'鸡胸肉',icon:'🍗',perPerson:150,unit:'g',pack:500,priceCents:2590}, detail:'鸡肉', kcal:180 },
    { pattern:/鸡蛋|炒蛋|煮蛋/, ids:[12], name: lunch?'番茄炖鸡肉':'清蒸鸡肉', icon:'🍗', product:{id:20,name:'鸡胸肉',icon:'🍗',perPerson:100,unit:'g',pack:500,priceCents:2590}, detail:'鸡肉', kcal:150 },
    { pattern:/豆腐/, ids:[5], name: lunch?'清炖冬瓜':'番茄冬瓜汤', icon:'🥣', product:{id:21,name:'冬瓜',icon:'🥣',perPerson:100,unit:'g',pack:500,priceCents:690}, detail:'冬瓜', kcal:55 },
    { pattern:/燕麦/, ids:[11], name:'小米粥', icon:'🥣', product:{id:22,name:'小米',icon:'🌾',perPerson:40,unit:'g',pack:500,priceCents:1590}, detail:'小米', kcal:150 },
  ]
  for (const replacement of replacements) {
    const targets = raw.dishes.filter(d => replacement.pattern.test(d.name) && ingredientConflicts(members,d.name+' '+d.detail).length)
    if (!targets.length) continue
    const product = replacement.product
    if (ingredientConflicts(members, product.name).length) continue
    raw.dishes = raw.dishes.map(d => targets.includes(d) ? {...d,name:replacement.name,icon:replacement.icon,kcal:replacement.kcal,detail:`${replacement.detail} ${product.perPerson*count}g · 清水烹饪，调味另放`} : d)
    raw.products = raw.products.filter(p => !replacement.ids.includes(p.id))
    const existing = raw.products.find(p => p.id === product.id)
    if (existing) { existing.need += product.perPerson*count; existing.quantity=Math.ceil(existing.need/existing.pack) }
    else raw.products.push({...product,need:product.perPerson*count,quantity:Math.ceil(product.perPerson*count/product.pack)})
  }
  // Avoid an explicit scallion/garlic restriction without changing procurement selections.
  if (ingredientConflicts(members,'葱蒜').length) raw.dishes=raw.dishes.map(d=>({...d,detail:d.detail.replace('姜葱','清水')}))
  raw.blocked.push(...ingredientConflicts(members,raw.dishes.map(d=>d.name+' '+d.detail).concat(raw.products.map(p=>p.name))))
  raw.general = unknownRestrictions(members)
  raw.safetyText = raw.blocked.length ? '暂无法完成安全适配，请补充资料' : raw.general ? '通用建议 · 未填写信息不代表没有限制；已避开已知冲突' : '已避开已知冲突'
  raw.memberNotes = members.map(member=>({id:member.id,name:member.name,notes:memberNotes(member),portion: member.healthStatus==='set'&&member.conditions?.includes('糖尿病') ? '主食单独分份，具体量依医嘱；其他菜按实际食量' : '按实际食量分餐'}))
  raw.nutrition = {kcal:raw.dishes.reduce((sum,d)=>sum+d.kcal,0)*count,protein:32*count,fat:16*count,carbs:74*count,sugars:8*count}
  return raw
}

export function subtotal(products, selected) {
  return products.filter(p => selected.includes(p.id)).reduce((sum, p) => sum + p.priceCents * p.quantity, 0)
}

export function photoEstimate(portion, oil) {
  const factor = { '半份': 0.5, '八成': 0.8, '全部': 1 }[portion] || 1
  const extra = { '少油': 0, '中等': 45, '不确定': 45, '偏多': 90 }[oil] || 0
  return { kcal: Math.round((575 + extra) * factor), low: Math.round((500 + extra) * factor), high: Math.round((665 + extra) * factor), protein: Math.round(32 * factor), carbs: Math.round(74 * factor), sugars: Math.round(8*factor), fat: Math.round((16 + extra / 9) * factor) }
}
