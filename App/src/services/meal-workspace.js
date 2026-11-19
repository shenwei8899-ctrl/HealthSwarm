import {ingredientLabels} from '../utils/meal-presentation.js'
import {storageContext} from './storage.js'
import {getSession} from './session.js'
export const mealOrder=['breakfast','lunch','dinner']
export const mealLabels={breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}
export function mealTarget(item,plan){return {kind:item.purchase_ready===false?'archive':item.source.kind,familyId:getSession().householdId,date:plan.date,purchaseReady:item.purchase_ready,mealType:item.meal_type,sourceId:item.source.id,version:item.source.version,dailyPlanVersion:plan.version,seed:{...item.meal,members:item.members||[]},purchaseOption:plan.purchase_options?.find(o=>o.kind===item.source.kind&&o.id===item.source.id),purchaseMeals:[item.meal_type]}}
export function purchaseGroups(plan){return (plan.purchase_options||[]).map(option=>{const items=plan.meals.filter(i=>i.source.kind===option.kind&&i.source.id===option.id&&option.meal_types.includes(i.meal_type));if(!items.length)return null;const target=mealTarget(items[0],plan);return {...target,ingredientLabels:ingredientLabels(items.flatMap(i=>i.meal.dishes)),purchaseMeals:mealOrder.filter(t=>option.meal_types.includes(t)),purchaseMembers:[...new Map(items.flatMap(i=>i.members||[]).map(m=>[m.id,m])).values()],label:option.meal_types.map(t=>mealLabels[t]).join('、')}}).filter(Boolean)}
const pendingMeals=new Map()
let mealNavigationId=0
let mealOpening=null
function clearPendingMeal(key){
 const pending=pendingMeals.get(key)
 if(!pending)return
 clearTimeout(pending.timer)
 pendingMeals.delete(key)
 if(mealOpening?.key===key)mealOpening=null
}
export function takeMealPageTarget(key){
 const pending=pendingMeals.get(key)
 if(!pending)return null
 clearPendingMeal(key)
 return pending.owner===storageContext()?pending.target:null
}
export function openMealPage(target,{purchase=false,all=false,dishIndex}={}){
 if(target.kind==='archive'){uni.navigateTo({url:'/pages/health/plans?date='+encodeURIComponent(target.date)});return}
 const owner=storageContext()
 if(mealOpening?.owner===owner)return
 const payload={...target,...(purchase?{initialView:'purchase'}:{}),...(Number.isInteger(dishIndex)?{initialView:'dish',dishIndex}:{})}
 const key=String(++mealNavigationId)
 const opening={owner,key}
 mealOpening=opening
 {
  // Pass only an opaque key through the route. Meal data stays in this session.
  const timer=setTimeout(()=>{clearPendingMeal(key);if(mealOpening===opening)mealOpening=null},60000)
  timer?.unref?.()
  pendingMeals.set(key,{owner,target:payload,timer})
 }
 uni.navigateTo({
  url:(all?'/pages/meals/purchase':'/pages/meals/detail')+'?mealNavigation='+key,
  success(result){if(mealOpening===opening)mealOpening=null;if(owner===storageContext())result?.eventChannel?.emit('mealWorkspace',{owner,target:payload})},
  fail(){
   if(mealOpening===opening)mealOpening=null
   if(key)clearPendingMeal(key)
   if(owner===storageContext())uni.showToast({title:'页面未能打开，请重试',icon:'none'})
  }
 })
}
export function referencePurchaseFor(target){if(target.kind!=='reference')return null;const option=target.purchaseOption,types=target.purchaseMeals||[target.mealType],all=option?.meal_types||[target.mealType];const subset=types.length!==all.length;const ingredients=new Set((target.seed?.dishes||[]).flatMap(d=>d.ingredients||[]));const mapped=!subset||(option?.items||[]).every(i=>Array.isArray(i.ingredient_refs));return {ingredientLabels:{...ingredientLabels(target.seed?.dishes),...target.ingredientLabels,...option?.ingredient_labels},previewId:target.sourceId,dailyPlanVersion:target.dailyPlanVersion,mealTypes:types,items:!mapped?[]:subset?(option?.items||[]).filter(i=>i.ingredient_refs.some(ref=>ingredients.has(ref))):option?.items||[],gaps:option?.gaps||[],quantityNotice:option?.quantity_notice||'',needsMatching:!mapped}}
