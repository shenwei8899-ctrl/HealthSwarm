import { DISH_NUTRITION_FIELDS, normalizeDishNutrition } from './dish-nutrition.js'

// Fixed UI fixtures only. These are neither a food composition database nor
// professionally calculated recipes. Never use them for nutrition advice.
const examples = {
  清蒸鲈鱼: [120, 20, 4, 1, null, 280],
  番茄炖鲈鱼: [125, 18, 4.5, 3, 0.5, 260],
  香煎鲈鱼: [150, 20, 7, 1.5, null, 300],
  豆腐蒸虾仁: [95, 13, 3.5, 3, 0.5, 220],
  原味燕麦粥: [55, 2, 1, 9.5, 1.5, 5],
  水煮蛋: [150, 13, 10, 2, 0, 130],
  清爽黄瓜: [16, 0.8, 0.2, 2.8, 0.5, 5],
  番茄炒蛋: [100, 5, 7, 4, 0.8, 240],
  香菇青菜: [45, 2, 2, 5, 2, 180],
  清炖豆腐: [70, 7, 3, 4, 0.5, 150],
  番茄豆腐汤: [35, 3, 1.5, 2.5, 0.5, 160],
  杂粮饭: [120, 3, 1, 25, 1.8, 5],
  清蒸鸡肉: [150, 26, 5, 0, 0, 180],
  番茄炖鸡肉: [110, 16, 4, 2.5, 0.6, 200],
  清炖冬瓜: [18, 0.5, 0.2, 3.5, 0.8, 100],
  番茄冬瓜汤: [20, 0.5, 0.2, 4, 0.8, 110],
  小米粥: [45, 1, 0.4, 9, 0.5, 5],
  清炒上海青: [40, 1.5, 2, 4, 1.5, 160],
}

export function demoDishNutrition(name) {
  if (!Object.prototype.hasOwnProperty.call(examples, name)) return normalizeDishNutrition(null)
  return normalizeDishNutrition({
    basis: 'per_100g', foodState: 'cooked_edible', source: 'demo', sourceReference: 'ui-fixture-v1',
    ...Object.fromEntries(DISH_NUTRITION_FIELDS.map(({ key }, index) => [key, examples[name][index]])),
  })
}
