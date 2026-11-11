// 编译后的页面与真实分块 HTTP 连接；业务响应全部为合成数据。
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import { createRequire } from 'node:module'
const require=createRequire(import.meta.url),{chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright')
const root=path.resolve(process.env.HISTORY_H5_BUILD),evidence=path.resolve(process.env.HISTORY_BROWSER_EVIDENCE)
await fs.mkdir(evidence,{recursive:true})
const id=n=>`${String(n).padStart(8,'0')}-1111-4111-8111-111111111111`
const family=id(1),member=id(2),active=id(3),history=id(4),requestId=id(5),runId=id(6)
const streams=new Set(),requests=[],errors=[]
let closedStreams=0,completed=false,holdDirectory=false,releaseDirectory
const gate=new Promise(resolve=>releaseDirectory=resolve)
const server=http.createServer(async(req,res)=>{
  if(req.url.includes('/events')){
    res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache','Connection':'keep-alive'})
    res.write(': connected\n\n');streams.add(res);req.on('close',()=>{streams.delete(res);closedStreams++});return
  }
  try{const name=decodeURIComponent(new URL(req.url,'http://local').pathname),file=path.resolve(root,'.'+(name==='/'?'/index.html':name));assert.ok(file.startsWith(root+path.sep));res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png','.webp':'image/webp'})[path.extname(file)]||'application/octet-stream');res.end(await fs.readFile(file))}catch{res.writeHead(404);res.end()}
})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
const browser=await chromium.launch({headless:true,executablePath:process.env.HISTORY_CHROME_EXE})
const context=await browser.newContext({viewport:{width:390,height:844}})
const person={id:member,healthMemberId:member,name:'我',relation:'本人',birthDate:'2000-01-01',gender:'女',height:165,weight:55,version:1,claimed:true,isSelf:true,confirmed:true,healthStatus:'none',conditions:[],goals:[],allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],doctorStatus:'none',clinicianGuidance:''}
const profile={source:'api',householdId:family,householdName:'合成家庭',familyVersion:1,usageMode:'个人使用',defaultDiners:[member],selfMemberId:member,isOwner:true,onboarded:true,completeProfile:true,members:[person]}
await context.addInitScript(({family,member,active})=>{
  const put=(key,data)=>localStorage.setItem(key,JSON.stringify({type:'object',data}))
  put('fn-session-v2:api',{accountId:'1',accountName:'合成测试',householdId:family,token:'synthetic-preview',authSource:'wechat',expiresAt:Date.now()/1000+86400,clientRevision:'preview-test',families:[{id:family,name:'合成家庭',isOwner:true,onboardingRequired:false}]})
  put('fn:v2:api:1:'+family+':homepage-conversation',{id:active,threadId:active,memberId:member,businessDate:''})
},{family,member,active})
await context.route('**/api/**',async route=>{
  const req=route.request(),p=new URL(req.url()).pathname;requests.push({method:req.method(),path:p})
  if(p.endsWith('/events'))return route.continue()
  let data,status=200
  if(p.endsWith('/session/exchange'))data={code:0,data:{user:{id:1,token:'synthetic-shop'},agent_account_id:'1'}}
  else if(p.endsWith('/commerce/session'))data={code:0,data:{user:{id:1},agent_account_id:'1'}}
  else if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'合成测试'},families:[{id:family,name:'合成家庭',is_owner:true,onboarding_required:false}]}
  else if(p.endsWith('/miniapp-profile'))data=profile
  else if(p.endsWith('/configuration'))data={policy_version:'synthetic',consultation:{available:true,processor:'synthetic'},meal_plan:{available:true,processor:'synthetic'}}
  else if(p==='/api/health/v1/members')data=[{id:member,is_owner:true,scopes:['ai_use','profile_view','diet_edit']}]
  else if(p.endsWith('/readiness'))data={capabilities:{member_id:member},entries:[{entry_type:'consultation',status:'available'}]}
  else if(p.endsWith('/consultations')){
    if(holdDirectory)await gate
    data={items:[active,history].map((thread_id,index)=>({thread_id,member_id:member,agent_slug:'health-consultation',business_date:null,created_at:'2026-11-10T01:00:00Z',title:index?'合成历史 B':'正在回复的 A',unavailable:false})),has_more:false,next_offset:null}
  }
  else if(p.endsWith('/history')){
    const isActive=p.includes(active)
    data={thread:{id:isActive?active:history,agent_id:'health-consultation'},runs:isActive?[{request_id:requestId,status:'running'}]:[],related_threads:[],history:isActive?[{id:1,type:'human',content:'合成原问题 A',created_at:'2026-11-10T01:00:00Z'}]:[{id:2,type:'human',content:'合成历史问题 B',created_at:'2026-11-09T01:00:00Z'},{id:3,type:'ai',content:'合成历史答复 B',created_at:'2026-11-09T01:00:01Z'},{id:4,type:'ai',content:JSON.stringify({result_type:'meal_plan_preview',preview_id:id(7),meals:[{meal_type:'lunch',dishes:[{name:'合成历史餐单',planned_grams:100}]}]}),created_at:'2026-11-09T01:00:02Z'}]}
  }
  else if(p.includes('/requests'))data={requests:[],queue:{status:'idle'}}
  else if(p.endsWith('/tasks/'+requestId))data={request_id:requestId,member_id:member,thread_id:active,agent_slug:'health-consultation',task_type:'consultation',request_status:'dispatched',execution_status:completed?'completed':'running',run_id:runId,...(completed?{result:{result_type:'general_education_answer',scope:'general_education',answer:'合成原对话 A 的最终答复',citations:[]},final_message_id:10}:{})}
  else if(p.endsWith('/daily-conversations'))data={days:[]}
  else if(p.includes('/daily-meal-plans')||p.includes('/daily-arrangements/'))data={status:'absent',version:0,meals:[]}
  else if(p.includes('/preparation'))data={status:'absent'}
  else{status=404;data={detail:'Synthetic endpoint not configured'}}
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
})
const browserDebug=[];const page=await context.newPage();page.on('console',m=>{if(m.type()==='error')browserDebug.push(m.text())});page.on('requestfailed',r=>browserDebug.push(r.url()+': '+r.failure()?.errorText));page.on('response',r=>{if(r.status()>=400)browserDebug.push(r.status()+': '+r.url())});page.on('pageerror',error=>errors.push(error.message))
const send=(type,payload,sequence)=>{for(const stream of streams)stream.write(`id: ${sequence}-0\nevent: ${type}\ndata: ${JSON.stringify({request_id:requestId,run_id:runId,thread_id:active,payload})}\n\n`)}
try{
  await page.goto('http://127.0.0.1:'+server.address().port+'/#/pages/chat/index?entry=conversation')
  await page.locator('.history-button').click()
  await page.locator('.drawer-conversation[aria-label="正在回复的 A"]').click()
  await page.locator('[aria-label="停止生成"]').waitFor()
  for(let n=0;!streams.size&&n<100;n++)await new Promise(resolve=>setTimeout(resolve,30))
  assert.equal(streams.size,1)
  const beforeBrowsing=requests.length
  send('custom',{name:'yuxi.health_answer_delta',chunk:{message_id:'answer-a',offset:0,content:'合成流式第一段。'}},1)
  await page.locator('#stream-answer').getByText('合成流式第一段。',{exact:true}).waitFor()
  await page.locator('.history-button').click();await page.locator('.drawer-conversation[aria-label="合成历史 B"]').waitFor()
  assert.equal(await page.locator('.drawer-conversation[aria-label="合成历史 B"]').isEnabled(),true)
  await page.locator('.drawer-backdrop').click({position:{x:385,y:400}})
  holdDirectory=true;await page.locator('.history-button').click()
  await page.getByText('正在更新对话…',{exact:true}).waitFor()
  assert.equal(await page.locator('.drawer-conversation').count(),2)
  await page.locator('.drawer-conversation[aria-label="合成历史 B"]').click()
  await page.locator('.history-preview').getByText('合成历史答复 B',{exact:true}).waitFor()
  assert.equal(await page.locator('.history-preview').getByText('保存这份餐单',{exact:true}).count(),0)
  assert.equal(closedStreams,0);assert.equal(streams.size,1)
  send('custom',{name:'yuxi.health_answer_delta',chunk:{message_id:'answer-a',offset:Array.from('合成流式第一段。').length,content:'合成流式第二段。'}},2)
  await page.waitForFunction(()=>document.querySelector('#stream-answer')?.textContent.includes('合成流式第二段。'))
  await page.screenshot({path:path.join(evidence,'preview-during-reply.png'),fullPage:true})
  completed=true;send('end',{},3)
  await page.waitForFunction(()=>document.body.textContent.includes('合成原对话 A 的最终答复'))
  assert.equal(await page.locator('.history-preview').isVisible(),true)
  await page.locator('[aria-label="返回当前对话"]').click()
  await page.getByText('合成原对话 A 的最终答复',{exact:true}).waitFor()
  assert.equal(await page.getByText('合成历史答复 B',{exact:true}).count(),0)
  assert.equal(requests.slice(beforeBrowsing).filter(r=>r.method!=='GET').length,0);assert.deepEqual(errors,[])
  await page.screenshot({path:path.join(evidence,'returned-to-final-answer.png'),fullPage:true})
  const result={passed:true,cachedDirectoryVisibleBeforeRefresh:true,previewReadableDuringRealHttpStream:true,streamContinuesUnderPreview:true,finalAnswerRetained:true,readOnlyCards:true,businessWrites:0,pageErrors:errors}
  await fs.writeFile(path.join(evidence,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result))
}catch(error){console.error(JSON.stringify({error:error.message,requests,errors,browserDebug,body:(await page.locator('body').innerText()).slice(0,2200)}));await page.screenshot({path:path.join(evidence,'debug.png'),fullPage:true});throw error}
finally{releaseDirectory();for(const stream of streams)stream.end();await browser.close();await new Promise(resolve=>server.close(resolve))}
