const SWAP_KEY = 'meal-dish-swaps-v1'
import { ingredientConflicts } from './health.js'

export const DINNER_FISH_SWAPS = [
  {
    id: 'tomato-fish',
    sourceDish: '清蒸鲈鱼',
    name: '番茄炖鲈鱼',
    icon: '🐟',
    color: '#f4ddd0',
    direction: '同主食材换做法',
    nutrition: '高蛋白、低油，结构接近',
    reuseRate: 85,
    minutes: 20,
    kcal: 195,
    kcalDelta: 15,
    ingredientNote: '继续使用鲈鱼，并复用菜单中已有番茄',
    shoppingChange: '无需新增食材，购物清单保持不变',
  },
  {
    id: 'seared-fish',
    sourceDish: '清蒸鲈鱼',
    name: '香煎鲈鱼',
    icon: '🐟',
    color: '#eee2c9',
    direction: '同主食材换做法',
    nutrition: '蛋白质接近，烹调油略有增加',
    reuseRate: 92,
    minutes: 16,
    kcal: 225,
    kcalDelta: 45,
    ingredientNote: '继续使用鲈鱼和现有蔬菜，烹调方式改为少油香煎',
    shoppingChange: '无需新增食材，购物清单保持不变',
  },
  {
    id: 'shrimp-tofu',
    sourceDish: '清蒸鲈鱼',
    name: '豆腐蒸虾仁',
    icon: '🦐',
    color: '#e5eee2',
    direction: '同营养结构换食材',
    nutrition: '优质蛋白结构接近，口味清淡',
    reuseRate: 62,
    minutes: 18,
    kcal: 175,
    kcalDelta: -5,
    ingredientNote: '保留嫩豆腐，将鲈鱼替换为虾仁',
    shoppingChange: '购物清单删除鲜鲈鱼，新增鲜虾仁',
  },
]

function readSwaps() {
  if (typeof uni === 'undefined') return {}
  return uni.getStorageSync(SWAP_KEY) || {}
}

function writeSwaps(swaps) {
  if (typeof uni !== 'undefined') uni.setStorageSync(SWAP_KEY, JSON.parse(JSON.stringify(swaps)))
}

export function getDishSwapOptions(meal, dishName, members = []) {
  return meal === '晚餐' && (dishName === '清蒸鲈鱼' || DINNER_FISH_SWAPS.some(s=>s.name===dishName)) ? DINNER_FISH_SWAPS.filter(s=>s.name!==dishName&&!ingredientConflicts(members,s.name+(s.id==='tomato-fish'?'番茄':'')+' 姜葱').length).slice(0,3) : []
}

const dateKey = meal => `${new Date().toLocaleDateString('sv-SE')}:${meal}`
export function getMealSwap(meal) { return readSwaps()[dateKey(meal)] || null }

export function saveMealSwap(meal, option) {
  const swaps = readSwaps()
  swaps[dateKey(meal)] = { id: option.id, sourceDish: option.sourceDish, updatedAt: new Date().toISOString() }
  writeSwaps(swaps)
  return swaps[dateKey(meal)]
}

export function clearMealSwap(meal) {
  const swaps = readSwaps()
  delete swaps[dateKey(meal)]
  writeSwaps(swaps)
}

export function clearMealSwaps() { writeSwaps({}) }

export function applyMealCustomization(plan, swap = null) {
  if (!swap || plan.meal !== '晚餐') return plan
  const option = DINNER_FISH_SWAPS.find(item => item.id === swap.id)
  if (!option || !plan.dishes.some(dish => dish.name === option.sourceDish)) return plan

  const next = {
    ...plan,
    dishes: plan.dishes.map(dish => dish.name === option.sourceDish ? {
      ...dish,
      icon: option.icon,
      name: option.name,
      color: option.color,
      kcal: option.kcal,
      detail: option.id === 'tomato-fish'
        ? `鲈鱼 ${150 * plan.count}g · 番茄 ${100 * plan.count}g · 少油慢炖`
        : option.id === 'seared-fish'
          ? `鲈鱼 ${150 * plan.count}g · 少油煎熟 · 蘸汁分开`
          : `虾仁 ${120 * plan.count}g · 嫩豆腐 ${100 * plan.count}g · 清蒸`,
    } : dish),
    products: plan.products.map(product => ({ ...product })),
    steps: [...plan.steps],
    swap: { ...swap, ...option },
  }

  if (option.id === 'tomato-fish') {
    const tomato=next.products.find(p=>p.id===4)
    if(tomato){tomato.need+=100*plan.count;tomato.quantity=Math.ceil(tomato.need/tomato.pack)}
    next.steps = ['先煮杂粮饭，再处理鲈鱼和番茄。', '番茄炒软后加入少量清水，放入鲈鱼炖至熟透。', '同时炒香菇青菜并煮番茄豆腐汤。', '调味和蘸汁分开放，按实际食量分餐。']
  } else if (option.id === 'seared-fish') {
    next.steps = ['先煮杂粮饭，再把鲈鱼吸干表面水分。', '锅中放少量油，将鲈鱼两面煎至熟透。', '同时炒香菇青菜并煮番茄豆腐汤。', '蘸汁分开放，按实际食量分餐。']
  } else {
    next.products = next.products.filter(product => product.id !== 1)
    next.products.push({ id: 7, icon: '🦐', name: '鲜虾仁', perPerson: 120, unit: 'g', pack: 400, priceCents: 3590, need: 120 * plan.count, quantity: Math.ceil(120 * plan.count / 400) })
    const tofu=next.products.find(p=>p.id===5)
    if(tofu){tofu.need+=100*plan.count;tofu.quantity=Math.ceil(tofu.need/tofu.pack)}
    next.steps = ['先煮杂粮饭，再把虾仁和嫩豆腐装盘。', '水沸后蒸豆腐虾仁，直至虾仁完全熟透。', '同时炒香菇青菜并煮番茄豆腐汤。', '调味和蘸汁分开放，按实际食量分餐。']
  }
  if(next.nutrition)next.nutrition={...next.nutrition,kcal:next.dishes.reduce((sum,d)=>sum+d.kcal,0)*next.count,fat:next.nutrition.fat+(option.id==='seared-fish'?5*next.count:0)}
  return next
}

