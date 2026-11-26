import { mealDay, mealLabels } from './cloud-meals.js'
import { newHealthRequestId } from './health-request-id.js'

export const journalMealLabels = { ...mealLabels, unknown: '未注明' }
export const coarsePortions = ['少量', '一般', '较多', '不确定']
const clone = value => JSON.parse(JSON.stringify(value))

export function journalWeek(day) {
  const date = new Date(day + 'T12:00:00+08:00')
  const mondayOffset = (date.getUTCDay() + 6) % 7
  return Array.from({ length: 7 }, (_, index) => {
    const value = mealDay(new Date(date.getTime() + (index - mondayOffset) * 86400000).toISOString())
    return { date: value, number: Number(value.slice(8)), label: ['一', '二', '三', '四', '五', '六', '日'][index] }
  })
}

export function coarsePortion(item) {
  return (item.uncertainties || []).find(value => value.startsWith('本人粗略份量：'))?.slice(7) || '不确定'
}

export function quantityText(item) {
  const quote = (item.uncertainties || []).find(value => value.startsWith('本人份量原文：'))?.slice(7)
  const parts = []
  if (quote && quote !== '未知') parts.push(quote)
  if (item.grams != null && item.share_ratio != null) parts.push(Number((Number(item.grams) * Number(item.share_ratio)).toFixed(2)) + ' g')
  const portion = coarsePortion(item)
  if (portion !== '不确定') parts.push(portion)
  return parts.join(' · ')
}

function foodLine(item) {
  const quote = (item.uncertainties || []).find(value => value.startsWith('本人份量原文：'))?.slice(7)
  return item.name + (quote && quote !== '未知' ? ' ' + quote : '')
}

export function createJournalDraft(record) {
  const meal = record.snapshot.meal
  const rows = meal.items.filter(item => !item.excluded).map(item => ({
    key: item.item_id, text: foodLine(item), original: clone(item),
    portion: coarsePortion(item),
    grams: item.grams != null && item.share_ratio != null ? Number(item.grams) * Number(item.share_ratio) : '',
  }))
  return { date: mealDay(meal.eaten_at), mealType: meal.meal_type, foodText: rows.map(row => row.text).join('\n'), rows }
}

export function syncJournalDraft(draft, newId = newHealthRequestId) {
  const available = [...draft.rows]
  draft.rows = draft.foodText.split('\n').map(line => line.trim()).filter(Boolean).map(text => {
    const index = available.findIndex(row => row.text === text)
    if (index >= 0) return available.splice(index, 1)[0]
    return { key: newId(), text, original: null, portion: '不确定', grams: '' }
  })
}

export function journalDraftMeal(record, draft) {
  if (!draft.rows.length || draft.rows.length > 30) throw new Error('请填写 1～30 行食物，每行一种。')
  const original = record.snapshot.meal
  const eaten = new Date(Date.parse(original.eaten_at) + 8 * 3600000).toISOString()
  const items = draft.rows.map(row => {
    if (!row.text || (!row.original && row.text.length > 120)) throw new Error('每行食物描述请保持在 120 字以内。')
    const grams = row.grams === '' || row.grams == null ? null : Number(row.grams)
    if (grams != null && (!Number.isFinite(grams) || grams <= 0 || grams > 10000)) throw new Error('实际克数请填写大于 0、且不超过 10000 的数字。')
    const item = row.original ? clone(row.original) : {
      item_id: row.key, name: row.text, locations: [], uncertainties: [],
      grams: null, share_ratio: null, portion_source: 'unknown', excluded: false,
    }
    item.uncertainties = [...(item.uncertainties || []).filter(value => !value.startsWith('本人粗略份量：')), '本人粗略份量：' + row.portion]
    const previous = row.original?.grams != null && row.original?.share_ratio != null ? Number(row.original.grams) * Number(row.original.share_ratio) : null
    if (grams !== previous) {
      item.uncertainties = item.uncertainties.filter(value => !/^本人份量原文：[\d.]+\s*(?:克|g|千克|公斤|kg)$/i.test(value))
      item.grams = grams
      item.share_ratio = grams == null ? null : 1
      item.portion_source = grams == null ? 'unknown' : 'manual'
      item.portion_reference_id = null
      item.portion_count = null
      item.servings = null
      // The referenced document may describe one serving with no gram conversion.
      item.nutrition_source = null
    }
    return item
  })
  return { ...clone(original), meal_type: draft.mealType, eaten_at: draft.date + eaten.slice(10, 19) + '+08:00', items }
}

export function recordSource(record) {
  if (record.snapshot.meal.photos?.length) return '拍照记餐'
  return record.snapshot.recording?.source === 'chat_actual_intake' ? '来自聊天' : '手动记餐'
}
