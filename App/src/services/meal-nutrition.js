import { request } from './request.js'
import { sessionRevision } from './session.js'

const root = '/api/health/v1'
export const mealNutritionState = () => ({ results: [], sources: [], portions: [], busy: false, error: '', sourceBusy: false, sourceError: '', portionBusy: false, portionError: '' })

/** 旧草稿的整份重量按本人比例换算，未知比例仍需重新核对。 */
export function recognizedMealDish(item) {
  const ratio=Number(item.share_ratio),known=item.share_ratio!=null&&ratio>0&&ratio<=1&&item.portion_source!=='unknown'
  const estimate=item.photo_estimate,initial=!known&&item.grams==null&&!!estimate?.draft_id
  return { item_id:item.item_id,name:item.name,food_id:item.food_id,recipe_version_id:item.recipe_version_id,nutrition_source:item.nutrition_source,photo_estimate:estimate||null,
    servings:known&&item.servings!=null?Number(item.servings)*ratio:null,source_basis:item.servings!=null?'per_serving':'per100g',
    grams:known&&item.grams!=null?Number(item.grams)*ratio:initial?Number(estimate.grams):null,
    portion_reference_id:known?item.portion_reference_id:null,
    portion_count:known&&item.portion_count!=null?Number(item.portion_count)*ratio:null,
    portion_label:'份',portion_source:known?item.portion_source:initial?'estimated':'unknown',
    adjustments:known?(item.adjustments||[]).map(a=>({...a,grams:Number(a.grams)*ratio})):[],
    portion_confirmed:initial||known&&(item.grams!=null||item.portion_reference_id!=null||item.servings!=null) }
}

/** 更换来源清除配方调整，计量基准变化后重新核对份量。 */
export function bindMealSource(dish,row){
  const changed=(dish.nutrition_source?.reference||dish.food_id||dish.recipe_version_id)!==row.id||dish.nutrition_source?.version!==row.nutrition_source?.version||!!dish.source_basis&&dish.source_basis!==(row.basis||'per100g')
  if(changed){dish.adjustments=[];dish.servings=null;if(dish.portion_reference_id||dish.source_basis==='per_serving'||row.basis==='per_serving'){dish.grams=null;dish.portion_reference_id=null;dish.portion_count=null;dish.portion_confirmed=false}}
  Object.assign(dish,{food_id:row.type==='food'?row.id:null,recipe_version_id:row.type==='recipe'?row.id:null,nutrition_source:row.nutrition_source||null,photo_estimate:null,source_name:row.name,dataset_version:row.dataset_version,source_basis:row.basis||'per100g',basis_label:row.basis_label})
}

/** 多义同名结果保留人工选择，不能按搜索顺序猜测菜品。 */
export function exactMealSource(name,rows){
  const normalize=s=>String(s).toLowerCase().replace(/[\s\p{P}]/gu,'')
  const matches=rows.filter(row=>row.name.split(/[｜|]/).some(alias=>normalize(alias)===normalize(name)))
  return matches.length===1?matches[0]:null
}

/** 当前输入变化或离开页面后，迟到结果不能重新显示为本餐营养。 */
export function createMealNutritionClient({ state, send = request, revision = sessionRevision } = {}) {
  let generation = 0
  const requests={preview:0,source:0,portion:0}
  function invalidate() { generation++; Object.assign(state, mealNutritionState()) }
  async function read(kind,action) {
    const mine = generation, ticket=++requests[kind],rev = revision(), current = () => mine === generation && ticket===requests[kind] && rev === revision()
    const busy=kind==='preview'?'busy':kind+'Busy',errorKey=kind==='preview'?'error':kind+'Error'
    state[busy] = true; state[errorKey] = ''
    try { await action(current) }
    catch (error) { if (current()) { if(kind==='preview')state.results = []; state[errorKey] = error.message || '营养数据暂时无法读取' } }
    finally { if (current()) state[busy] = false; else if (mine === generation&&rev!==revision()) invalidate() }
  }
  return {
    invalidate,
    preview(meals) {
      state.results = []
      return read('preview',async current => {
        const results = await Promise.all(meals.map(async row => {
          const { data } = await send({ path: `${root}/members/${encodeURIComponent(row.memberId)}/meal-nutrition-preview`, method: 'POST', data: row.meal })
          if (data.member_id !== row.memberId) throw new Error('营养预览所属成员不一致')
          return { ...data, meal: row.meal }
        }))
        if (current()) state.results = results
      })
    },
    search(query,memberId) {
      state.sources = []; state.portions = []
      return read('source',async current => {
        if(!memberId)throw new Error('请先选择记餐成员')
        const {data}=await send({path:`${root}/members/${encodeURIComponent(memberId)}/meal-nutrition-sources?q=${encodeURIComponent(query.trim())}`})
        if (current()) state.sources = data
      })
    },
    async match(query,memberId){
      const rev=revision()
      const {data}=await send({path:`${root}/members/${encodeURIComponent(memberId)}/meal-nutrition-sources?q=${encodeURIComponent(query.trim())}`})
      return rev===revision()?data:[]
    },
    portions(dish) {
      requests.portion++;state.portionBusy=false;state.portionError=''
      state.portions = []
      if (!dish.food_id && !dish.recipe_version_id) return
      const field = dish.food_id ? 'food_id' : 'recipe_version_id'
      return read('portion',async current => {
        const { data } = await send({ path: `${root}/portion-references?${field}=${encodeURIComponent(dish[field])}` })
        if (current()) state.portions = data
      })
    },
  }
}
