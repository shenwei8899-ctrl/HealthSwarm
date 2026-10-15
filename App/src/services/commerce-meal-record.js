import { confirmPortionDraft } from '../utils/scan-portions.js'

// A manual intake record keeps order provenance without claiming photo analysis.
export function makeCommerceMealRecord(context, draft, { id, photoPath = null, createdAt = new Date().toISOString() }) {
  const menu=context?.meal_snapshot
  if (!context?.order_sn || !menu?.package_sn || !menu.dishes?.length) throw new Error('订单菜谱未确认，请重新读取')
  const names=[...new Set(menu.dishes.map(d=>d.recipe_name))]
  if (!draft.people.length) throw new Error('请选择实际用餐成员')
  const {people,oil}=confirmPortionDraft(draft,names)
  const dishes=[...new Set(people.flatMap(p=>p.dishes))]
  return {
    id,version:1,source:'按订单菜谱手动确认',captureScope:people.length>1?'家庭共享桌菜':'单人餐盘',
    sourceOrderSn:context.order_sn,packageSn:menu.package_sn,packageVersion:menu.package_version,
    menuVersionRef:menu.menu_version_ref,recipeVersions:menu.dishes.map(d=>({recipeRef:d.recipe_ref,recipeVersion:d.recipe_version})),
    memberId:people[0].memberId,memberName:people[0].memberName,memberIds:people.map(p=>p.memberId),memberNames:people.map(p=>p.memberName),memberIntake:people,
    meal:{breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}[menu.meal]||'晚餐',dishes,oil,
    portion:people.length>1?'逐人确认':people[0].portion,grams:people.length>1?null:people[0].grams,
    kcal:null,low:null,high:null,protein:null,carbs:null,fat:null,sugars:null,
    photo:Boolean(photoPath),photoPath,createdAt,isDemo:menu.is_local_fixture===true,
    storage:'local-member',nutritionStatus:'unknown',photoAnalysisStatus:'not_requested',
  }
}
