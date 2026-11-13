// Write each question as something a person would actually ask. Topic metadata
// drives matching; it must not be mechanically prepended to the visible copy.
// Categories are shared metadata; every pipe-separated question is authored in full.
const categories = ["breakfast", "takeaway", "eat-out", "snacks", "cooking", "label", "office-lunch", "weekly"]
const questions = {
  hypertension: "高血压早餐吃啥？|外卖怎么少盐？|聚餐该少点啥？|推荐清淡零食|少放盐怎么提味？|教我看钠含量|想带份少盐午饭|调味料也藏盐吗？",
  diabetes: "控糖早餐吃啥？|外卖主食怎么搭？|控糖聚餐点啥？|推荐控糖加餐|粗粮能替米饭吗？|无糖食品能吃吗？|控糖午饭带啥？|三餐主食怎么分？",
  lipids: "血脂高早餐吃啥？|外卖怎么避油？|清蒸还是红烧？|想试试控脂加餐|家常菜怎么少油？|怎么看饱和脂肪？|想带清淡便当|控脂还能吃肉吗？",
  purines: "尿酸高早餐吃啥？|尿酸高怎么点餐？|火锅哪些菜少吃？|推荐合适的加餐|浓肉汤能喝吗？|饮料配料怎么看？|低嘌呤午饭吃啥？|想了解控尿酸饮食",
  kidney: "肾病早餐怎么选？|肾病外卖怎么选？|出门吃饭问什么？|想按医嘱选加餐|怎么按医嘱做饭？|肾病看哪些标签？|带饭前要查什么？|配餐还要查什么？",
  salt: "少盐早餐吃啥？|外卖怎样吃清淡？|聚餐吃啥清淡？|推荐不咸的加餐|少放盐也能香吗？|标签上的钠是啥？|想试试少盐便当|哪些调料盐多？",
  sugar: "控糖早餐怎么搭？|外卖饭菜怎么配？|聚餐能喝点啥？|想找控糖小点心|甜口菜怎么减糖？|零蔗糖算无糖吗？|推荐控糖便当|控糖得戒主食吗？",
  fat: "少油早餐吃啥？|看着不油就少油？|聚餐怎么少吃油？|想换掉油炸零食|炒菜怎样少放油？|教我看脂肪含量|推荐少油便当|沙拉酱也有油吗？",
  'low-purine': "低嘌呤早餐吃啥？|低嘌呤外卖点啥？|聚餐哪些菜少吃？|推荐低嘌呤加餐|低嘌呤菜怎么做？|选饮料看什么？|想带低嘌呤便当|低嘌呤就得吃素？",
  weight: "减脂早餐吃啥？|减脂外卖怎么点？|聚餐怎么少热量？|推荐解馋加餐|家常菜怎么减脂？|零脂肪就低热量？|想带顶饱的午饭|减脂能吃晚饭吗？",
  muscle: "增肌早餐怎么搭？|增肌外卖点什么？|聚餐吃啥补蛋白？|推荐练后加餐|增肌餐怎么换样？|高蛋白怎么看？|想试试增肌便当|增肌得多吃肉吗？",
  balanced: "光吃面包够吗？|外卖怎样搭均衡？|聚餐荤素怎么搭？|想要均衡的加餐|家常饭怎么搭配？|标签先看哪几项？|推荐简单便当|三餐要天天换吗？",
  vegetables: "早餐加点什么菜？|外卖蔬菜少咋办？|聚餐点什么蔬菜？|推荐蔬菜小点心|蔬菜除了清炒呢？|菜干能代替鲜菜？|带饭选什么蔬菜？|每天吃同种菜行吗",
  light: "清淡早餐吃啥？|外卖怎样备注？|聚餐想吃清淡点|推荐清淡零食|清淡菜怎么提味？|清淡就得吃水煮？|想带份清淡午饭|吃清淡等于吃素？",
  protein: "早餐吃啥补蛋白？|外卖怎样补蛋白？|不吃肉怎么补蛋白|推荐蛋白质加餐|补蛋白怎么换样？|怎么看蛋白含量？|午饭想加点蛋白|只在晚上补行吗？",
  'other-condition': "有基础病早餐吃啥|点外卖要核对啥？|聚餐有哪些忌口？|想按档案选加餐|家常饭怎么按医嘱|挑食品看什么？|带饭要留意什么？|配餐前还要问啥？",
  allergy: "过敏时早餐吃啥？|外卖怎么说过敏？|聚餐要问餐厅啥？|想挑合适的零食|做饭怎么防过敏？|配料表找过敏原|推荐避敏便当|避开过敏原怎么吃",
  intolerance: "早餐不耐受咋换？|外卖备注怎么写？|聚餐该问啥配料？|想换个合适的加餐|不耐受食材怎么换|配料表注意什么？|想带合适的便当|不耐受就是过敏？",
  avoidance: "有忌口早餐吃啥？|外卖怎么写忌口？|点菜先问啥配料？|想找不踩雷的加餐|忌口食材怎么换？|配料表找忌口|推荐忌口便当|忌口不同能同桌？",
}

function questionForm(text) {
  if (/^(推荐|给我|教我|帮我|想)/.test(text)) return 'request'
  if (/[吗呢][？?]$/.test(text)) return 'yes-no'
  if (/哪些|什么|哪几|哪个|啥/.test(text)) return 'choice'
  return 'how'
}

export const PERSONALIZED_CHAT_PROMPT_POOL = Object.freeze(Object.entries(questions).flatMap(([topic, entries]) =>
  entries.split('|').map((text, index) => { const category = categories[index]; return Object.freeze({ id: `${topic}:${category}`, text, topic, category, form: questionForm(text), action: 'consultation' }) })))
