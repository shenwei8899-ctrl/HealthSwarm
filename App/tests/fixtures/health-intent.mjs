/** Synthetic server response for component lifecycle tests; backend routing is
 * verified independently in test_health_intent_router.py. */
import {parseChatMealIntent,parseMultiDayMealIntent,isMealPlanningCancelled} from '../../src/utils/chat-meal-intent.js'
import {mealQuestionAction} from '../../src/services/daily-meal-plan.js'
export function syntheticIntent(data,today){
 const text=data.text
 if(parseMultiDayMealIntent(text,today)||/(?:安排|生成|规划).*(?:一周|两周|三周|三天|七天|八天)/.test(text))return {route:'exclusive_plan',action:'handoff',message:'目前可生成 21 天 AI 专属计划，点击后进入专属计划页面。'}
 if(/下周|下星期/.test(text))return {route:'needs_clarification',action:'ask',message:'请说明要安排的具体日期。'}
 const parsed=parseChatMealIntent(text,today,!!data.previous_date)
 if(isMealPlanningCancelled(text)||/换个话题|换个问题|什么是|介绍|解释|科普|原则|怎样|怎么(?:选|做|换|搭配)/.test(text))return {route:'nutrition_consultation',action:'generate'}
 const action=/只改|只换/.test(text)||parsed?.revision||/改成|不放|不含|去掉|少放|不要|加一点/.test(text)&&data.previous_date?'change':mealQuestionAction(text)
 const continuing=data.awaiting_meal_details&&data.previous_date&&!/明天|后天|全家|父亲|母亲|爸爸|妈妈/.test(text)
 if(parsed||action!=='consultation'||continuing){
  const offset=/大后天/.test(text)?3:/后天/.test(text)?2:/明天|明日|明早|明晚/.test(text)?1:0
  const date=/今天|今日|明天|明日|后天|今早|今晚|明早|明晚/.test(text)?new Date(Date.parse(today)+offset*86400000).toISOString().slice(0,10):action==='change'||continuing?data.previous_date||today:parsed?.date||today
  const meals=[['breakfast',/早餐|早饭|早上|今早|明早/],['lunch',/午餐|午饭|中午/],['dinner',/晚餐|晚饭|晚上|今晚|明晚/]].filter(([,p])=>p.test(text.split(/[，,]/).filter(part=>!/不变|保持原样|照旧/.test(part)).join('，'))).map(([meal])=>meal)
  return {route:'single_day_meal',action:continuing?'continue':action==='consultation'?'generate':action,business_date:date,meal_types:meals.length?meals:action==='change'||continuing?data.previous_meals||['breakfast','lunch','dinner']:['breakfast','lunch','dinner']}
 }
 return {route:'nutrition_consultation',action:'generate'}
}
