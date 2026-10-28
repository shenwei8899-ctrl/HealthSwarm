export function readyPreparation(date='2026-10-26') {
 const meals=['breakfast','lunch','dinner'].map(type=>({type,members:[{id:'member',name:'合成成员'}],dishes:[{id:'dish',name:'合成菜品',recipeVersion:1,ingredients:[{}],steps:['合成步骤']}],detail_ref:'detail',nutrition:{kcal:1},nutritionSource:'synthetic',memberNotes:[{memberId:'member',dishes:['dish']}],purchase:{package_sn:'synthetic-package',package_version:1}}))
 return {status:'ready',id:'prepared',date,profile_saved:true,thread_id:'saved-thread',arrangement:{status:'ready',id:'saved-arrangement',date,version:1,saved:true,validation:{status:'passed'},procurement:{checked:true},analysis:{source:'agent',request_id:'request',run_id:'run',text:'合成分析'},meals}}
}
