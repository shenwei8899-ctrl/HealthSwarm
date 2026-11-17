// Synthetic API integration: never creates real intake records.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import {createRequire} from 'node:module'
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_PACKAGE||'playwright')
const root=path.resolve(process.env.CAPTURE_MENU_H5_BUILD),base=path.resolve(process.env.CAPTURE_MENU_EVIDENCE)
await fs.mkdir(base,{recursive:true})
const server=http.createServer(async(req,res)=>{try{const file=path.resolve(root,'.'+(new URL(req.url,'http://local').pathname==='/'?'/index.html':decodeURIComponent(new URL(req.url,'http://local').pathname)));assert.ok(file.startsWith(root+path.sep));res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream');res.end(await fs.readFile(file))}catch{res.writeHead(404);res.end()}})
await new Promise(r=>server.listen(0,'127.0.0.1',r))
const browser=await chromium.launch({headless:true,executablePath:process.env.CAPTURE_MENU_BROWSER_EXE})
const family='11111111-1111-4111-8111-111111111111',member='22222222-2222-4222-8222-222222222222',day=new Date(Date.now()+8*3600000).toISOString().slice(0,10),results=[]
try{for(const width of [390,320]){
 const context=await browser.newContext({viewport:{width,height:844}}),calls=[],errors=[];let submitted=null,record=null
 await context.addInitScript(({family})=>localStorage.setItem('fn-session-v2:api',JSON.stringify({type:'object',data:{accountId:'1',accountName:'合成测试',householdId:family,token:'synthetic-token',authSource:'wechat',expiresAt:Date.now()/1000+86400,clientRevision:'synthetic',families:[{id:family,name:'合成家庭',isOwner:true,onboardingRequired:false}]}})),{family})
 await context.route('**/api/**',async route=>{
  const req=route.request(),p=new URL(req.url()).pathname,body=req.postDataJSON();calls.push({path:p,method:req.method(),body});let data
  if(p.endsWith('/session/exchange'))data={code:0,data:{user:{id:1,token:'synthetic-shop'},agent_account_id:'1'}}
  else if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'合成测试'},families:[{id:family,name:'合成家庭',is_owner:true,onboarding_required:false}]}
  else if(p.endsWith('/miniapp-profile'))data={source:'api',householdId:family,householdName:'合成家庭',familyVersion:1,usageMode:'个人使用',defaultDiners:[member],selfMemberId:member,isOwner:true,onboarded:true,completeProfile:true,members:[{id:member,name:'我',relation:'本人',birthDate:'2000-01-01',gender:'女',height:165,weight:55,version:1,claimed:true,isSelf:true,confirmed:true,healthStatus:'none',conditions:[],goals:[],tastePreferences:[],cuisines:[],allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],doctorStatus:'none',clinicianGuidance:''}]}
  else if(p==='/api/health/v1/members')data=[{id:member,display_name:'我',scopes:['diet_edit','ai_use']}]
  else if(p.endsWith('/configuration'))data={policy_version:'v1',consultation:{available:true,processor:'synthetic'},meal:{available:false,reason:'合成测试不调用识别'}}
  else if(p.endsWith('/processing-consents'))data={accepted:false}
  else if(p.endsWith('/readiness'))data={capabilities:{member_id:member},entries:[{entry_type:'consultation',status:'available'}]}
  else if(p.endsWith('/consultations'))data={items:[],has_more:false,next_offset:null}
  else if(p.includes('/requests'))data={requests:[],queue:{status:'idle'}}
  else if(p.endsWith('/history'))data={thread:{id:'synthetic-thread'},runs:[],related_threads:[],history:[]}
  else if(p.endsWith('/daily-conversations'))data={days:[]}
  else if(p.includes('/preparation'))data={status:'absent'}
  else if(p.endsWith('/dish-swap-candidates'))data={date:day,version:4,meals:[]}
  else if(p.endsWith('/daily-meal-plans/'+day))data={status:'ready',date:day,version:4,meals:[{meal_type:'lunch',source:{kind:'reference',id:'synthetic-menu'},meal:{dishes:[{name:'Fish',display_zh:{name:'清蒸鱼'},planned_grams:300,nutrition:{energy_kcal:900}},{name:'米饭'}]}}]}
  else if(p.endsWith('/meal-nutrition-preview'))data={member_id:member,complete:false,totals:{energy_kcal:null},items:body.items.map(i=>({...i,complete:false,energy_kcal:null}))}
  else if(p.includes('/meal-nutrition-sources'))data=[]
  else if(p.endsWith('/manual-drafts')){submitted=body.meal;data={id:'synthetic-draft',member_id:member,version:1}}
  else if(p.endsWith('/calculate'))data={draft_version:1,calculation_id:'synthetic-calc',complete:false}
  else if(p.endsWith('/confirm')){assert.equal(body.accept_incomplete,true);record={id:'synthetic-record',source_version:1,snapshot:{meal:submitted,nutrition:{complete:false,totals:{energy_kcal:null}}}};data={review_status:'confirmed',target_ids:[record.id]}}
  else if(p.endsWith('/diet-logs/page'))data={records:record?[record]:[],next_offset:null}
  else if(p.endsWith('/vision/page'))data={jobs:[],drafts:[],jobs_next_offset:null,drafts_next_offset:null}
  else {console.error('Missing fixture:',p);await route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({detail:'Synthetic endpoint not included'})});return}
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})
 })
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message))
 try{
  await page.goto(`http://127.0.0.1:${server.address().port}/#/pages/chat/index`)
  await page.locator('.composer input').waitFor()
  await page.waitForTimeout(800)
  await page.evaluate(hash=>location.hash=hash,`/pages/scan/index?meal=lunch&date=${day}&memberId=${member}`)
  await page.getByText('从今日食谱选择 ›',{exact:true}).click()
  const dialog=page.locator('.portion-dialog');await dialog.waitFor()
  assert.equal(calls.filter(c=>c.path.endsWith('/manual-drafts')).length,0)
  assert.equal(await dialog.locator('.dish-picks .active').count(),0)
  await dialog.getByText('清蒸鱼',{exact:true}).click()
  await dialog.locator('input').fill('120')
  await page.screenshot({path:path.join(base,`${width}-select.png`),fullPage:true})
  await dialog.getByText('确认',{exact:true}).click()
  await page.getByText('仅保存已知内容，缺失营养保持未知',{exact:true}).waitFor()
  await page.waitForTimeout(650)
  await page.getByText('仅保存已知内容，缺失营养保持未知',{exact:true}).click()
  await page.getByText('保存已知内容',{exact:true}).click()
  await page.getByText('查看饮食记录 ›',{exact:true}).waitFor()
  assert.deepEqual(submitted.items.map(i=>i.name),['清蒸鱼'])
  assert.equal(submitted.items[0].grams,120);assert.equal(submitted.items[0].recipe_version_id,null);assert.equal(submitted.items[0].nutrition_source,null)
  assert.equal(submitted.meal_type,'lunch');assert.equal(submitted.eaten_at.slice(0,10),day)
  assert.equal(calls.filter(c=>c.path.endsWith('/manual-drafts')).length,1)
  assert.equal(calls.filter(c=>c.path.endsWith('/confirm')).length,1)
  assert.ok(calls.some(c=>c.path.endsWith('/diet-logs/page')))
  assert.equal(calls.some(c=>c.path.includes('daily-arrangements')||c.path.endsWith('/meal-photo-tasks')),false)
  assert.equal(await page.getByText('当前成员授权或来源已变化，请重新读取。',{exact:true}).count(),0)
  await page.screenshot({path:path.join(base,`${width}-saved.png`),fullPage:true})
  await page.getByText('查看饮食记录 ›',{exact:true}).click()
  await page.locator('.dj37').getByText('清蒸鱼',{exact:true}).waitFor()
  await page.locator('.dj37').click()
  await page.getByText('一般 · 120 g',{exact:true}).waitFor().catch(async()=>{await page.getByText('不确定 · 120 g',{exact:true}).waitFor()})
  assert.equal(await page.locator('.dj44').count(),1)
  await page.screenshot({path:path.join(base,`${width}-record.png`),fullPage:true})
  assert.deepEqual(errors,[]);results.push({width,passed:true,save_count:1,readback:true})
 }catch(e){await page.screenshot({path:path.join(base,`${width}-failure.png`),fullPage:true});console.error(await page.locator('body').innerText());throw e}
 finally{await context.close()}
}
 await fs.writeFile(path.join(base,'result.json'),JSON.stringify({passed:true,api:'synthetic',results},null,2));console.log(JSON.stringify({passed:true,results}))
}finally{await browser.close();await new Promise(r=>server.close(r))}
