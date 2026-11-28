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
const historyRun=id(8),responses=new Map(),streams=new Set(),requests=[],errors=[]
const notice={acknowledged:true,version:'2026-11-22-v1',content_hash:'a'.repeat(64)}
let completed=false,historyStatus='',historyRequest='',holdDirectory=false,releaseDirectory
const gate=new Promise(resolve=>releaseDirectory=resolve)
const server=http.createServer(async(req,res)=>{
  if(req.url.includes('/events')){
    res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache','Connection':'keep-alive'})
    res.write(': connected\n\n')
    const stream={res,run:req.url.includes(historyRun)?historyRun:runId}
    const cursor=Number(new URL(req.url,'http://local').searchParams.get('after_seq')?.split('-')[0]||0)
    for(const [sequence,event] of responses.get(stream.run)||[])if(sequence>cursor)res.write(event)
    streams.add(stream);req.on('close',()=>streams.delete(stream));return
  }
  try{const name=decodeURIComponent(new URL(req.url,'http://local').pathname).replace(/^\/family-app\//,'/'),file=path.resolve(root,'.'+(name==='/'?'/index.html':name));assert.ok(file.startsWith(root+path.sep));res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png','.webp':'image/webp'})[path.extname(file)]||'application/octet-stream');res.end(await fs.readFile(file))}catch{res.writeHead(404);res.end()}
})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
const browser=await chromium.launch({headless:true,executablePath:process.env.HISTORY_CHROME_EXE})
const context=await browser.newContext({viewport:{width:390,height:844}})
const person={id:member,healthMemberId:member,name:'我',relation:'本人',birthDate:'2000-01-01',gender:'女',height:165,weight:55,version:1,claimed:true,isSelf:true,confirmed:true,healthStatus:'none',conditions:[],goals:[],allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],doctorStatus:'none',clinicianGuidance:''}
const profile={source:'api',householdId:family,householdName:'合成家庭',familyVersion:1,usageMode:'个人使用',defaultDiners:[member],selfMemberId:member,isOwner:true,onboarded:true,completeProfile:true,members:[person]}
await context.addInitScript(({family,member,active,notice})=>{
  const put=(key,data)=>localStorage.setItem(key,JSON.stringify({type:'object',data}))
  put('fn-session-v2:api',{accountId:'1',accountName:'合成测试',householdId:family,token:'synthetic-preview',authSource:'wechat',serviceNotice:notice,expiresAt:Date.now()/1000+86400,clientRevision:'preview-test',families:[{id:family,name:'合成家庭',isOwner:true,onboardingRequired:false}]})
  const pointer='fn:v2:api:1:'+family+':homepage-conversation'
  if(!localStorage.getItem(pointer))put(pointer,{id:active,threadId:active,memberId:member,businessDate:''})
},{family,member,active,notice})
await context.route('**/api/**',async route=>{
  const req=route.request(),p=new URL(req.url()).pathname;requests.push({method:req.method(),path:p})
  if(p.endsWith('/events'))return route.continue()
  let data,status=200
  if(p.endsWith('/session/exchange'))data={code:0,data:{user:{id:1,token:'synthetic-shop'},agent_account_id:'1'}}
  else if(p.endsWith('/commerce/session'))data={code:0,data:{user:{id:1},agent_account_id:'1'}}
  else if(p==='/api/account/service-notice')data=notice
  else if(p==='/api/service-notice')data={...notice,checkbox_text:'我已阅读并理解',sections:['服务','健康','数据'].map(title=>({title,text:'合成服务声明'}))}
  else if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,service_notice:notice,account:{id:1,name:'合成测试'},families:[{id:family,name:'合成家庭',is_owner:true,onboarding_required:false}]}
  else if(p.endsWith('/miniapp-profile'))data=profile
  else if(p.endsWith('/configuration'))data={policy_version:'synthetic',consultation:{available:true,processor:'synthetic'},meal_plan:{available:true,processor:'synthetic'}}
  else if(p==='/api/health/v1/members')data=[{id:member,is_owner:true,scopes:['ai_use','profile_view','diet_edit']}]
  else if(p.endsWith('/readiness'))data={capabilities:{member_id:member},entries:[{entry_type:'consultation',status:'available'}]}
  else if(p.endsWith('/consultations')){
    if(holdDirectory)await gate
    data={items:[active,history].map((thread_id,index)=>({thread_id,member_id:member,agent_slug:'health-consultation',business_date:null,created_at:index?'2026-11-09T01:00:00Z':'2026-11-10T01:00:00Z',title:index?'合成历史 B':'正在回复的 A',unavailable:false})),has_more:false,next_offset:null}
  }
  else if(p.endsWith('/history')){
    const isActive=p.includes(active)
    data={thread:{id:isActive?active:history,agent_id:'health-consultation'},runs:isActive&&!completed?[{request_id:requestId,status:'running'}]:[],related_threads:[],history:isActive?[{id:1,type:'human',content:'合成原问题 A',created_at:'2026-11-10T01:00:00Z'}]:[{id:2,type:'human',content:'合成历史问题 B',created_at:'2026-11-09T01:00:00Z'},{id:3,type:'ai',content:'合成历史答复 B',created_at:'2026-11-09T01:00:01Z'}]}
  }
  else if(p.includes('/requests'))data={requests:[],queue:{status:'idle'}}
  else if(p.endsWith('/tasks/'+requestId))data={request_id:requestId,member_id:member,thread_id:active,agent_slug:'health-consultation',task_type:'consultation',request_status:'dispatched',execution_status:completed?'completed':'running',run_id:runId,...(completed?{result:{result_type:'general_education_answer',scope:'general_education',answer:'合成原对话 A 的最终答复',citations:[]},final_message_id:10}:{})}
  else if(historyRequest&&p.endsWith('/tasks/'+historyRequest))data={request_id:historyRequest,member_id:member,thread_id:history,agent_slug:'health-consultation',task_type:'consultation',request_status:'dispatched',execution_status:historyStatus,run_id:historyRun}
  else if(p.endsWith('/chat-intent'))data={route:'nutrition_consultation'}
  else if(p==='/api/agent/runs'&&req.method()==='POST'){
    const input=req.postDataJSON()
    assert.equal(input.thread_id,history)
    assert.equal(input.query,'这是发给 B 的追问')
    historyRequest=input.meta.request_id;historyStatus='running'
    data={request_id:historyRequest,thread_id:history}
  }
  else if(p.endsWith('/daily-conversations'))data={days:[]}
  else if(p.includes('/daily-meal-plans')||p.includes('/daily-arrangements/'))data={status:'absent',version:0,meals:[]}
  else if(p.includes('/preparation'))data={status:'absent'}
  else{status=404;data={detail:'Synthetic endpoint not configured'}}
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
})
const browserDebug=[];const page=await context.newPage();page.on('console',m=>{if(m.type()==='error')browserDebug.push(m.text())});page.on('requestfailed',r=>browserDebug.push(r.url()+': '+r.failure()?.errorText));page.on('response',r=>{if(r.status()>=400)browserDebug.push(r.status()+': '+r.url())});page.on('pageerror',error=>errors.push(error.message))
function send(type,payload,sequence,run=runId){
  const other=run===historyRun
  const envelope={request_id:other?historyRequest:requestId,run_id:run,thread_id:other?history:active,payload}
  const event=`id: ${sequence}-0\nevent: ${type}\ndata: ${JSON.stringify(envelope)}\n\n`
  responses.set(run,[...(responses.get(run)||[]),[sequence,event]])
  for(const stream of streams)if(stream.run===run)stream.res.write(event)
}
try{
  await page.goto('http://127.0.0.1:'+server.address().port+'/family-app/#/pages/chat/index?entry=conversation')
  await page.locator('.history-button').click()
  await page.locator('.drawer-conversation[aria-label="正在回复的 A"]').click()
  await page.locator('[aria-label="停止生成"]').waitFor()
  for(let n=0;!streams.size&&n<100;n++)await new Promise(resolve=>setTimeout(resolve,30))
  assert.equal(streams.size,1)
  const a=page.locator('.drawer-conversation[aria-label="正在回复的 A"]')
  const b=page.locator('.drawer-conversation[aria-label="合成历史 B"]')
  const drawer=()=>page.locator('.history-button').click()
  const order=()=>page.locator('.drawer-conversation').evaluateAll(rows=>rows.map(row=>row.getAttribute('aria-label')))
  const composer=page.locator('.composer input')
  const waitForStream=async run=>{
    for(let n=0;n<100&&!Array.from(streams).some(stream=>stream.run===run);n++)await new Promise(resolve=>setTimeout(resolve,30))
    assert.ok(Array.from(streams).some(stream=>stream.run===run))
  }
  holdDirectory=true;await drawer()
  await page.getByText('正在更新对话…',{exact:true}).waitFor()
  await a.locator('.drawer-spinner').waitFor()
  assert.deepEqual(await order(),['正在回复的 A','合成历史 B'])
  await b.click()
  await page.getByText('合成历史答复 B',{exact:true}).waitFor()
  holdDirectory=false;releaseDirectory()
  await composer.fill('这是发给 B 的追问')
  await page.locator('.send-button').click()
  await waitForStream(historyRun)
  assert.equal(streams.size,2)
  const first='合成流式第一段。'
  send('custom',{name:'yuxi.health_answer_delta',chunk:{message_id:'answer-a',offset:0,content:first}},1)
  await drawer()
  await a.locator('.drawer-unread').waitFor()
  await b.locator('.drawer-spinner').waitFor()
  send('custom',{name:'yuxi.health_answer_delta',chunk:{message_id:'answer-b',offset:0,content:'合成 B 的流式答复。'}},1,historyRun)
  await b.locator('.drawer-unread').waitFor()
  assert.deepEqual(await order(),['正在回复的 A','合成历史 B'])
  await page.screenshot({path:path.join(evidence,'two-unread-replies.png'),fullPage:true})
  await a.click()
  await page.locator('#stream-answer').getByText(first,{exact:true}).waitFor()
  assert.equal(await page.getByText('合成历史答复 B',{exact:true}).count(),0)
  await page.waitForFunction(id=>{
    for(const name of Object.keys(localStorage).filter(key=>key.includes('conversation-reply-activity:'))){
      const item=JSON.parse(localStorage.getItem(name)).data[id]
      if(item?.length>0&&item.seen===item.length)return true
    }
    return false
  },active)
  await drawer();assert.equal(await a.locator('.drawer-unread').count(),0)
  await b.click()
  await page.locator('#stream-answer').getByText('合成 B 的流式答复。',{exact:true}).waitFor()
  await page.reload()
  await drawer();await b.click()
  await page.locator('#stream-answer').getByText('合成 B 的流式答复。',{exact:true}).waitFor()
  await waitForStream(runId)
  await drawer();assert.equal(await a.locator('.drawer-unread').count(),0)
  const second='合成流式第二段🙂。'
  send('custom',{name:'yuxi.health_answer_delta',chunk:{message_id:'answer-a',offset:Array.from(first).length,content:second}},2)
  await a.locator('.drawer-unread').waitFor()
  assert.equal(await page.getByText(second,{exact:true}).count(),0)
  await a.click()
  await page.locator('#stream-answer').getByText(first+second,{exact:true}).waitFor()
  completed=true;send('end',{},3)
  await page.getByText('合成原对话 A 的最终答复',{exact:true}).waitFor()
  assert.equal(await page.getByText('合成历史答复 B',{exact:true}).count(),0)
  historyStatus='failed';send('failed',{},2,historyRun)
  await drawer()
  await b.locator('.drawer-indicator').locator('[role="status"]').waitFor({state:'hidden'})
  assert.deepEqual(await order(),['正在回复的 A','合成历史 B'])
  assert.equal(requests.filter(r=>r.method==='POST'&&r.path==='/api/agent/runs').length,1)
  assert.deepEqual(errors,[])
  await page.screenshot({path:path.join(evidence,'returned-to-final-answer.png'),fullPage:true})
  const result={passed:true,cachedDirectoryVisibleBeforeRefresh:true,followUpDuringAnotherReply:true,simultaneousStreams:true,unreadTransitions:true,reloadRecoversStreams:true,orderPreserved:true,finalAnswerRetained:true,pageErrors:errors}
  await fs.writeFile(path.join(evidence,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result))
}catch(error){console.error(JSON.stringify({error:error.message,requests,errors,browserDebug,body:(await page.locator('body').innerText()).slice(0,2200)}));await page.screenshot({path:path.join(evidence,'debug.png'),fullPage:true});throw error}
finally{releaseDirectory();for(const stream of streams)stream.res.end();await browser.close();await new Promise(resolve=>server.close(resolve))}
