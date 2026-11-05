export function mealCandidates(date='2026-10-31',member='self',mealTypes=['breakfast']) {
 const value={status:'reference_candidates',scope:'cooking_reference',plan_date:date,
  selection:{mode:'reference',family_id:'family',participant_ids:[member],plan_date:date,meal_types:['breakfast']},
  members:[{id:member,name:'合成成员',allergens:['合成限制'],avoidances:[],intolerances:[],doctor_instructions:''}],
  candidate_selection:[{meal_type:'breakfast',candidate_ids:['rice-candidate']}],
  meals:[{meal_type:'breakfast',dishes:[{id:'rice-candidate',name:'合成米饭做法',ingredient_food:'rice',
   ingredients:['大米 100克','水 适量'],steps:['淘洗大米。','加水煮熟，确认熟透后食用。'],meal_types:['breakfast'],no_added_oil:true,no_added_salt:true,
   source:{title:'合成烹饪来源',url:'https://example.com/rice',kind:'source_based_notes',content_hash:'a'.repeat(64),
    hash_algorithm:'sha256',hash_scope:'reference_without_source_content_hash_canonical_json_utf8',notes:'整理稿内容的哈希，不是来源网页原文字节哈希。'}}]}],
  restriction_verification:{status:'unresolved',restrictions:[{member_id:member,field:'allergens',text:'合成限制仍需核对'}]},
  purchase_items:[],purchase_allowed:false,notice:'候选做法仅供核对，尚未确认个人适用性。',
  unresolved_materials:['真实配料尚未核对','交叉接触信息缺失','限制分类尚未核对','医嘱解释尚未核对']}
 value.selection.meal_types=[...mealTypes]
 value.candidate_selection=mealTypes.map(meal_type=>({meal_type,candidate_ids:['rice-candidate-'+meal_type]}))
 const dish=value.meals[0].dishes[0]
 value.meals=mealTypes.map(meal_type=>({meal_type,dishes:[{...structuredClone(dish),id:'rice-candidate-'+meal_type,meal_types:[...mealTypes]}]}))
 return value
}
