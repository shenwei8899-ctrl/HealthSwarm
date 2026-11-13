// Real compiled UI, held network responses, and synthetic account data only.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import {createRequire} from 'node:module'
import {PERSONALIZED_CHAT_PROMPT_POOL} from '../../src/services/chat-prompts.js'
const require=createRequire(import.meta.url),{chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright')
const root=path.resolve(process.env.HOME_SUGGESTIONS_BUILD),evidence=path.resolve(process.env.HOME_SUGGESTIONS_EVIDENCE)
await fs.mkdir(evidence,{recursive:true})
const server=http.createServer(async(req,res)=>{
 try{
  const name=decodeURIComponent(new URL(req.url,'http://local').pathname),file=path.resolve(root,'.'+(name==='/'?'/index.html':name))
  assert.ok(file.startsWith(root+path.sep))
  res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png','.webp':'image/webp'})[path.extname(file)]||'application/octet-stream')
  res.end(await fs.readFile(file))
 }catch{res.writeHead(404);res.end()}
})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_SUGGESTIONS_BROWSER})
const family='11111111-1111-4111-8111-111111111111',member='22222222-2222-4222-8222-222222222222',thread='33333333-3333-4333-8333-333333333333'
const profile={source:'api',householdId:family,householdName:'合成家庭',familyVersion:1,usageMode:'个人使用',defaultDiners:[member],selfMemberId:member,isOwner:true,onboarded:true,completeProfile:true,members:[{id:member,healthMemberId:member,name:'我',relation:'本人',birthDate:'2000-01-01',gender:'女',height:165,weight:55,version:1,claimed:true,isSelf:true,confirmed:true,healthStatus:'none',conditions:[],goals:[],tastePreferences:[],cuisines:[],allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],doctorStatus:'none',clinicianGuidance:''}]}
const row={thread_id:thread,member_id:member,agent_slug:'health-consultation',business_date:null,feedback_selection:null}
const results=[]
try{
 for(const scenario of ['stable-home','initial-click','return-click','personalized-family','personalized-send','personalized-goals']){
  const context=await browser.newContext({viewport:{width:390,height:844}}),requests=[],errors=[]
  const scenarioProfile=structuredClone(profile)
  const personalizedLabels=new Set(PERSONALIZED_CHAT_PROMPT_POOL.filter(p=>scenario==='personalized-goals'?['salt','sugar','fat'].includes(p.topic):p.topic==='hypertension').map(p=>p.text))
  if(scenario==='personalized-goals'){
   scenarioProfile.members[0].goals=['控压','控糖'];scenarioProfile.members[0].tastePreferences=['少油']
  }else if(scenario.startsWith('personalized')){
   scenarioProfile.usageMode='家庭使用'
   scenarioProfile.members.push({...structuredClone(profile.members[0]),id:'22222222-2222-4222-8222-222222222223',healthMemberId:null,name:'妈妈',relation:'母亲',isSelf:false,claimed:false,healthStatus:'set',conditions:['高血压']})
  }
  let hold=true,release,created=false
  let gate=new Promise(resolve=>release=resolve)
  await context.addInitScript(({family})=>localStorage.setItem('fn-session-v2:api',JSON.stringify({type:'object',data:{accountId:'1',accountName:'合成测试',householdId:family,token:'synthetic-home-test',authSource:'wechat',expiresAt:Date.now()/1000+86400,clientRevision:'home-test',families:[{id:family,name:'合成家庭',isOwner:true,onboardingRequired:false}]}})),{family})
  await context.route('**/api/**',async route=>{
   const request=route.request(),p=new URL(request.url()).pathname,method=request.method();requests.push({path:p,method,body:method==='POST'?request.postDataJSON():null})
   let data,status=200
   if(p.endsWith('/session/exchange'))data={code:0,data:{user:{id:1,token:'synthetic-shop'},agent_account_id:'1'}}
   else if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'合成测试'},families:[{id:family,name:'合成家庭',is_owner:true,onboarding_required:false}]}
   else if(p.endsWith('/miniapp-profile')){if(method==='GET'&&hold)await gate;data=scenarioProfile}
   else if(p.endsWith('/configuration'))data={policy_version:'synthetic',consultation:{available:true,processor:'synthetic'},meal_plan:{available:true,processor:'synthetic'}}
   else if(p==='/api/health/v1/members')data=[{id:member,display_name:'我',is_owner:true,scopes:['ai_use','profile_view','diet_edit']}]
   else if(p.endsWith('/readiness'))data={capabilities:{member_id:member},entries:[{entry_type:'consultation',status:'available'}]}
   else if(p.endsWith('/consultations')){if(method==='POST'){created=true;data=row}else data={items:created?[row]:[],has_more:false,next_offset:null}}
   else if(p.includes('/requests'))data={requests:[],queue:{status:'idle'}}
   else if(p.endsWith('/history'))data={thread:{id:thread,agent_id:'health-consultation'},runs:[],related_threads:[],history:[]}
   else if(p.endsWith('/chat-intent'))data={route:'needs_clarification',message:'合成确认：问题已经收到。'}
   else if(p.endsWith('/daily-conversations'))data={days:[]}
   else if(p.includes('/daily-meal-plans/'))data={status:'absent',date:p.split('/').at(-1),version:0,meals:[]}
   else if(p.includes('/preparation'))data={status:'absent'}
   else {status=404;data={detail:'Synthetic fixture not provided'}}
   await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
  })
  const page=await context.newPage();page.setDefaultTimeout(8000);page.on('pageerror',error=>errors.push(error.message))
  const cards=page.locator('#chat-welcome-layer .prompt-grid > *'),shuffle=page.locator('#chat-welcome-layer .shuffle-prompts')
  const clickQuestion=async()=>{
   let card
   for(let i=0;i<10;i++){
    card=cards.filter({hasText:/^(?!.*(?:看看|查看)).+/}).first()
    if(await card.count())break
    await shuffle.click()
   }
   const text=await card.innerText();await card.click()
   await page.locator('.message-row.user').filter({hasText:text}).waitFor({timeout:2000})
   assert.equal(requests.filter(r=>r.path.endsWith('/chat-intent')).length,0)
   return text
  }
  try{
   await page.goto('http://127.0.0.1:'+server.address().port+'/#/pages/chat/index')
   await cards.nth(3).waitFor({timeout:5000})
   assert.equal(await cards.count(),4)
   for(const card of await cards.all())assert.equal((await card.getAttribute('class')).includes('uni-button-disabled'),false)
   assert.equal(await page.locator('.composer .uni-input-placeholder').innerText(),'有问题尽管问我')
   const before=requests.length,old=await cards.allTextContents();await shuffle.click()
   assert.equal(requests.length,before)
   assert.ok((await cards.allTextContents()).every(text=>!old.includes(text)))
   await page.screenshot({path:path.join(evidence,scenario+'-before-ready.png'),fullPage:true})
   if(scenario==='stable-home'||scenario.startsWith('personalized')){
    await page.evaluate(()=>window.homeLayer=document.querySelector('#chat-welcome-layer'))
    const ready=page.waitForResponse(r=>r.url().includes('/readiness'));hold=false;release();await ready
    await page.waitForFunction(()=>document.querySelector('.camera-button')&&!document.querySelector('.camera-button').classList.contains('uni-button-disabled'))
    assert.equal(await page.evaluate(()=>window.homeLayer===document.querySelector('#chat-welcome-layer')),true)
    if(scenario.startsWith('personalized')){
     assert.equal((await cards.allTextContents()).filter(text=>personalizedLabels.has(text)).length,3)
     const previous=await cards.allTextContents(),requestCount=requests.length
     await shuffle.click()
     assert.equal(requests.length,requestCount)
     assert.equal((await cards.allTextContents()).filter(text=>personalizedLabels.has(text)).length,3)
     assert.ok((await cards.allTextContents()).every(text=>!previous.includes(text)))
     await page.screenshot({path:path.join(evidence,scenario+'-personalized.png'),fullPage:true})
     if(scenario==='personalized-goals'){
      for(const width of [320,375,390,430]){
       await page.setViewportSize({width,height:844})
       const fits=await cards.evaluateAll(buttons=>buttons.every(button=>{
        const range=document.createRange();range.selectNodeContents(button)
        const text=range.getBoundingClientRect(),card=button.getBoundingClientRect()
        return range.getClientRects().length===1&&text.top>=card.top-1&&text.bottom<=card.bottom+1&&text.left>=card.left-1&&text.right<=card.right+1
       }))
       assert.ok(fits,'question text must fit on one line in the '+width+'px cards')
       await page.screenshot({path:path.join(evidence,scenario+'-'+width+'.png'),fullPage:true})
      }
     }else if(scenario==='personalized-send'){
      const index=(await cards.allTextContents()).findIndex(text=>personalizedLabels.has(text))
      const label=await cards.nth(index).innerText()
      await cards.nth(index).click()
      await page.getByText('合成确认：问题已经收到。',{exact:true}).waitFor()
      const sends=requests.filter(r=>r.path.endsWith('/chat-intent'))
      assert.equal(sends.length,1)
      assert.equal(sends[0].body.text,label)
      assert.deepEqual(await page.locator('.message-row.user .bubble').allTextContents(),[label])
     }else{
      await page.locator('.shortcut-family').click();await page.waitForURL(/pages\/profile\/index/)
      await page.getByText('合成家庭',{exact:true}).first().waitFor()
      scenarioProfile.members[1].healthStatus='none'
      await page.goBack();await cards.nth(3).waitFor()
      await page.waitForFunction(labels=>![...document.querySelectorAll('#chat-welcome-layer .prompt-grid > *')].some(card=>labels.includes(card.textContent)),[...personalizedLabels])
      assert.equal(await cards.count(),4)
     }
    }
   }else{
    if(scenario==='return-click'){
     const ready=page.waitForResponse(r=>r.url().includes('/readiness'));hold=false;release();await ready
     await page.waitForFunction(()=>document.querySelector('.camera-button')&&!document.querySelector('.camera-button').classList.contains('uni-button-disabled'))
     await page.locator('.shortcut-family').click();await page.waitForURL(/pages\/profile\/index/)
     await page.getByText('合成家庭',{exact:true}).first().waitFor()
     hold=true;gate=new Promise(resolve=>release=resolve)
     const returnRead=page.waitForRequest(r=>r.url().includes('/miniapp-profile')&&r.method()==='GET')
     await page.goBack();await returnRead;await cards.nth(3).waitFor()
    }
    const reads=requests.filter(r=>r.path.endsWith('/miniapp-profile')&&r.method==='GET').length
    await clickQuestion();hold=false;release()
    await page.getByText('合成确认：问题已经收到。',{exact:true}).waitFor({timeout:10000})
    assert.equal(requests.filter(r=>r.path.endsWith('/chat-intent')).length,1)
    assert.equal(requests.filter(r=>r.path.endsWith('/miniapp-profile')&&r.method==='GET').length,reads)
   }
   assert.deepEqual(errors,[])
   assert.equal(requests.some(r=>r.path==='/api/agent/runs'),false)
   results.push({scenario,passed:true,pageErrors:errors})
  }catch(error){await page.screenshot({path:path.join(evidence,scenario+'-debug.png'),fullPage:true});console.error(JSON.stringify({scenario,requests,errors,body:(await page.locator('body').innerText()).slice(0,1800)}));throw error}
  finally{hold=false;release();await context.close()}
 }
 await fs.writeFile(path.join(evidence,'result.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results))
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}
