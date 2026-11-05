import { chatFoodCovers } from '../data/chat-food-covers.js'
import { recipeCovers } from '../data/recipe-covers.js'

/** 只匹配首个食物的确切名称或已列明的别名，不从后面的菜借图。 */
export function chatFoodCover(firstDish) {
  const text = String(firstDish || '').trim()
  // “燕麦或全麦面包”仍取先提到的燕麦；括号内的替代说明不拆开。
  const first = text.match(/^([^（(]+?)(?:或者|或)/)?.[1] || text
  const name = first.trim()
    .replace(/^(?:主食|主菜|蛋白质|蔬菜|水果|奶类)\s*[:：]\s*/, '')
    .replace(/[（(][^）)]*(?:克|毫升|份|碗|杯|个|片|g\b|ml\b)[^）)]*[）)]\s*$/i, '')
    .replace(/\s*(?:\d+(?:\.\d+)?|[一二两三四五六七八九十半]+)\s*(?:小|中|大)?(?:g|克|ml|毫升|份|碗|杯|个|片)\s*$/i, '').trim()
  const local = chatFoodCovers.find(cover => cover.names.includes(name))
  if (local) return { src: local.image, label: name, generated: true }
  const recipe = recipeCovers.find(cover => cover.title === name)
  return recipe ? { src: recipe.image_url, label: name, generated: false } : null
}
