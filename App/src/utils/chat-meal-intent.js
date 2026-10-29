const allMeals = ['breakfast', 'lunch', 'dinner']

export function isMealPlanningCancelled(value) {
  return /(?:不用|不要|不需要|不想|取消|停止)(?:(?:再|继续|这次|本次|当前|的)|(?:给|为|帮|替)[^，。！？；\s]{1,12}?){0,2}(?:配餐|配菜|安排|生成|制定)/.test(String(value || ''))
}

/** 只识别明确的用餐安排请求；疾病科普不会成为本人诊断。 */
export function parseChatMealIntent(value, today) {
  const text = String(value || '').trim()
  if (!text || isMealPlanningCancelled(text)) return null
  const education = /(?:什么是|介绍|解释|科普|原则|注意事项|怎么理解|如何理解|有何区别|有什么区别)/.test(text)
  const request = /配餐|配菜|推荐(?:几|两|三|一|些|点|道).*(?:菜|吃)|(?:安排|生成|制定|规划|推荐|设计|提供|给我|帮我|为我).*(?:餐|早饭|午饭|晚饭|食谱|菜单|吃)|(?:今天|今日|明天|明日|今晚|今早|明早|早饭|午饭|晚饭|早餐|午餐|晚餐|一日三餐).*(?:怎么吃|吃什么|吃啥|如何吃|吃点什么|推荐|安排|搭配)|(?:今天|明天|今晚|明晚|今早|明早).*(?:早餐|午餐|晚餐|早饭|午饭|晚饭).*(?:不要|避免|不能吃|不吃|过敏)/.test(text)
  if (!request || education) return null
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
    date: Number.isNaN(date.getTime()) ? today : date.toISOString().slice(0, 10),
    meals: matchedMeals.length ? matchedMeals : [...allMeals],
    audience: /全家|一家人|一家|家人|我们|家庭(?:三餐|配餐|餐单|菜单|用餐|饮食计划)/.test(text) ? 'family' : /为我|给我|帮我|本人|自己|一个人|一人|只(?:有|给)?我/.test(text) ? 'self' : 'default',
    unsupportedDate,
    // 聊天限制尚未写入档案时，不能假装已纳入服务端配餐校验。
    requiresProfileReview: condition || /(?:过敏|不耐受|忌口|医嘱|医生(?:说|要求|不让)|不能吃|不吃|不放|不要(?:加)?|避免|去掉|不含|少放|多放)/.test(text),
  }
}
