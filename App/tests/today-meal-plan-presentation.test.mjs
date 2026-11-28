import test from 'node:test'
import assert from 'node:assert/strict'
import {todayMealPlanPresentation as present} from '../src/services/today-meal-plan-presentation.js'

const saved = patch => ({plan:{roster:{}},notice:'',action:'',pending:null,generationFailed:false,...patch})

test('ordinary saved-menu verification does not claim the menu is being updated',()=>{
 const result=present(saved({checking:true}))
 assert.equal(result.kind,'');assert.equal(result.showNotice,false)
})
test('member synchronization and actual local generation use a short status instead of a banner',()=>{
 for(const [state,generating] of [
  [saved({plan:{roster:{lunch:{status:'pending'}}},notice:'正在按新的就餐成员更新餐单'}),false],
  [saved({notice:'正在更新餐单，已有餐次可继续查看。'}),true],
  [saved({pending:{status:'running'},notice:'正在更新餐单'}),false],
 ]){
  const result=present(state,generating)
  assert.equal(result.kind,'updating');assert.equal(result.label,'更新中');assert.equal(result.showNotice,false);assert.equal(result.retry,false)
 }
 assert.equal(present(saved()).kind,'')
})
test('only an existing refresh or regenerate action makes a failed status actionable',()=>{
 for(const action of ['', 'refresh', 'regenerate']){
  const result=present(saved({plan:{roster:{lunch:{status:'failed'}}},action}))
  assert.equal(result.label,'未完成');assert.equal(result.showNotice,false);assert.equal(result.retry,!!action)
 }
 assert.equal(present(saved({generationFailed:true,action:'regenerate'})).retry,true)
})
test('historical failed tasks do not turn a usable complete menu into a failure',()=>{
 assert.equal(present(saved({pending:{status:'failed'}})).kind,'')
})
test('a fresh local retry shows updating while the previous roster failure is still stored',()=>{
 assert.equal(present(saved({plan:{roster:{lunch:{status:'failed'}}}}),true).kind,'updating')
})
test('a partial background failure stays visible while other meals update without offering premature retry',()=>{
 const result=present(saved({plan:{roster:{lunch:{status:'failed'},dinner:{status:'pending'}}},action:'regenerate'}))
 assert.equal(result.kind,'failed');assert.equal(result.retry,false)
})
test('consent, follow-up questions and candidate review retain their original action area',()=>{
 for(const patch of [
  {consentOption:{processor:'合成处理方',policyVersion:'v1'},action:'consent'},
  {pending:{status:'needs_input',questions:['合成问题']},action:'answer'},
  {pending:{status:'reference_candidates'},action:'candidates'},
 ]){
  const result=present(saved({plan:{roster:{lunch:{status:'pending'}}},...patch}),true)
  assert.equal(result.kind,'');assert.equal(result.showNotice,true)
 }
})
test('incomplete menu instructions and first-time loading/error screens retain existing rendering',()=>{
 assert.equal(present(saved({notice:'三餐尚未配齐',action:'regenerate'})).showNotice,true)
 for(const phase of ['generating','error']){
  const result=present({plan:null,phase,notice:'合成提示',action:'refresh'},true)
  assert.equal(result.kind,'');assert.equal(result.showNotice,false)
 }
})
