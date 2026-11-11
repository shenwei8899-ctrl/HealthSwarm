const allMeals = ['breakfast', 'lunch', 'dinner']
const canonicalWeeklyRequest = /^(?:请|麻烦)?(?:为我们|给全家|为全家|帮全家)?(?:安排|生成|制定|规划|设计|做一份)(?:明天|明日)?(?:起|开始)?(?:一(?:个)?星期|一周|七天|七日|7天|7日|[2-7二两三四五六](?:天|日))(?:的)?(?:三餐|一日三餐|完整餐单|每天的?餐单)[。！？]?$/

export function isMealPlanningCancelled(value) {
  return /(?:不用|不要|不需要|不想|取消|停止)(?:(?:再|继续|这次|本次|当前|的)|(?:给|为|帮|替)[^，。！？；\s]{1,12}?){0,2}(?:配餐|配菜|安排|生成|制定)/.test(String(value || ''))
}

/** 只把明确要求连续二至七天完整三餐的文本交给多日安排。 */
export function parseMultiDayMealIntent(value, today) {
  const text = String(value || '').trim()
  if (!text || isMealPlanningCancelled(text) || /什么是|介绍|解释|科普|原则|注意事项|怎么理解|如何理解/.test(text)) return null
  if (!/(?:安排|生成|制定|规划|设计|做一份|给我|帮我|想要|希望|我要)/.test(text) || !/(?:三餐|一日三餐|完整餐单|每天的?餐单)/.test(text)) return null
  let count = /(?:一(?:个)?星期|一周|七天|七日|7天|7日)/.test(text) ? 7 : null
  if (count === null) {
    const found = text.match(/([2-7二两三四五六])(?:天|日)/)
    const words = {二:2,两:2,三:3,四:4,五:5,六:6}
    count = found ? words[found[1]] || Number(found[1]) : null
  }
  if (!count || /下周|下星期|上周|昨天|昨日|\d{4}[-年/.]\d|\d{1,2}月\d/.test(text)) return null
  const start = new Date(today + 'T12:00:00Z')
  if (Number.isNaN(start.getTime())) return null
  if (/明天|明日/.test(text)) start.setUTCDate(start.getUTCDate() + 1)
  const requiresProfileReview = !canonicalWeeklyRequest.test(text)
  return {dayCount:count,startDate:start.toISOString().slice(0,10),requiresProfileReview}
}

/** 只识别明确的用餐安排请求；疾病科普不会成为本人诊断。 */
export function parseChatMealIntent(value, today, hasMealContext = false) {
  const text = String(value || '').trim()
  if (!text || isMealPlanningCancelled(text)) return null
  if (/^(?:请)?(?:你)?(?:不用|不要|不需要|别)(?:再)?(?:给|为|帮)(?:我|我们)(?:提供|发)?(?:今天|今日|明天|明日)?(?:的)?(?:早餐|午餐|晚餐)?(?:的)?(?:食谱|菜谱|菜单)[。！？!?\s]*$/.test(text)) return null
  const education = /(?:什么是|介绍|解释|科普|原则|注意事项|怎么理解|如何理解|有何区别|有什么区别)/.test(text)
  const revision = !education && !/换(?:个|一个)?话题|换个问题/.test(text) &&
    (/(?:再|重新)?(?:换|更换|替换)(?:一|几|两|三|些|点|批|道|个|下|别|其他|其它|这|那|菜|餐).*(?:菜|餐|食谱|菜单)/.test(text) ||
      hasMealContext && /^(?:请|帮我|给我|再|能不能|可以|麻烦|那|就|都|全部|重新)*(?:换(?:一批|一组|几个|几道|一下|一些|掉|成其他的)|还有(?:别的|其他的|其它的)(?:吗|么)?)[。？！!？\s]*$/.test(text))
  const changeMeal = /(?:^|[：:，。！？；,;\s])(?:请)?(?:只)?(?:更换|替换|换|调整)(?:一下)?(?:今天|今日|明天|明日|今晚|明晚)?(?:的)?(?:早餐|午餐|晚餐|早饭|午饭|晚饭)/.test(text)
  const request = /配餐|配菜|推荐(?:几|两|三|一|些|点|道).*(?:菜|吃)|(?:安排|生成|制定|规划|推荐|设计|提供|给我|帮我|为我).*(?:餐|早饭|午饭|晚饭|食谱|菜谱|菜单|吃)|(?:今天|今日|明天|明日|今晚|今早|明早|早饭|午饭|晚饭|早餐|午餐|晚餐|一日三餐).*(?:怎么吃|吃什么|吃啥|如何吃|吃点什么|推荐|安排|搭配)|(?:今天|明天|今晚|明晚|今早|明早).*(?:早餐|午餐|晚餐|早饭|午饭|晚饭).*(?:不要|避免|不能吃|不吃|过敏)/.test(text)
  const dishRequest = /(?:推荐|搭配|挑|选|安排|做|来).*(?:菜|食谱|菜单)|(?:什么菜|哪些菜|哪道菜|菜品|菜谱|菜肴).*(?:适合|推荐|搭配)|(?:适合|想|可以).*(?:吃|做).*(?:什么菜|哪些菜|哪道菜)/.test(text)
  const recipeRequest = /^(?:请|麻烦)?(?:你)?(?:把)?(?:今天|今日|明天|明日)?(?:的)?(?:早餐|午餐|晚餐|早饭|午饭|晚饭)?(?:的)?(?:食谱|菜谱|菜单)(?:发给|给|提供给)(?:我|我们)(?:看看|看一下)?[。！!\s]*$/.test(text)
  if ((!request && !dishRequest && !recipeRequest && !changeMeal && !revision) || education) return null
  const condition = /糖尿病|高血压|高血脂|肾病|肾脏|妊娠|孕期|哺乳|婴儿/.test(text)
  if (condition && !/(?:为我|给我|帮我|给我们|为我们|帮我们|全家|一家人).*(?:安排|生成|制定|配餐)/.test(text)) return null

  const matchedMeals = [
    [/早餐|早饭|早上|今早|明早/, 'breakfast'],
    [/午餐|午饭|中午/, 'lunch'],
    [/晚餐|晚饭|晚上|今晚|明晚/, 'dinner'],
  ].filter(([pattern]) => pattern.test(text)).map(([, meal]) => meal)
  const tomorrow = /明天|明日|明早|明晚/.test(text)
  const date = new Date(today + 'T12:00:00Z')
  if (tomorrow) date.setUTCDate(date.getUTCDate() + 1)
  const unsupportedDate = /后天|大后天|昨天|昨日|上周|下周|下星期|本周|这周|一周|(?:[2-9]\d*|1\d+|[二两三四五六七八九十百][一二两三四五六七八九十百]*)[天日]|未来|\d{4}[-年/.]\d|\d{1,2}月\d/.test(text)
  return {
    ...(revision ? {revision:true} : {}),
    date: Number.isNaN(date.getTime()) ? today : date.toISOString().slice(0, 10),
    meals: matchedMeals.length ? matchedMeals : [...allMeals],
    audience: /全家|一家人|一家|家人|我们|家庭(?:三餐|配餐|餐单|菜单|用餐|饮食计划)/.test(text) ? 'family' : /为我|给我|帮我|本人|自己|一个人|一人|只(?:有|给)?我/.test(text) ? 'self' : 'default',
    unsupportedDate,
    // 聊天限制尚未写入档案时，不能假装已纳入服务端配餐校验。
    requiresProfileReview: condition || /(?:过敏|不耐受|忌口|医嘱|医生(?:说|要求|不让)|不能吃|不吃|不放|不用(?:放|加)?|不要(?:加)?|避免|去掉|不含|少放|多放)/.test(text),
  }
}
