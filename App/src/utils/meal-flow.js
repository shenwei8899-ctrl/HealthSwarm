import { bundleImage } from './meal-bundles.js'

export const DAILY_MEALS = [
  { name: '早餐', route: 'breakfast' },
  { name: '午餐', route: 'lunch' },
  { name: '晚餐', route: 'dinner' },
]

export function mealFromRoute(route) {
  return DAILY_MEALS.find(meal => meal.route === route)?.name || '晚餐'
}

export function mealToRoute(name) {
  return DAILY_MEALS.find(meal => meal.name === name)?.route || 'dinner'
}

const dishRecipeTemplates = {
  清蒸鸡肉: {image:'eggs',minutes:20,steps:['鸡肉洗净切成均匀块状，生熟工具分开。','清水烧开后放入鸡肉蒸制，确认中心熟透。','调味另放，按本餐实际食量分餐。'],notes:['当前为替代菜谱演示，避免交叉接触已知过敏成分。']},
  番茄炖鸡肉: {image:'tomato-tofu',minutes:22,steps:['番茄洗净切块，鸡肉切块备用。','番茄煮软后加入鸡肉，小火炖熟。','确认鸡肉中心熟透后出锅，按需分餐。'],notes:['鸡肉必须完全熟透。']},
  清炖冬瓜: {image:'tomato-tofu',minutes:18,steps:['冬瓜去皮切块。','放入清水炖煮至熟。','少量调味后分餐。'],notes:['调味料与已知过敏成分分开。']},
  番茄冬瓜汤: {image:'tomato-tofu',minutes:18,steps:['番茄和冬瓜洗净切块。','番茄煮软后加入冬瓜炖熟。','调味另放，注意入口温度。'],notes:['汤品注意入口温度。']},
  小米粥: {image:'grains',minutes:20,steps:['小米淘洗后加入清水。','小火煮至软糯。','稍放凉，按需分碗。'],notes:['不额外添加糖。']},
  清炒上海青: {image:'fish-veg',minutes:10,steps:['上海青洗净切配。','少量油炒至熟透。','调味另放，按需分餐。'],notes:['生熟分开。']},
  原味燕麦粥: { image: 'oats', minutes: 12, steps: ['燕麦淘洗后与清水一同入锅。', '中小火煮至燕麦软糯，期间搅拌防止粘锅。', '关火后稍放凉，按实际食量分碗。'], notes: ['不额外加糖；儿童及吞咽困难者需调整稠度。'] },
  水煮蛋: { image: 'eggs', minutes: 10, steps: ['鸡蛋洗净，冷水下锅。', '水沸后继续煮至蛋黄完全凝固。', '捞出稍放凉后剥壳，按人数分装。'], notes: ['确保蛋白和蛋黄熟透；已知鸡蛋过敏者不得食用。'] },
  清爽黄瓜: { image: 'cucumber', minutes: 6, steps: ['黄瓜用流动水充分洗净。', '切成适合入口的薄片或小段。', '可直接食用，调味汁另放。'], notes: ['生食蔬菜注意清洁；不使用来源不明的凉拌汁。'] },
  番茄炒蛋: { image: 'eggs', minutes: 15, steps: ['番茄洗净切块，鸡蛋打散。', '鸡蛋炒至凝固后盛出，再将番茄炒软。', '鸡蛋回锅混合，少量调味后出锅。'], notes: ['鸡蛋需熟透；控盐人群减少额外调味。'] },
  香菇青菜: { image: 'fish-veg', minutes: 12, steps: ['青菜与香菇分别洗净切配。', '先将香菇炒至出香，再加入青菜。', '翻炒至全部熟透，少量调味。'], notes: ['香菇与青菜需彻底清洗；避免长时间加热导致口感过软。'] },
  清炖豆腐: { image: 'tomato-tofu', minutes: 15, steps: ['豆腐切成大小均匀的小块。', '锅中加水煮开，放入豆腐小火炖煮。', '确认中心热透后少量调味。'], notes: ['大豆过敏者不得食用；翻动时避免将豆腐弄碎。'] },
  番茄豆腐汤: { image: 'tomato-tofu', minutes: 18, steps: ['番茄洗净切块，豆腐切块备用。', '番茄煮软出汤后加入豆腐。', '小火煮至豆腐中心热透，少量调味。'], notes: ['大豆过敏者不得食用；汤品注意入口温度。'] },
  杂粮饭: { image: 'grains', minutes: 35, steps: ['杂粮米淘洗干净，按包装建议浸泡。', '按米水比例放入电饭煲并启动煮饭。', '煮熟后焖几分钟，再按实际食量盛饭。'], notes: ['份量应结合本餐就餐者实际需要；不要把测试份量当作医嘱。'] },
  清蒸鲈鱼: { image: 'fish-veg', minutes: 20, steps: ['鲈鱼处理并冲洗干净，放入姜葱。', '水沸后上锅蒸制，按鱼的大小调整时间。', '确认鱼肉完全熟透后取出，调味汁另放。'], notes: ['鱼类过敏者不得食用；注意去除鱼刺并确保鱼肉熟透。'] },
  番茄炖鲈鱼: { image: 'fish-veg', minutes: 25, steps: ['鲈鱼处理干净并切段，番茄切块。', '番茄先煮软，再加入鲈鱼小火炖煮。', '确认鱼肉熟透后少量调味。'], notes: ['鱼类过敏者不得食用；翻动时注意鱼刺。'] },
  香煎鲈鱼: { image: 'fish-veg', minutes: 18, steps: ['鲈鱼处理干净并吸干表面水分。', '少量油将两面煎至定型。', '继续加热至鱼肉完全熟透后出锅。'], notes: ['鱼类过敏者不得食用；控制用油并注意鱼刺。'] },
  豆腐蒸虾仁: { image: 'tomato-tofu', minutes: 18, steps: ['豆腐切片铺盘，虾仁清洗备用。', '虾仁放在豆腐上，水沸后上锅蒸。', '确认虾仁和豆腐均热透后出锅。'], notes: ['甲壳类或大豆过敏者不得食用；虾仁必须熟透。'] },
}

export function createDishGuide(plan, dishName) {
  const dish = plan.dishes.find(item => item.name === dishName) || plan.dishes[0] || { name: dishName, detail: '所需食材按本餐清单准备', icon: '菜' }
  const template = dishRecipeTemplates[dish.name] || { image: plan.meal === '早餐' ? 'oats' : plan.meal === '午餐' ? 'tomato-tofu' : 'fish-veg', minutes: Math.max(10, Math.round((plan.minutes || 20) / Math.max(1, plan.dishes.length))), steps: ['按本餐清单清洗并备齐食材。', '根据食材特性烹调至完全熟透。', '少量调味后按实际食量分餐。'], notes: ['当前为测试做法，正式做法需由营养与菜谱团队审核。'] }
  return {
    name: dish.name,
    icon: dish.icon,
    image: ['清蒸鸡肉','番茄炖鸡肉','清炖冬瓜','番茄冬瓜汤','小米粥'].includes(dish.name)?instructionImage(2,'',dish.name):bundleImage(template.image),
    minutes: template.minutes,
    ingredients: String(dish.detail || '所需食材按本餐清单准备').split(' · '),
    steps: [...template.steps],
    stepImages: template.steps.map((step,index)=>instructionImage(index,step,dish.name)),
    notes: [...template.notes],
    videoUrl: '',
  }
}

const exclusiveSteps = {
  '原味燕麦与水煮蛋': ['燕麦加水煮至软糯，同时把鸡蛋煮至全熟。', '鸡蛋稍放凉后剥壳，燕麦粥按人数分碗。', '按实际食量用餐。'],
  '鸡蛋黄瓜全麦搭配': ['把鸡蛋煮至全熟，黄瓜洗净切片。', '全麦主食按包装说明准备好。', '鸡蛋、黄瓜和主食分装，按实际食量用餐。'],
  '番茄豆腐汤与杂粮饭': ['先淘洗杂粮米并开始煮饭。', '番茄洗净切块，豆腐切块后一同煮至热透。', '汤和杂粮饭按人数分装，少量调味。'],
  '燕麦黄瓜早餐': ['燕麦加水煮熟，黄瓜洗净切片。', '将燕麦粥与黄瓜分别分装。', '按实际食量用餐。'],
  '番茄豆腐汤与时蔬': ['番茄洗净切块，豆腐切块备用。', '番茄煮软后加入豆腐，小火煮至热透。', '时蔬清洗后炒熟，与汤一起分装。'],
  '原味燕麦与鸡蛋': ['燕麦加水煮至软糯，同时把鸡蛋煮至全熟。', '将燕麦粥与鸡蛋按人数分装。', '按实际食量用餐。'],
  '香菇青菜与杂粮饭': ['先淘洗杂粮米并开始煮饭。', '清洗香菇和青菜，切配后炒至熟透。', '青菜和杂粮饭按人数分装，少量调味。'],
  '水煮蛋与清爽黄瓜': ['把鸡蛋煮至全熟，黄瓜洗净切片。', '鸡蛋稍放凉后剥壳，与黄瓜分别分装。', '按实际食量用餐。'],
  '清蒸鲈鱼与豆腐汤': ['清洗鲈鱼，将豆腐切块备用。', '水烧开后蒸鲈鱼，确保鱼肉完全熟透。', '豆腐加水小火煮至热透，与鱼按人数分装。'],
  '鸡蛋燕麦早餐': ['燕麦加水煮至软糯，同时把鸡蛋煮至全熟。', '燕麦粥和鸡蛋按人数分装。', '按实际食量用餐。'],
}

export function createCookingGuide(plan, exclusivePlan = null, { batchIndex = 1, meal = '晚餐' } = {}) {
  if(exclusivePlan?.fixturePlans){const day=exclusivePlan.fixturePlans[(batchIndex-1)%exclusivePlan.fixturePlans.length];return createCookingGuide(day.find(p=>p.meal===meal)||day[0])}
  if (exclusivePlan) {
    const day = exclusivePlan.days[(batchIndex - 1) % exclusivePlan.days.length]
    const selectedMeal = day.meals.find(item => item.type === meal) || day.meals[0]
    const steps = batchIndex === 1 && selectedMeal.type === '晚餐'
      ? exclusivePlan.cookingSteps
      : exclusiveSteps[selectedMeal.name]
    const dishes = selectedMeal.name.split('与')
    const mockPlan = { meal: selectedMeal.type, minutes: selectedMeal.minutes, dishes: dishes.map(name => ({ name, detail: '所需食材按计划清单准备', icon: '菜' })) }
    return {
      meal: selectedMeal.type, title: selectedMeal.name, minutes: selectedMeal.minutes,
      dishes, steps: [...(steps || ['清洗并备齐这一餐的食材。', '按食材包装和家庭习惯烹调至熟透。', '按实际食量分餐。'])],
      dishGuides: dishes.map(name => createDishGuide(mockPlan, name)), image: selectedMeal.image, videoUrl: '',
    }
  }
  return {
    meal: plan.meal, title: `${plan.meal}烹饪指引`, minutes: plan.minutes,
    memberIds: (plan.members||[]).map(m=>m.id), recipeVersion:'演示图文菜谱 v2',
    dishes: plan.dishes.map(dish => dish.name), steps: [...plan.steps],
    dishGuides: plan.dishes.map(dish => createDishGuide(plan, dish.name)), image: '', videoUrl: '',
  }
}

// Offline instructional diagrams: no external image downloads or fake AI food photographs.
export function instructionImage(index,step,name=''){
  const escaped=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]))
  const drawings=[
    '<path d="M75 180h330v18H75z" fill="#afc58a"/><path d="M160 105l110 15-35 28-105-8z" fill="#719566"/><path d="M335 78l-74 67" stroke="#365f4b" stroke-width="15"/><path d="M335 78l20-16" stroke="#bd8843" stroke-width="22"/>',
    '<path d="M130 125h220v35q-110 75-220 0z" fill="#315d4b"/><path d="M112 120h256" stroke="#bd8843" stroke-width="10"/><path d="M200 90q-20-20 0-40m40 40q-20-20 0-40m40 40q-20-20 0-40" stroke="#9db18c" fill="none" stroke-width="7"/><path d="M188 195l15-18 17 18 17-18 17 18" stroke="#b36944" fill="none" stroke-width="6"/>',
    '<ellipse cx="240" cy="150" rx="132" ry="56" fill="#fffdf4" stroke="#a8bd91" stroke-width="8"/><ellipse cx="240" cy="150" rx="88" ry="34" fill="#d5e3b5"/><path d="M200 150l35 12 48-36" fill="none" stroke="#315d4b" stroke-width="9"/>'
  ]
  return 'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="480" height="270" viewBox="0 0 480 270"><rect width="480" height="270" rx="24" fill="#edf1df"/><text x="28" y="35" fill="#315d4b" font-size="16">${escaped(name)} · 步骤 ${index+1} 示意</text>${drawings[Math.min(index,2)]}<text x="240" y="244" text-anchor="middle" fill="#647862" font-size="15">${['食材准备','烹调加热','分餐装盘'][Math.min(index,2)]} · 配合文字操作</text></svg>`)
}
