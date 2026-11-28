import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {compile,createSSRApp} from 'vue'
import {renderToString} from 'vue/server-renderer'
import {planningProfileIssues,profileCompletionUrl} from '../src/services/planning-profile-issues.js'
import {createHealthTaskFlow} from '../src/services/health-task-flow.js'

const problem={member_id:'synthetic-member',name:'合成乙',can_edit:true,fields:[{field:'height_cm',label:'身高',message:'请填写身高',reason:'missing',section:'basic'}]}
test('task entry preserves structured profile rejection and permission loss clears it',async()=>{
 const id='11111111-1111-4111-8111-111111111111',request='22222222-2222-4222-8222-222222222222'
 let denied=false;const calls=[]
 const flow=createHealthTaskFlow({session:()=>({accountId:'synthetic',householdId:'family',token:'synthetic'}),revision:()=>1,
  storage:{getStorageSync(){},setStorageSync(){}},newId:()=>request,watchNetwork:()=>()=>{},
  send:async options=>{
   calls.push(options.path)
   if(denied)throw Object.assign(new Error('no permission'),{code:403})
   if(options.path==='/api/health/v1/members')return {data:[{id,is_owner:true}]}
   if(options.path.endsWith('/readiness'))return {data:{capabilities:{member_id:id},entries:[{entry_type:'blood_glucose_review',status:'available'}]}}
   throw Object.assign(new Error('请补齐合成乙的资料'),{code:422,businessCode:'profile_incomplete',profileIssues:[problem]})
  }})
 await flow.open(id,'blood_glucose_review');await flow.createEntry()
 assert.equal(flow.getState().businessCode,'profile_incomplete')
 assert.equal(flow.getState().profileIssues[0].name,'合成乙')
 assert.equal(calls.filter(path=>path.endsWith('/task-entries')).length,1)
 denied=true;await flow.open(id,'blood_glucose_review')
 assert.deepEqual(flow.getState().profileIssues,[])
 flow.hide()
})
test('completion links bind the exact member and field and never open unauthorized edits',()=>{
 assert.equal(profileCompletionUrl(problem),'/pages/profile/member?id=synthetic-member&complete=1&section=basic&field=height_cm')
 assert.equal(profileCompletionUrl({...problem,can_edit:false}),null)
 assert.deepEqual(planningProfileIssues([{...problem,private_profile:{height:123}}])[0],{...problem,version:undefined})
 assert.deepEqual(planningProfileIssues([{member_id:'x',name:'bad',fields:null}]),[])
})
test('meal panel renders member-specific prompts and no generic failure or loading text',async()=>{
 const source=readFileSync(new URL('../src/components/TodayMealPlanContent.vue',import.meta.url),'utf8')
 const render=compile(source.match(/<template>([\s\S]*?)<\/template>\s*<style/)[1])
 const html=await renderToString(createSSRApp({render,setup:()=>({
  state:{plan:null,phase:'error',profileIssues:[problem,{...problem,member_id:'second',name:'合成丙',can_edit:false}]},
  presentation:{showNotice:false},heading:false,busy:false,interactive:true,meals:[],mealEntries:[],missingMeals:'',emit:()=>{},
 })}))
 assert.match(html,/合成乙/);assert.match(html,/合成丙/);assert.match(html,/请填写身高/)
 assert.equal((html.match(/去补齐/g)||[]).length,1)
 assert.match(html,/请由本人或有权限的家人补齐资料/)
 assert.doesNotMatch(html,/暂时无法读取餐单|暂未获取餐单结果|tm-loading/)
})
