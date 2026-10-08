import { subtotal } from './demo.js'

export const bundleImage = name => `/static/bundles/${name}.png`

// Cards and the shop share the same product IDs and package-based totals.
export function createMealBundles(plan) {
  if (plan.blocked.length) return []
  const swappedFishBundle = plan.swap?.id === 'tomato-fish'
    ? { id: 'fish-veg', name: '番茄炖鲈鱼鲜蔬包', category: '荤素搭配', description: '鲈鱼 + 番茄 + 上海青', image: 'fish-veg', productIds: [1, 2, 4] }
    : plan.swap?.id === 'seared-fish'
      ? { id: 'fish-veg', name: '香煎鲈鱼鲜蔬包', category: '荤素搭配', description: '鲈鱼 + 上海青 + 香菇', image: 'fish-veg', productIds: [1, 2, 3] }
      : plan.swap?.id === 'shrimp-tofu'
        ? { id: 'fish-veg', name: '豆腐蒸虾仁鲜蔬包', category: '荤素搭配', description: '虾仁 + 嫩豆腐 + 上海青', image: 'fish-veg', productIds: [7, 5, 2] }
        : { id: 'fish-veg', name: '清蒸鲈鱼鲜蔬包', category: '荤素搭配', description: '鲈鱼 + 上海青 + 香菇', image: 'fish-veg', productIds: [1, 2, 3] }
  const definitions = plan.meal === '早餐' ? [
    { id: 'oats', name: '原味燕麦早餐包', category: '谷物主食', description: '原味燕麦 · 轻松煮粥', image: 'oats', productIds: [11] },
    { id: 'eggs', name: '鲜鸡蛋蛋白搭配包', category: '蛋白搭配', description: '水煮蛋 · 早餐搭配', image: 'eggs', productIds: [12] },
    { id: 'cucumber', name: '清爽黄瓜蔬果包', category: '蔬果', description: '清洗切片 · 清爽加餐', image: 'cucumber', productIds: [13] },
  ] : plan.meal === '午餐' ? [
    { id: 'tomato-eggs', name: '番茄鸡蛋午餐包', category: '蛋白搭配', description: '番茄 + 鸡蛋', image: 'eggs', productIds: [4, 12] },
    { id: 'greens-tofu', name: '青菜香菇豆腐包', category: '荤素搭配', description: '上海青 + 香菇 + 嫩豆腐', image: 'tomato-tofu', productIds: [2, 3, 5] },
    { id: 'grains', name: '家庭杂粮主食包', category: '谷物主食', description: '杂粮米 · 共享一餐', image: 'grains', productIds: [6] },
  ] : [
    swappedFishBundle,
    { id: 'tomato-tofu', name: '番茄豆腐鲜汤包', category: '汤料', description: '番茄 + 嫩豆腐', image: 'tomato-tofu', productIds: [4, 5] },
    { id: 'grains', name: '家庭杂粮主食包', category: '谷物主食', description: '杂粮米 · 共享一餐', image: 'grains', productIds: [6] },
  ]
  const mapped = definitions.map(bundle=>{
    const ids=bundle.productIds.map(id=>plan.products.some(p=>p.id===id)?id:id===1||id===12?20:id===5?21:id===11?22:id).filter(id=>plan.products.some(p=>p.id===id))
    if(!ids.length)return null
    const changed=ids.join(',')!==bundle.productIds.join(',')
    return {...bundle,productIds:[...new Set(ids)],...(changed?{name:plan.products.filter(p=>ids.includes(p.id)).map(p=>p.name).join('与')+'搭配包',description:'已按成员限制调整的示例食材包'}:{})}
  }).filter(Boolean)
  return mapped.map(bundle => ({
    ...bundle,
    image: bundleImage(bundle.image),
    priceCents: subtotal(plan.products, bundle.productIds),
    spec: plan.products.filter(p => bundle.productIds.includes(p.id)).map(p => `${p.pack}${p.unit}×${p.quantity}`).join(' / '),
    count: plan.count,
  }))
}
