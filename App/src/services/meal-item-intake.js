import { newHealthRequestId } from './health-request-id.js'
export const itemPortions = ['少量', '一般', '较多', '不确定']
const copy = value => JSON.parse(JSON.stringify(value))
export function ensureMealItemIds(dishes, newId = newHealthRequestId) {
  for (const dish of dishes) dish.item_id ||= newId()
}
export function intakeRows(person, dishes, useDishAmounts = false) {
  return dishes.map(dish => {
    const stored = person.itemIntakes?.[dish.item_id]
    const selected = stored ? stored.selected : (person.dishes || []).includes(dish.name)
    const singleLegacy = !person.itemIntakes && person.dishes?.length === 1
    const known = useDishAmounts && dish.portion_confirmed
    return { itemId: dish.item_id, name: dish.name, selected: !person.noneConfirmed && !!selected,
      portion: stored?.portion || (singleLegacy && person.portion !== '不确定' ? person.portion : '') || (known ? dish.coarse_portion : '') || '不确定',
      grams: stored ? stored.grams : singleLegacy && String(person.grams ?? '').trim() ? person.grams : known && dish.grams != null ? dish.grams : '',
      originalGrams: stored ? stored.originalGrams : known && dish.grams != null ? dish.grams : '',
      originalAmount: stored ? copy(stored.originalAmount || null) : known ? copy(dish) : null }
  })
}
export function createCapturePortionDraft(people, dishes, useDishAmounts = false) {
  return people.map(person => ({ ...copy(person), rows: intakeRows(person, dishes, useDishAmounts),
    legacyTotal: !person.itemIntakes && person.dishes?.length > 1 ? person.grams || '' : '' }))
}
export function intakeGrams(value) {
  const text = String(value ?? '').trim()
  if (!text) return null
  if (!/^\d+(?:\.\d+)?$/.test(text) || !Number.isFinite(Number(text)) || Number(text) <= 0 || Number(text) > 10000) throw new Error('实际克数请填写大于 0、且不超过 10000 的数字，或留空。')
  return Number(text)
}
export function confirmCapturePortions(draft, dishes) {
  const available = new Set(dishes.map(dish => dish.item_id))
  return draft.map(person => {
    if (!person.noneConfirmed && !person.rows.some(row => row.selected && available.has(row.itemId))) throw new Error('请为每位成员勾选吃过的菜，或选择本餐未吃。')
    const itemIntakes = Object.create(null)
    for (const row of person.rows) {
      if (!available.has(row.itemId)) { if (row.selected) throw new Error('菜品已变化，请重新打开核对。'); continue }
      if (row.selected && !person.noneConfirmed) {
        intakeGrams(row.grams)
        if (!itemPortions.includes(row.portion)) throw new Error('请选择有效的粗略份量。')
      }
      itemIntakes[row.itemId] = { selected: !person.noneConfirmed && !!row.selected, portion: row.portion, grams: row.grams,
        originalGrams: row.originalGrams, originalAmount: row.originalAmount ? copy(row.originalAmount) : null }
    }
    const { rows, legacyTotal, ...base } = person
    return { ...base, itemIntakes, dishes: dishes.filter(dish => itemIntakes[dish.item_id]?.selected).map(dish => dish.name), portion: '不确定', grams: '' }
  })
}
export function selectedIntakeDishes(person, dishes) {
  return person.noneConfirmed ? [] : dishes.filter(dish => person.itemIntakes ? person.itemIntakes[dish.item_id]?.selected : person.dishes?.includes(dish.name))
}
export function captureIntakeSummary(person, dishes) {
  if (person.noneConfirmed) return '本餐未吃'
  if (!person.itemIntakes) return person.dishes?.length ? person.dishes.join(' · ') + ' · 待逐菜核对' : '选择吃过的菜'
  return selectedIntakeDishes(person, dishes).map(dish => {
    const row = person.itemIntakes[dish.item_id]
    return dish.name + (String(row.grams ?? '').trim() ? ' ' + row.grams + 'g' : row.portion !== '不确定' ? ' ' + row.portion : ' 份量待补充')
  }).join('；') || '选择吃过的菜'
}
export function applyPersonalItemAmount(item, dish, row) {
  const grams = intakeGrams(row.grams)
  const original = row.originalAmount
  const sameSource = original && ['food_id', 'recipe_version_id', 'source_basis'].every(key => original[key] === dish[key]) && JSON.stringify(original.nutrition_source || null) === JSON.stringify(dish.nutrition_source || null)
  const unchanged = sameSource && String(row.grams ?? '') === String(row.originalGrams ?? '')
  if (unchanged) {
    Object.assign(item, { grams: original.grams ?? null, servings: original.servings ?? null, share_ratio: 1,
      portion_reference_id: original.portion_reference_id || null, portion_count: original.portion_count ?? null,
      portion_source: original.portion_source || 'unknown', adjustments: copy(original.adjustments || []) })
  } else {
    Object.assign(item, { grams, share_ratio: grams == null ? null : 1, portion_source: grams == null ? 'unknown' : 'manual',
      servings: null, portion_reference_id: null, portion_count: null, adjustments: [] })
    if (dish.source_basis === 'per_serving') item.nutrition_source = null
  }
  item.uncertainties = (item.uncertainties || []).filter(value => !value.startsWith('本人粗略份量：') && !value.startsWith('本人所选菜品合计重量：'))
  item.uncertainties.push('本人粗略份量：' + row.portion, '本人逐菜核对：是')
  return item
}
