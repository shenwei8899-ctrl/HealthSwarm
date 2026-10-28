import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { createRequire } from 'node:module'
const require=createRequire(import.meta.url)
const { chromium }=require(process.env.PLAYWRIGHT_PACKAGE||'playwright')
const origin=process.env.PROFILE_TEST_ORIGIN||'http://127.0.0.1:15236'
const evidence=process.env.PROFILE_TEST_EVIDENCE
assert.ok(evidence,'PROFILE_TEST_EVIDENCE is required')
await fs.mkdir(evidence,{recursive:true})
const family='11111111-1111-4111-8111-111111111111',own='22222222-2222-4222-8222-222222222222',mother='33333333-3333-4333-8333-333333333333',health='44444444-4444-4444-8444-444444444444'
const fields=['sex','birth_date','height_cm','dietary_details','goal','allergens','avoidances','doctor_instructions','medical_history','medications']
const raw=id=>({id,name:id===own?'合成本人':'合成妈妈',relationship:id===own?'本人':'妈妈',is_self:id===own,is_active:true,claimed:true,is_guardian:false,version:2,relationship_version:1,confirmed:true,allowed_fields:fields,editable_fields:fields,profile:{sex:'female',birth_date:id===own?'1990-01-01':'1960-01-01',height_cm:165,medications:'合成旧用药信息',dietary_details:{statedWeightKg:55,healthStatus:'none',allergyStatus:'set',allergies:['合成过敏原'],intoleranceStatus:'none',avoidanceStatus:'none',doctorStatus:'none',goals:['饮食均衡'],cuisines:['家常菜'],tastePreferences:['清淡']}}})
const members=[raw(own),raw(mother)],writes=[],unexpected=[],errors=[]
let failRead=false
function projection(){return {source:'api',householdId:family,householdName:'合成测试家庭',familyVersion:1,usageMode:'家庭使用',onboarded:members[0].confirmed,selfMemberId:own,isOwner:true,defaultDiners:[own,mother],members:members.map(m=>({id:m.id,name:m.name,relation:m.relationship,version:m.version,claimed:true,healthMemberId:m.healthMemberId||null,birthDate:m.profile.birth_date,gender:'女',height:m.profile.height_cm,weight:m.profile.dietary_details.statedWeightKg,...m.profile.dietary_details}))}}
const browser=await chromium.launch({headless:true,channel:process.env.PROFILE_TEST_BROWSER||'chrome'})
const page=await browser.newPage({viewport:{width:414,height:900}})
page.on('pageerror',e=>errors.push(e.message))
await page.route('**/api/**',async route=>{
  const r=route.request(),path=new URL(r.url()).pathname,method=r.method()
  let status=200,data
  if(method!=='GET')writes.push({path,method,body:r.postDataJSON()})
  if(path==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'合成本人'},families:[{id:family,name:'合成测试家庭',is_owner:true,onboarding_required:false}]}
  else if(path==='/api/health/v1/configuration')data={policy_version:'synthetic-v1',consultation:{available:true,processor:'合成测试处理方'}}
  else if(path===`/api/family/${family}/miniapp-profile`&&method==='GET')data=projection()
  else if(path===`/api/family/${family}/miniapp-profile`&&method==='POST'){
    const body=r.postDataJSON();assert.equal(body.action,'start_analysis');assert.equal(body.member_id,own);assert.equal(body.accepted,true)
    members[0].healthMemberId=health;data=projection()
  }
  else if(path===`/api/health/v1/members/${health}/readiness`)data={entries:[{entry_type:'consultation',status:'available'}]}
  else if(path===`/api/health/v1/members/${health}/vision/page`)data={drafts:[]}
  else if([`/api/health/v1/members/${health}/observations`,`/api/health/v1/members/${health}/diet-logs`].includes(path))data=[]
  else if(path===`/api/family/${family}`&&method==='GET'){if(failRead){status=503;data={message:'合成读取失败，请重试'}}else data={id:family,version:1,members}}
  else if(path===`/api/family/${family}/members/${mother}`&&method==='PUT'){
    const body=r.postDataJSON();assert.equal(body.expected_version,members[1].version)
    members[1].profile={...members[1].profile,...body.profile};members[1].version++;members[1].confirmed=false;data=members[1]
  }else if(path.endsWith('/invite')){status=403;data={detail:'合成已认领成员无需邀请'}}
  else {unexpected.push({path,method});status=404;data={message:'unhandled synthetic request'}}
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
})
const button=text=>page.locator('uni-button').filter({hasText:new RegExp('^'+text+'$')})
async function navigate(url){await page.evaluate(url=>{location.hash='#'+url},url)}
try{
  await page.goto(origin,{waitUntil:'domcontentloaded',timeout:60000});await page.locator('uni-page').waitFor({timeout:60000})
  await page.evaluate(({family})=>localStorage.setItem('fn-session-v2:api',JSON.stringify({type:'object',data:{accountId:'1',householdId:family,token:'synthetic-token',authSource:'wechat',clientRevision:'synthetic-1',families:[{id:family,name:'合成测试家庭',isOwner:true}]}})),{family})
  await navigate('/pages/profile/index')
  await page.getByText('合成妈妈',{exact:true}).waitFor()
  await page.getByText('合成妈妈',{exact:true}).click()
  await page.getByText('合成妈妈的健康档案',{exact:true}).waitFor()
  assert.equal(await page.locator('.archive-field').filter({has:page.getByText('用药说明',{exact:true})}).locator('textarea').inputValue(),'合成旧用药信息')
  assert.equal(await button('同意并开始分析').count(),0)
  await button('编辑').click()
  await page.locator('.field-card .two-col>uni-view').filter({has:page.getByText('体重 kg（可后补）',{exact:true})}).locator('input').fill('57')
  await button('保存档案').click()
  await page.getByText('身高 165 cm · 体重 57 kg',{exact:true}).waitFor()
  const saves=writes.filter(w=>w.method==='PUT')
  assert.equal(saves.length,1);assert.equal(saves[0].path,`/api/family/${family}/members/${mother}`)
  assert.deepEqual(Object.keys(saves[0].body.profile),['dietary_details'])
  assert.equal(members[0].profile.dietary_details.statedWeightKg,55)
  assert.equal(members[1].confirmed,false)
  await page.screenshot({path:`${evidence}/mother-saved.png`,fullPage:true})
  await navigate(`/pages/profile/member?id=${own}`)
  await page.getByText('合成本人的健康档案',{exact:true}).waitFor()
  assert.equal(await button('同意并开始分析').count(),1)
  assert.equal(await button('同意并开始分析').getAttribute('disabled')!==null,true)
  await page.screenshot({path:`${evidence}/self-confirmation.png`,fullPage:true})
  await page.locator('uni-checkbox').click();await button('同意并开始分析').click()
  await button('开始咨询').waitFor()
  assert.equal(await button('同意并开始分析').count(),0)
  assert.equal(writes.filter(w=>w.body?.action==='start_analysis').length,1)
  await navigate('/pages/profile/index')
  await page.getByText('合成妈妈',{exact:true}).waitFor()
  failRead=true
  await page.getByText('合成妈妈',{exact:true}).click()
  await page.getByText('合成读取失败，请重试',{exact:true}).waitFor()
  assert.equal(await button('编辑').count(),0)
  failRead=false;await button('重新读取').click()
  await page.getByText('合成妈妈的健康档案',{exact:true}).waitFor()
  assert.deepEqual(unexpected,[]);assert.deepEqual(errors,[])
  await fs.writeFile(`${evidence}/browser-result.json`,JSON.stringify({status:'passed',source:'synthetic HTTP fixtures; real H5 UI',singleMemberWrites:saves,errors},null,2))
  console.log('Unified profile browser checks passed')
}catch(error){await page.screenshot({path:`${evidence}/failure.png`,fullPage:true});console.error((await page.locator('body').innerText()).slice(0,1600),errors,unexpected);throw error}finally{await browser.close()}
