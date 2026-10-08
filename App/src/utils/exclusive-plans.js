import { bundleImage as planImage } from './meal-bundles.js'
import { createPlan } from './demo.js'
import { getProfile } from './profile.js'

export const EXCLUSIVE_PLANS = [
  {
    id: 'balanced', name: '家庭均衡营养计划', subtitle: '荤素科学搭配，营养全面均衡，全家安心享用',
    image: planImage('fish-veg'), estimateCents: 16800, totalEstimateCents: 168000, tag: '首选推荐',
    days: [
      { day: '周一', meals: [{ type: '早餐', name: '原味燕麦与水煮蛋', minutes: 15, image: planImage('oats') }, { type: '午餐', name: '番茄炒蛋与杂粮饭', minutes: 28, image: planImage('tomato-tofu') }, { type: '晚餐', name: '清蒸鲈鱼与香菇青菜', minutes: 35, image: planImage('fish-veg') }] },
      { day: '周二', meals: [{ type: '早餐', name: '鸡蛋黄瓜全麦搭配', minutes: 12, image: planImage('eggs') }, { type: '午餐', name: '香菇青菜与豆腐', minutes: 25, image: planImage('fish-veg') }, { type: '晚餐', name: '番茄豆腐汤与杂粮饭', minutes: 30, image: planImage('tomato-tofu') }] },
    ],
    products: [{ name: '清蒸鲈鱼鲜蔬包', count: '3 份', cents: 4860, image: planImage('fish-veg') }, { name: '番茄豆腐鲜汤包', count: '3 份', cents: 1270, image: planImage('tomato-tofu') }, { name: '家庭杂粮主食包', count: '3 份', cents: 1290, image: planImage('grains') }],
    cookingSteps: ['先淘洗杂粮米并开始煮饭，清洗鲈鱼、上海青和香菇。', '水烧开后放入鲈鱼，蒸至鱼肉熟透。', '香菇与上海青炒熟，油盐按家庭口味少量添加。', '将鱼、蔬菜和杂粮饭分装，按实际食量用餐。'],
    allergens: [{ type: '含鱼类', items: '鲈鱼' }, { type: '含蛋', items: '鸡蛋' }, { type: '含大豆', items: '豆腐' }],
  },
  {
    id: 'fiber', name: '高纤轻食计划', subtitle: '围绕高纤蔬果与杂粮搭配，兼顾营养和家常口味',
    image: planImage('tomato-tofu'), estimateCents: 15800, totalEstimateCents: 158000, tag: '清爽家常',
    days: [
      { day: '周一', meals: [{ type: '早餐', name: '燕麦黄瓜早餐', minutes: 12, image: planImage('cucumber') }, { type: '午餐', name: '时蔬豆腐与杂粮饭', minutes: 24, image: planImage('grains') }, { type: '晚餐', name: '番茄豆腐汤与时蔬', minutes: 28, image: planImage('tomato-tofu') }] },
      { day: '周二', meals: [{ type: '早餐', name: '原味燕麦与鸡蛋', minutes: 15, image: planImage('oats') }, { type: '午餐', name: '番茄时蔬与黄瓜', minutes: 22, image: planImage('cucumber') }, { type: '晚餐', name: '香菇青菜与杂粮饭', minutes: 25, image: planImage('grains') }] },
    ],
    products: [{ name: '番茄豆腐鲜汤包', count: '3 份', cents: 1270, image: planImage('tomato-tofu') }, { name: '清爽黄瓜蔬果包', count: '3 份', cents: 590, image: planImage('cucumber') }, { name: '家庭杂粮主食包', count: '3 份', cents: 1290, image: planImage('grains') }],
    cookingSteps: ['清洗番茄和时蔬，豆腐切块备用。', '番茄煮软后加入豆腐，小火煮至热透。', '时蔬清炒至熟，少量调味。', '将汤和时蔬分装，按实际食量用餐。'],
    allergens: [{ type: '含蛋', items: '鸡蛋' }, { type: '含大豆', items: '豆腐' }],
  },
  {
    id: 'protein', name: '优质蛋白计划', subtitle: '优质蛋白与蔬菜组合，做法简单，适合家庭共享',
    image: planImage('eggs'), estimateCents: 17600, totalEstimateCents: 176000, tag: '省心搭配',
    days: [
      { day: '周一', meals: [{ type: '早餐', name: '水煮蛋与清爽黄瓜', minutes: 10, image: planImage('eggs') }, { type: '午餐', name: '鸡蛋豆腐与时蔬', minutes: 25, image: planImage('eggs') }, { type: '晚餐', name: '清蒸鲈鱼与豆腐汤', minutes: 35, image: planImage('fish-veg') }] },
      { day: '周二', meals: [{ type: '早餐', name: '鸡蛋燕麦早餐', minutes: 15, image: planImage('oats') }, { type: '午餐', name: '清蒸鲈鱼与杂粮饭', minutes: 30, image: planImage('fish-veg') }, { type: '晚餐', name: '香菇青菜与杂粮饭', minutes: 28, image: planImage('grains') }] },
    ],
    products: [{ name: '鲜鸡蛋蛋白搭配包', count: '3 份', cents: 990, image: planImage('eggs') }, { name: '清蒸鲈鱼鲜蔬包', count: '3 份', cents: 4860, image: planImage('fish-veg') }, { name: '番茄豆腐鲜汤包', count: '3 份', cents: 1270, image: planImage('tomato-tofu') }],
    cookingSteps: ['清洗鲈鱼、番茄并将豆腐切块。', '水烧开后蒸鲈鱼，确保鱼肉完全熟透。', '番茄煮软后加入豆腐，小火煮至热透。', '将鱼和豆腐汤按家庭成员实际食量分装。'],
    allergens: [{ type: '含鱼类', items: '鲈鱼' }, { type: '含蛋', items: '鸡蛋' }, { type: '含大豆', items: '豆腐' }],
  },
]

export function getExclusivePlan(id) { return EXCLUSIVE_PLANS.find(plan => plan.id === id) || EXCLUSIVE_PLANS[0] }
export function adaptExclusivePlan(template, profile=getProfile()) {
  const tier={balanced:'标准型',fiber:'经济型',protein:'品质型'}[template.id]
  const regeneration=uni.getStorageSync('exclusive-generation')||0
  const variants=[0,1].map(day=>['早餐','午餐','晚餐'].map(meal=>{
    const plan=createPlan(profile,meal)
    if((day+regeneration)%2===1) plan.dishes=plan.dishes.map(d=>d.name==='香菇青菜'?{...d,name:'清炒上海青',detail:d.detail.replace(/ · 香菇 \d+g/,'')}:d)
    if((day+regeneration)%2===1)plan.products=plan.products.filter(p=>p.id!==3)
    if(template.id==='fiber'&&meal==='午餐'&&!plan.blocked.length){plan.dishes=plan.dishes.filter(d=>d.name!=='番茄炒蛋');plan.products=plan.products.filter(p=>p.id!==12);plan.nutrition=null}
    if(template.id==='protein'&&meal==='晚餐'&&!plan.blocked.length&&plan.dishes.some(d=>d.name==='清蒸鲈鱼')){plan.dishes=plan.dishes.map(d=>d.name==='清蒸鲈鱼'?{...d,name:'番茄炖鲈鱼',detail:d.detail.replace('姜葱蒸熟','番茄炖熟')}:d);const tomato=plan.products.find(p=>p.id===4);if(tomato){tomato.need+=100*plan.count;tomato.quantity=Math.ceil(tomato.need/tomato.pack)}}
    return plan
  }))
  const blocked=[...new Set(variants.flatMap(day=>day.flatMap(p=>p.blocked)))]
  const days=variants.map((plans,i)=>({day:'第 '+(i+1)+' 天',meals:plans.map(p=>({type:p.meal,name:p.dishes.map(d=>d.name).join('与'),minutes:p.minutes,image:planImage(p.meal==='早餐'?'oats':'fish-veg')}))}))
  const totals=new Map()
  variants[0].flatMap(p=>p.products).forEach(p=>{const existing=totals.get(p.id);if(existing)existing.need+=p.need;else totals.set(p.id,{...p})})
  const specs={fiber:'家庭基础规格',balanced:'常规精选规格',protein:'品质精选规格'}[template.id]
  const products=[...totals.values()].map(p=>({name:p.name,count:Math.ceil(p.need/p.pack)+' 包 · '+p.pack+p.unit,cents:p.priceCents*Math.ceil(p.need/p.pack),image:template.image}))
  return {...template,name:tier,tag:tier,subtitle:specs+' · '+(regeneration?'更新后的':'')+'21 天三餐方案',days,products,fixturePlans:variants,blocked,specs,generation:regeneration}
}
export function regenerateExclusivePlans(){uni.setStorageSync('exclusive-generation',(uni.getStorageSync('exclusive-generation')||0)+1)}

function isoDate(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function defaultPlanStartDate() {
  const date = new Date()
  date.setDate(date.getDate() + 2)
  return isoDate(date)
}

export function createDeliveryBatches(plan, startDate = defaultPlanStartDate(), count = 21) {
  const [year, month, day] = startDate.split('-').map(Number)
  const start = new Date(year, month - 1, day, 12)
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(start)
    date.setDate(start.getDate() + index)
    const template = plan.days[index % plan.days.length]
    return {
      index: index + 1,
      date: isoDate(date),
      label: `${date.getMonth() + 1}月${date.getDate()}日`,
      dishes: template.meals.map(meal => meal.name),
      meals: template.meals.map(meal => ({ ...meal })),
    }
  })
}
