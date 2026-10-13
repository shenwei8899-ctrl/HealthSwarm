// Units are ingredient units. These helpers never infer nutrition from age.
export function fixtureDemands(members, ingredients) {
  return members.map(member => ({
    memberId: member.id,
    source: 'demo',
    ingredients: ingredients.map(product => ({ productId: product.id, amount: product.perPerson, unit: product.unit })),
  }))
}

export function demandTotal(demands, productId, unit) {
  return demands.flatMap(member => member.ingredients || []).filter(item => item.productId === productId && item.unit === unit).reduce((sum, item) => sum + item.amount, 0)
}

export function productsFromDemands(products, demands) {
  return products.map(product => {
    const need = demandTotal(demands, product.id, product.unit)
    return { ...product, need, quantity: Math.ceil(need / product.pack) }
  }).filter(product => product.need > 0)
}

export function addFixtureDemand(plan, product) {
  const demands = plan.memberDemands || fixtureDemands(plan.members || [], plan.products)
  plan.memberDemands = demands.map(member => member.participates === false ? member : ({ ...member, ingredients: [...member.ingredients, { productId: product.id, amount: product.perPerson, unit: product.unit }] }))
  const existing = plan.products.find(item => item.id === product.id)
  if (!existing) plan.products.push({ ...product })
  plan.products = productsFromDemands(plan.products, plan.memberDemands)
  return demandTotal(plan.memberDemands, product.id, product.unit)
}

export function removeDemandProducts(plan, ids) {
  plan.memberDemands = (plan.memberDemands || []).map(member => ({ ...member, ingredients: member.ingredients.filter(item => !ids.includes(item.productId)) }))
  plan.products = plan.products.filter(product => !ids.includes(product.id))
}
