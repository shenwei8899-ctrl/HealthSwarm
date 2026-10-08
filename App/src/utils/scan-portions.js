export const portionOptions = ['少量', '一般', '较多', '不确定']
export const oilOptions = ['少油', '中等', '偏多', '不确定']

// Keep popup edits separate from the confirmed meal until the user applies them.
export function createPortionDraft(people, dishes, oil = '不确定') {
  return {
    oil,
    people: people.map(person => ({
      memberId: person.memberId,
      memberName: person.memberName,
      dishes: [...(person.dishes || [])].filter(dish => dishes.includes(dish)),
      portion: portionOptions.includes(person.portion) ? person.portion : '不确定',
      grams: person.grams == null ? '' : String(person.grams),
      noneConfirmed: Boolean(person.noneConfirmed),
    })),
  }
}

export function confirmPortionDraft(draft, dishes) {
  if (!oilOptions.includes(draft.oil)) throw new Error('请选择烹饪用油情况')
  const people = draft.people.map(person => {
    const selected = [...new Set(person.dishes)].filter(dish => dishes.includes(dish))
    if (!selected.length && !person.noneConfirmed) {
      throw new Error(`请确认${person.memberName}吃过的菜，或选择“未吃这些菜”`)
    }
    if (!portionOptions.includes(person.portion)) throw new Error('请选择粗略份量')
    const text = String(person.grams ?? '').trim()
    if (selected.length && text && (!/^\d+(\.\d+)?$/.test(text) || !Number.isFinite(Number(text)) || Number(text) <= 0)) {
      throw new Error(`${person.memberName}的克数需填写大于 0 的数字，也可以留空`)
    }
    return {
      memberId: person.memberId,
      memberName: person.memberName,
      dishes: selected,
      portion: selected.length ? person.portion : '不确定',
      grams: selected.length && text ? Number(text) : null,
      noneConfirmed: !selected.length && person.noneConfirmed,
    }
  })
  return { oil: draft.oil, people }
}

export function intakeSummary(person) {
  if (person.noneConfirmed && !(person.dishes || []).length) return '未吃这些菜'
  return `${person.portion || '不确定'}${person.grams ? ` · ${person.grams} g` : ''}`
}
