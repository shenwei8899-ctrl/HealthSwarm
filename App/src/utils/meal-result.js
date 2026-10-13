import { ingredientConflicts, unresolvedHealth, memberNotes } from './health.js'
import { productsFromDemands } from './meal-demands.js'
import { normalizeDishNutrition } from './dish-nutrition.js'

const invalid = message => { throw Object.assign(new Error('配餐结果不完整：' + message), { code: 'INVALID_MEAL_RESULT' }) }
const number = value => typeof value === 'number' && Number.isFinite(value) && value >= 0
const strings = value => Array.isArray(value) && value.every(item => typeof item === 'string' && item.trim())

function mealNutrition(dishes, notes) {
  if (notes.some(note => !note.dishes.length)) return null
  const fields={kcal:'energyKcal',protein:'proteinG',fat:'fatG',carbs:'carbohydrateG',fiber:'fiberG',sodium:'sodiumMg'}
  return Object.fromEntries(Object.entries(fields).map(([key,field])=>{
    let total=0
    for (const portion of notes.flatMap(note=>note.dishes)) {
      const value=dishes.find(dish=>dish.recipeId===portion.recipeId).nutrition[field]
      if (!number(value)) return [key,null]
      total+=value*portion.amount/100
    }
    return [key,Math.round(total*10)/10]
  }))
}

// Validate the backend contract; never parse amounts out of generated prose.
export function normalizeMealResult(value, input) {
  if (!value || !['passed', 'needs_info', 'conflict'].includes(value.status) || !value.generationId || value.date !== input.date || value.meal !== input.meal) invalid('状态、日期、餐次或生成版本')
  if (!Array.isArray(value.issues) || value.issues.some(issue => !['needs_info', 'conflict', 'ingredient_conflict'].includes(issue.type) || !issue.message?.trim())) invalid('检查结果')
  if (value.status !== 'passed' && !value.issues.length) invalid('缺少具体问题')
  const members = input.members
  const local = unresolvedHealth(members).map(message => ({ type: /矛盾/.test(message) ? 'conflict' : 'needs_info', message }))
  const issues = [...value.issues, ...local]
  if (value.status !== 'passed') return { ...value, members, count: members.length, sourceType: 'api', dishes: [], products: [], steps: [], memberNotes: [], memberDemands: [], nutrition: null, blocked: issues.map(issue => issue.message), safetyText: issues[0]?.message, general: true }
  if (!Array.isArray(value.dishes) || !Array.isArray(value.products) || !Array.isArray(value.memberDemands) || !Array.isArray(value.memberNotes)) invalid('菜单与逐人需求')
  if (!strings(value.steps) || (value.dishes.length && !value.steps.length)) invalid('做法')
  const ids = members.map(member => member.id)
  for (const field of ['memberDemands', 'memberNotes']) {
    const actual = value[field].map(item => field === 'memberNotes' ? item.id : item.memberId)
    if (actual.length !== ids.length || new Set(actual).size !== ids.length || ids.some(id => !actual.includes(id))) invalid('成员归属')
  }
  const productIds = new Set(value.products.map(product => product.id))
  if (productIds.size !== value.products.length) invalid('重复商品')
  for (const product of value.products) {
    if (product.id == null || !product.name?.trim() || !product.unit?.trim() || !number(product.pack) || product.pack === 0 || !Number.isSafeInteger(product.priceCents) || product.priceCents < 0 || !strings(product.ingredients) || !product.ingredients.length) invalid('商品与全部配料')
  }
  for (const demand of value.memberDemands) {
    if (!Array.isArray(demand.ingredients) || !demand.sourceReference) invalid('成员需求依据')
    for (const item of demand.ingredients) {
      const product = value.products.find(product => product.id === item.productId)
      if (!product || !number(item.amount) || item.unit !== product.unit) invalid('食材用量与单位')
    }
  }
  const dishes = value.dishes.map(dish => {
    if (!dish.name?.trim() || !dish.recipeId || !dish.recipeVersion || !strings(dish.ingredients) || !dish.ingredients.length || !strings(dish.steps) || !dish.steps.length) invalid('菜谱、配料与做法依据')
    const nutrition=dish.nutrition?.source==='demo'||!dish.nutrition?.sourceReference?null:dish.nutrition
    return { ...dish, detail: dish.detail || dish.ingredients.join(' · '), nutrition: normalizeDishNutrition(nutrition) }
  })
  for (const note of value.memberNotes) {
    if (!Array.isArray(note.dishes) || !strings(note.notes || []) || typeof note.portion !== 'string') invalid('个人建议')
    if (!note.dishes.length && !note.portion.trim()) invalid('缺少个人吃法说明')
    if(new Set(note.dishes.map(portion=>portion.recipeId)).size!==note.dishes.length)invalid('重复个人菜品')
    for (const portion of note.dishes) {
      if (!dishes.some(dish => dish.recipeId === portion.recipeId && dish.recipeVersion === portion.recipeVersion) || !number(portion.amount) || portion.unit !== 'g' || portion.foodState !== 'cooked_edible' || !portion.sourceReference) invalid('个人份量与熟重依据')
    }
  }
  const conflicts = ingredientConflicts(members, [...dishes.flatMap(dish => dish.ingredients), ...value.products.flatMap(product => product.ingredients)])
  issues.push(...conflicts.map(message => ({ type: 'ingredient_conflict', message })))
  return { ...value, members, count: members.length, dishes, products: productsFromDemands(value.products, value.memberDemands), sourceType: 'api', issues,
    memberNotes: value.memberNotes.map(note => ({ ...note, name: members.find(member => member.id === note.id).name, notes: [...memberNotes(members.find(member => member.id === note.id)), ...(note.notes || [])] })),
    // Meal totals need their own validated basis. Per-100g recipe values are not totals.
    nutrition: mealNutrition(dishes,value.memberNotes), blocked: issues.map(issue => issue.message), general: false,
    safetyText: issues.length ? '本餐有待处理的饮食问题' : '已完成本餐已知信息检查' }
}
