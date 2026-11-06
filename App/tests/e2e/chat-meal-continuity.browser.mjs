// 编译后的 H5 使用隔离合成响应，验证餐单与对话的连续性。
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import {createRequire} from 'node:module'

const require=createRequire(import.meta.url)
const {chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright')
const root=path.resolve(process.env.CHAT_CONTINUITY_H5_BUILD)
const evidence=path.resolve(process.env.CHAT_CONTINUITY_EVIDENCE)
await fs.mkdir(evidence,{recursive:true})
const server=http.createServer(async(req,res)=>{
  try{
    const name=decodeURIComponent(new URL(req.url,'http://local').pathname)
    const file=path.resolve(root,'.'+(name==='/'?'/index.html':name))
    assert.ok(file.startsWith(root+path.sep))
    res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png','.webp':'image/webp','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream')
    res.end(await fs.readFile(file))
  }catch{res.writeHead(404);res.end()}
})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
const browser=await chromium.launch({headless:true,executablePath:process.env.CHAT_CONTINUITY_BROWSER_EXE})
const family='11111111-1111-4111-8111-111111111111'
const member='22222222-2222-4222-8222-222222222222'
const thread='33333333-3333-4333-8333-333333333333'
const planner='44444444-4444-4444-8444-444444444444'
const pending='55555555-5555-4555-8555-555555555555'
const date=new Date(Date.now()+8*3600000).toISOString().slice(0,10)
const person={id:member,healthMemberId:member,name:'我',relation:'本人',birthDate:'2000-01-01',gender:'女',height:165,weight:55,version:1,claimed:true,isSelf:true,confirmed:true,healthStatus:'none',conditions:[],goals:[],tastePreferences:[],cuisines:[],allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],doctorStatus:'none',clinicianGuidance:''}
const profile={source:'api',householdId:family,householdName:'合成家庭',familyVersion:1,usageMode:'个人使用',defaultDiners:[member],selfMemberId:member,isOwner:true,onboarded:true,completeProfile:true,members:[person]}
const meal=(meal_type,name)=>({meal_type,members:[person],source:{kind:'reference',id:planner,version:1},meal:{dishes:[{name,dish_key:meal_type+'-dish'}]}})
const results=[]
try{
  for(const scenario of ['existing-lunch','pending-plan','race-409','race-423']){
    const context=await browser.newContext({viewport:{width:390,height:844}})
    const requests=[],errors=[]
    let plan={date,status:'ready',version:1,meals:[meal('lunch','合成午餐')],pending:scenario==='existing-lunch'?{status:'running',request_id:pending}:null}
    if(scenario==='pending-plan')plan={date,status:'absent',version:0,meals:[],pending:{status:'running',request_id:pending}}
    await context.addInitScript(({family})=>localStorage.setItem('fn-session-v2:api',JSON.stringify({type:'object',data:{accountId:'1',accountName:'合成测试',householdId:family,token:'synthetic-continuity',authSource:'wechat',expiresAt:Date.now()/1000+86400,clientRevision:'continuity-test',families:[{id:family,name:'合成家庭',isOwner:true,onboardingRequired:false}]}})),{family})
    await context.route('**/api/**',async route=>{
      const req=route.request(),p=new URL(req.url()).pathname
      requests.push({path:p,method:req.method()})
      let data,status=200
      if(p.endsWith('/session/exchange'))data={code:0,data:{user:{id:1,token:'synthetic-shop'},agent_account_id:'1'}}
      else if(p.endsWith('/commerce/session'))data={code:0,data:{user:{id:1},agent_account_id:'1'}}
      else if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'合成测试'},families:[{id:family,name:'合成家庭',is_owner:true,onboarding_required:false}]}
      else if(p.endsWith('/miniapp-profile'))data=profile
      else if(p.endsWith('/configuration'))data={policy_version:'synthetic',consultation:{available:true,processor:'synthetic'},meal_plan:{available:true,processor:'synthetic'}}
      else if(p==='/api/health/v1/members')data=[{id:member,is_owner:true,scopes:['ai_use','profile_view','diet_edit']}]
      else if(p.endsWith('/readiness'))data={capabilities:{member_id:member},entries:['consultation','reference_meal_preview'].map(entry_type=>({entry_type,status:'available'}))}
      else if(p.endsWith('/consultations')&&req.method()==='POST'){
        status=201;data={member_id:member,thread_id:thread,agent_slug:'health-consultation',business_date:null,feedback_selection:null}
      }
      else if(p.endsWith('/consultations'))data={items:[{member_id:member,thread_id:thread,agent_slug:'health-consultation',business_date:null}],has_more:false,next_offset:null}
      else if(p.endsWith('/task-entries'))data={member_id:member,thread_id:planner,task_type:'reference_meal_preview',client_request_id:req.postDataJSON().client_request_id,agent_slug:'health-meal-planner',entry_status:'ready',request_submit_url:'/api/agent/runs'}
      else if(p==='/api/agent/runs'&&req.method()==='POST'){
        status=scenario==='race-409'?409:423
        plan={...plan,pending:{status:'running',request_id:pending}}
        data={detail:status===409?'饮食计划已更新，请重新读取后操作':'该日饮食计划正在生成，请读取已有任务'}
      }
      else if(p.endsWith('/history')){
        const child=p.includes(planner)
        data={thread:{id:child?planner:thread,agent_id:child?'health-meal-planner':'health-consultation'},history:[],runs:[],related_threads:[]}
      }
      else if(p.includes('/requests'))data={requests:[],queue:{status:'idle'}}
      else if(p.includes('/daily-meal-plans/'))data=plan
      else if(p.includes('/preparation'))data={status:'absent'}
      else if(p.endsWith('/daily-conversations'))data={days:[]}
      else {status=404;data={detail:'Synthetic endpoint not configured'}}
      await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
    })
    const page=await context.newPage()
    page.on('pageerror',error=>errors.push(error.message))
    try{
      await page.goto('http://127.0.0.1:'+server.address().port+'/#/pages/chat/index')
      await page.locator('.composer input').waitFor()
      await page.waitForFunction(()=>document.querySelector('.camera-button')&&!document.querySelector('.camera-button').classList.contains('uni-button-disabled')&&document.querySelector('.camera-button').getAttribute('disabled')!=='true')
      const question=scenario.startsWith('race-')?'今天晚餐吃什么？':'今天午餐吃什么？'
      await page.locator('.composer input').fill(question)
      await page.locator('.send-button[aria-label="发送"]').click()
      await page.locator('.message-row.assistant').filter({hasText:scenario==='existing-lunch'?'这是已安排的餐单。':'餐单正在生成，完成后会在这里更新。'}).waitFor()
      assert.equal(await page.locator('.message-row.user').count(),1)
      assert.equal(await page.locator('.message-issue').count(),0)
      assert.equal(await page.locator('.composer input').inputValue(),'')
      assert.equal(requests.filter(r=>r.path.endsWith('/consultations')&&r.method==='POST').length,1)
      assert.equal(requests.filter(r=>r.path==='/api/agent/runs'&&r.method==='POST').length,scenario.startsWith('race-')?1:0)
      assert.equal(await page.locator('.tm-mask').count(),0)
      if(scenario!=='existing-lunch'){
        plan={date,status:'ready',version:2,meals:[meal('lunch','更新后的合成午餐'),meal('dinner','更新后的合成晚餐')],pending:null}
        await page.locator('.message-row.assistant').filter({hasText:'这是目前已安排的餐单。'}).waitFor({timeout:12000})
        await page.locator('.message-row.assistant').getByText(scenario==='pending-plan'?'更新后的合成午餐':'更新后的合成晚餐',{exact:true}).waitFor()
      }
      assert.deepEqual(errors,[])
      await page.screenshot({path:path.join(evidence,scenario+'.png'),fullPage:true})
      results.push({scenario,passed:true,rootConversationsCreated:1,aiSubmissions:scenario.startsWith('race-')?1:0,pageErrors:errors})
    }catch(error){
      await page.screenshot({path:path.join(evidence,scenario+'-debug.png'),fullPage:true})
      console.error(JSON.stringify({scenario,requests,errors,body:(await page.locator('body').innerText()).slice(0,1800)}))
      throw error
    }finally{await context.close()}
  }
  await fs.writeFile(path.join(evidence,'result.json'),JSON.stringify(results,null,2))
  console.log(JSON.stringify(results))
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}
