// Synthetic UI verification. Native WeChat forwarding is checked separately on device.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {createRequire} from 'node:module'
const require=createRequire(import.meta.url)
const {chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright')
const root=path.resolve(process.env.INVITATION_BROWSER_BUILD||fileURLToPath(new URL('../../dist/invitations-check/h5/',import.meta.url)))
const evidence=process.env.INVITATION_BROWSER_EVIDENCE
assert.ok(evidence,'INVITATION_BROWSER_EVIDENCE is required')
const index=await fs.readFile(path.join(root,'index.html'),'utf8')
const base=index.match(/src="(\/[^"<>]*?)assets\//)?.[1]||'/'
await fs.mkdir(evidence,{recursive:true})
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.jpg':'image/jpeg','.png':'image/png','.webp':'image/webp','.svg':'image/svg+xml'}
const server=http.createServer(async(req,res)=>{
 try{
  const raw=decodeURIComponent(new URL(req.url,'http://local').pathname)
  const requested=raw.startsWith(base)?'/'+raw.slice(base.length):raw
  const file=path.resolve(root,'.'+(requested==='/'?'/index.html':requested))
  if(!file.startsWith(path.resolve(root)+path.sep)){res.writeHead(403);res.end();return}
  res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream'})
  res.end(await fs.readFile(file))
 }catch{res.writeHead(404);res.end()}
})
await new Promise(done=>server.listen(0,'127.0.0.1',done))
const origin='http://127.0.0.1:'+server.address().port
const browser=await chromium.launch({headless:true,executablePath:process.env.INVITATION_BROWSER_EXE})
const family='11111111-1111-4111-8111-111111111111',self='22222222-2222-4222-8222-222222222222',mom='33333333-3333-4333-8333-333333333333'
const code='family_'+ 'm'.repeat(40),errors=[],writes=[],readinessReads=[],mealReads=[]
const selfHealth='44444444-4444-4444-8444-444444444444',momHealth='55555555-5555-4555-8555-555555555555'
const thread='66666666-6666-4666-8666-666666666666'
let joined=false,reviewed=false,consented=false
let debugPage
const member=(id,isRecipient)=>({id,healthMemberId:id===self?selfHealth:joined?momHealth:null,name:id===mom?'妈妈':'我',relation:id===mom?(isRecipient?'本人':'妈妈'):'本人',birthDate:'1960-01-01',gender:'女',height:165,weight:55,activityLevel:'light',version:1,claimed:id===self||joined,isSelf:isRecipient?id===mom:id===self,confirmed:id===self||reviewed,
 healthStatus:'none',conditions:[],goals:['吃得均衡'],tastePreferences:['清淡'],cuisines:[],allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],doctorStatus:'none',clinicianGuidance:''})
const profile=recipient=>({source:'api',householdId:family,householdName:'我的家',familyVersion:1,usageMode:'家庭使用',defaultDiners:[self],selfMemberId:recipient?mom:self,isOwner:!recipient,onboarded:!recipient||reviewed,completeProfile:true,invitationReviewPending:recipient&&!reviewed,invitationAnalysisPending:recipient&&!consented,members:[member(self,recipient),member(mom,recipient)]})
async function context(recipient=false){
 const c=await browser.newContext({viewport:{width:390,height:844}})
 const conversation={thread_id:thread,member_id:recipient?momHealth:selfHealth,agent_slug:'health-consultation',business_date:null,feedback_selection:null}
 let conversationCreated=false
 await c.addInitScript(({family,recipient})=>{
  const account={accountId:recipient?'2':'1',accountName:'合成测试',householdId:recipient?null:family,token:recipient?'synthetic-recipient':'synthetic-owner',authSource:'wechat',expiresAt:Date.now()/1000+86400,clientRevision:'synthetic',families:recipient?[]:[{id:family,name:'我的家',isOwner:true,onboardingRequired:false}]}
  localStorage.setItem('fn-session-v2:api',JSON.stringify({type:'object',data:account}))
 },{family,recipient})
 await c.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url()),p=url.pathname
  if(url.origin!==origin){await route.abort();return}
  if(!p.startsWith('/api/')){await route.continue();return}
  const body=req.postDataJSON?.()
  let result,status=200
  if(req.method()!=='GET')writes.push({path:p,body,recipient})
  if(p==='/api/auth/wechat/session')result={wechat_authenticated:true,account:{id:recipient?2:1,name:'合成测试'},families:recipient&&!joined?[]:[{id:family,name:'我的家',is_owner:!recipient,onboarding_required:recipient&&!reviewed,invitation_review_pending:recipient&&!reviewed}]}
  else if(p.endsWith('/invitations/prepare'))result={options:[{key:mom,member_id:mom,name:'妈妈',code,expires_at:new Date(Date.now()+2*86400000).toISOString()},{key:'family',member_id:null,name:'邀请其他家人',code:'familyshare_'+ 'f'.repeat(65),expires_at:null,version:0}]}
  else if(p==='/api/family/invitations/'+code)result={kind:'member',member_name:'妈妈',family_id:family,can_accept:true,already_accepted:joined,state:joined?'already_joined':'available',sharing:['有效家庭成员可查看和维护普通健康档案','加入家庭不代表同意 AI 分析']}
  else if(p==='/api/family/join'){joined=true;result={id:family}}
  else if(p.endsWith('/miniapp-profile')){
   if(recipient&&req.method()==='POST'&&!body.action)reviewed=true
   if(recipient&&body?.action==='start_analysis'){
    assert.equal(reviewed,true)
    assert.equal(body.accepted,true)
    assert.equal(body.member_id,mom)
    assert.equal(body.expected_version,1)
    assert.equal(body.purpose,'consultation')
    assert.equal(body.processor,'合成测试服务')
    assert.equal(body.policy_version,'synthetic-policy')
    consented=true
   }
   // The older server can return 200 to automatic-open without a recipient grant.
   result=profile(recipient)
  }else if(p==='/api/health/v1/configuration')result={consultation:{available:true,processor:'合成测试服务'},meal_plan:{available:true,processor:'合成测试服务'},policy_version:'synthetic-policy'}
  else if(p==='/api/health/v1/members'){
   const id=recipient?momHealth:selfHealth
   result=[{id,display_name:recipient?'妈妈':'我',is_owner:true,scopes:recipient&&!consented?[]:['ai_use','profile_view','diet_edit']}]
  }
  else if(p.startsWith('/api/health/v1/members/')&&p.endsWith('/readiness')){
   const id=recipient?momHealth:selfHealth
   const requested=p.split('/').at(-2)
   readinessReads.push({recipient,consented,requested})
   result={capabilities:{member_id:requested},entries:[{entry_type:'consultation',...(requested!==id||recipient&&!consented?{status:'unavailable',reason_code:'missing_scopes'}:{status:'available'})}]}
  }
  else if(p.endsWith('/consultations')){
   if(req.method()==='POST'){conversationCreated=true;result=conversation}
   else result={items:conversationCreated?[conversation]:[],has_more:false,next_offset:null}
  }
  else if(p.endsWith('/history'))result={thread:{id:thread,agent_id:'health-consultation'},runs:[],related_threads:[],history:[]}
  else if(p.includes('/requests'))result={requests:[],queue:{status:'idle'}}
  else if(p.endsWith('/daily-conversations'))result={days:[]}
  else if(p.includes('/daily-meal-plans/')){mealReads.push({recipient,consented});result={status:'absent',date:p.split('/').at(-1),version:0,meals:[]}}
  else if(p.endsWith('/chat-intent'))result={route:'needs_clarification',message:'合成确认：问题已经收到。'}
  else if(p.endsWith('/invite/revoke'))result={revoked:true}
  else if(p==='/api/family/'+family)result={id:family,members:[self,mom].map(id=>({id,name:id===mom?'妈妈':'我',is_active:true,is_self:id===self,version:1,relationship_version:1,editable_fields:[],profile:{},claimed:id===self}))}
  else {status=404;result={detail:'synthetic UI endpoint not included'}}
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(result),headers:{'Access-Control-Allow-Origin':'*'}})
 })
 return c
}
try{
 const owner=await context(),page=await owner.newPage();debugPage=page;page.on('pageerror',e=>errors.push(e.message))
 await page.goto(origin+base)
 await page.waitForURL('**/pages/chat/index')
 await page.locator('.shortcut-family').click()
 await page.getByText('＋ 邀请家人',{exact:true}).waitFor({timeout:10000})
 await page.getByText('＋ 邀请家人',{exact:true}).click()
 await page.getByText('邀请谁加入家庭？',{exact:true}).waitFor()
 await page.locator('.invite-row').filter({hasText:'妈妈'}).waitFor()
 assert.equal(await page.locator('.invite-person').count(),2)
 assert.equal(await page.getByText('发送微信邀请',{exact:true}).count(),0)
 await page.screenshot({path:path.join(evidence,'01-选择邀请家人.png')})
 await page.locator('.invite-row').filter({hasText:'妈妈'}).getByText('撤销邀请',{exact:true}).click()
 await page.getByText('原邀请已撤销',{exact:true}).waitFor()
 await owner.close()
 const receiver=await context(true),incoming=await receiver.newPage();debugPage=incoming;incoming.on('pageerror',e=>errors.push(e.message))
 await incoming.goto(origin+base+'#/pages/invite/index?token='+code)
 await incoming.getByText('接受邀请，加入家庭',{exact:true}).waitFor()
 assert.equal(await incoming.locator('.invitation-card').getByText('我的家',{exact:true}).count(),0)
 assert.ok((await incoming.locator('.invitation-card').innerText()).includes('妈妈'))
 await incoming.screenshot({path:path.join(evidence,'02-接受家庭邀请.png')})
 await incoming.getByText('接受邀请，加入家庭',{exact:true}).click()
 await incoming.waitForURL('**/pages/onboarding/index')
 await incoming.getByText('先认识一下你',{exact:true}).waitFor()
 assert.ok(!reviewed)
 await incoming.screenshot({path:path.join(evidence,'03-核对本人资料.png')})
 await incoming.getByText('下一步，饮食偏好',{exact:true}).click()
 await incoming.getByText('下一步，饮食限制',{exact:true}).click()
 assert.equal(await incoming.getByText('同意并开启本人 AI 咨询（可选）',{exact:false}).count(),0)
 await incoming.getByText('保存，进入家庭',{exact:true}).click()
 await incoming.waitForFunction(()=>location.hash.includes('/pages/chat/index'))
 assert.equal(reviewed,true)
 const submission=writes.find(w=>w.recipient&&w.path.endsWith('/miniapp-profile')&&!w.body?.action)
 assert.equal(submission.body.scope,'self');assert.equal(submission.body.members.length,1)
 assert.equal(submission.body.members[0].member_id,mom);assert.equal(submission.body.analysis_consent,null)
 const consentButton=incoming.getByText('查看并确认咨询授权',{exact:true})
 await consentButton.waitFor()
 assert.equal(writes.filter(w=>w.recipient&&w.body?.action==='open_consultation').length,0)
 assert.equal(readinessReads.some(read=>read.recipient),false)
 assert.equal(await incoming.getByText('暂时无法连接，请重试',{exact:true}).count(),0)
 await incoming.screenshot({path:path.join(evidence,'04-等待本人授权.png')})
 await consentButton.click()
 await incoming.locator('.uni-modal').getByText('取消',{exact:true}).click()
 assert.equal(consented,false)
 assert.equal(writes.some(w=>w.recipient&&w.body?.action==='start_analysis'),false)
 await consentButton.click()
 const readiness=incoming.waitForResponse(response=>response.url().includes('/members/'+momHealth+'/readiness')&&response.ok())
 await incoming.locator('.uni-modal').getByText('同意继续',{exact:true}).click()
 await readiness
 assert.equal(consented,true)
 assert.equal(writes.filter(w=>w.recipient&&w.body?.action==='start_analysis').length,1)
 assert.ok(readinessReads.some(read=>read.recipient&&read.consented&&read.requested===momHealth))
 assert.equal(await consentButton.count(),0)
 const input=incoming.locator('.composer input')
 await input.fill('今天的饮食如何搭配？')
 await incoming.getByLabel('发送',{exact:true}).click()
 await incoming.getByText('合成确认：问题已经收到。',{exact:true}).waitFor({timeout:10000})
 assert.ok(writes.some(w=>w.recipient&&w.path.endsWith('/chat-intent')&&w.body?.thread_id===thread))
 await incoming.locator('.shortcut-today').click()
 await incoming.getByRole('dialog',{name:'今日餐单'}).waitFor()
 assert.ok(mealReads.some(read=>read.recipient&&read.consented))
 await incoming.screenshot({path:path.join(evidence,'05-聊天及餐单恢复.png')})
 assert.deepEqual(errors,[])
 const report={passed:true,explicitConsentWrites:1,chatReady:true,todayMenuOpened:true,nativeForwarding:'not tested in H5',screenshots:5}
 await fs.writeFile(path.join(evidence,'result.json'),JSON.stringify(report,null,2))
 console.log(JSON.stringify(report))
 await receiver.close()
}catch(error){
 if(debugPage&&!debugPage.isClosed()){
  await debugPage.screenshot({path:path.join(evidence,'debug-failure.png')})
  console.error(JSON.stringify({url:debugPage.url(),body:(await debugPage.locator('body').innerText()).slice(0,1500),errors,writes:writes.map(w=>({path:w.path,action:w.body?.action,recipient:w.recipient})),readinessReads}))
 }
 throw error
}finally{await browser.close();await new Promise(done=>server.close(done))}
