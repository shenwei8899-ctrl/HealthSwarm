import test from 'node:test'
import assert from 'node:assert/strict'
import {parseChatMealIntent} from '../src/utils/chat-meal-intent.js'

test('direct requests with the recipe before the giving verb enter meal planning',()=>{
  for(const text of ['你把菜谱给我','把今天的菜谱发给我','菜谱给我','给我菜谱','把明天早餐食谱给我们看看']){
    assert.ok(parseChatMealIntent(text,'2026-11-07'),text)
  }
  const intent=parseChatMealIntent('把明天早餐食谱给我们看看','2026-11-07')
  assert.equal(intent.date,'2026-11-08')
  assert.deepEqual(intent.meals,['breakfast'])
  assert.equal(intent.audience,'family')
  for(const text of ['为什么要把菜谱给我','不要把菜谱给我','不用给我菜谱','菜谱不要给我','菜谱是什么','你把菜谱给我有什么好处']){
    assert.equal(parseChatMealIntent(text,'2026-11-07'),null,text)
  }
  for(const text of ['晚餐不要牛肉，给我菜谱','不用辣椒，帮我安排明天早餐食谱']){
    const restricted=parseChatMealIntent(text,'2026-11-07')
    assert.ok(restricted,text)
    assert.equal(restricted.requiresProfileReview,true)
  }
  assert.deepEqual(parseChatMealIntent('请给我安排今天晚餐，顺便说说为什么这样搭配','2026-11-07').meals,['dinner'])
})
