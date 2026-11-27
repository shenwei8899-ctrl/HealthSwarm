import test from 'node:test'
import assert from 'node:assert/strict'
import { referenceNutritionOptions, referenceNutritionItems } from '../src/utils/reference-serving.js'
import { recipeIngredients } from '../src/utils/dish-commerce-presentation.js'

test('personal and whole-dish nutrition retain distinct bases and missing values', () => {
  const options = referenceNutritionOptions({ nutrition_total: { basis: 'whole_dish', energyKcal: 240 },
    member_servings: [{ member_id: 'a', name: '甲', nutrition: { basis: 'per_serving', energyKcal: 170, sodiumMg: 0 } }, { member_id: 'b', name: '乙' }] })
  assert.equal(referenceNutritionItems(options[1])[0].text, '240')
  const mine = referenceNutritionItems(options[2])
  assert.equal(mine[0].text, '170')
  assert.equal(mine.find(x => x.key === 'sodiumMg').text, '0')
  assert.equal(mine.find(x => x.key === 'proteinG').text, '暂未核算')
  assert.ok(referenceNutritionItems(options[3]).every(x => !x.available))
  assert.ok(referenceNutritionItems(referenceNutritionOptions({ nutrition_total: { basis: 'per_100g', energyKcal: 100 } })[1]).every(x => !x.available))
})

test('planned ingredient amounts do not overwrite source recipe or purchase quantity', () => {
  const dish = { name: '合成菜', ingredients: ['大米 100克', '水 适量'], steps: [],
    serving_suggestion: { ingredient_amounts: [{ position: 0, amount: 80, unit: '克' }] } }
  const rows = recipeIngredients(dish)
  assert.equal(rows[0].amount, '大米 100克（本餐建议 80克）')
  assert.equal(rows[1].amount, '水 适量')
  assert.deepEqual(dish.ingredients, ['大米 100克', '水 适量'])
})
