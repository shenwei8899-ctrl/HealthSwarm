// Compiled H5 with synthetic API responses; the readiness request is held open.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import {createRequire} from 'node:module'
const require=createRequire(import.meta.url),{chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright')
const root=path.resolve(process.env.HISTORY_H5_BUILD),evidence=path.resolve(process.env.HISTORY_BROWSER_EVIDENCE)
await fs.mkdir(evidence,{recursive:true})
const server=http.createServer(async(req,res)=>{try{const name=decodeURIComponent(new URL(req.url,'http://local').pathname),file=path.resolve(root,'.'+(name==='/'?'/index.html':name));if(!file.startsWith(root+path.sep))throw Error('path');res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png','.webp':'image/webp'})[path.extname(file)]||'application/octet-stream');res.end(await fs.readFile(file))}catch{res.writeHead(404);res.end()}})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
const browser=await chromium.launch({headless:true,executablePath:process.env.HISTORY_CHROME_EXE})
const context=await browser.newContext({viewport:{width:390,height:844}})
const family='11111111-1111-4111-8111-111111111111',member='22222222-2222-4222-8222-222222222222',thread='33333333-3333-4333-8333-333333333333'
const child='55555555-5555-4555-8555-555555555555'
const profile={source:'api',householdId:family,householdName:'合成家庭',familyVersion:1,usageMode:'个人使用',defaultDiners:[member],selfMemberId:member,isOwner:true,onboarded:true,completeProfile:true,members:[{id:member,healthMemberId:member,name:'我',relation:'本人',birthDate:'2000-01-01',gender:'女',height:165,weight:55,version:1,claimed:true,isSelf:true,confirmed:true,healthStatus:'none',conditions:[],goals:[],tastePreferences:[],cuisines:[],allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],doctorStatus:'none',clinicianGuidance:''}]}
let hold=false,release;const gate=new Promise(resolve=>release=resolve),reads=[],writes=[],errors=[]
await context.addInitScript(({family})=>localStorage.setItem('fn-session-v2:api',JSON.stringify({type:'object',data:{accountId:'1',accountName:'合成测试',householdId:family,token:'synthetic-history-test',authSource:'wechat',expiresAt:Date.now()/1000+86400,clientRevision:'history-test',families:[{id:family,name:'合成家庭',isOwner:true,onboardingRequired:false}]}})),{family})
await context.addInitScript(({family,member,thread,child})=>{
 const prefix='fn:v2:api:1:'+family+':'
 localStorage.setItem(prefix+'conversation-index:'+thread,JSON.stringify({type:'object',data:{id:thread,memberId:member}}))
 localStorage.setItem(prefix+'conversation-threads:'+thread,JSON.stringify({type:'object',data:[{thread_id:child,memberId:member,task_type:'reference_meal_preview'}]}))
},{family,member,thread,child})
await context.route('**/api/**',async route=>{
 const req=route.request(),url=new URL(req.url()),p=url.pathname;let data,status=200
 if(req.method()==='GET')reads.push(p);else writes.push(p)
 if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'合成测试'},families:[{id:family,name:'合成家庭',is_owner:true,onboarding_required:false}]}
 else if(p.endsWith('/miniapp-profile'))data=profile
 else if(p.endsWith('/configuration'))data={policy_version:'synthetic',consultation:{available:true,processor:'synthetic'},meal_plan:{available:true,processor:'synthetic'}}
 else if(p==='/api/health/v1/members')data=[{id:member,display_name:'我',is_owner:true,scopes:['ai_use','profile_view','diet_edit']}]
 else if(p.endsWith('/readiness')){if(hold)await gate;data={capabilities:{member_id:member},entries:[{entry_type:'consultation',status:'available'}]}}
 else if(p.endsWith('/consultations'))data={items:[{thread_id:thread,member_id:member,agent_slug:'health-consultation',business_date:null,created_at:new Date().toISOString(),title:'新对话',unavailable:false}],has_more:false,next_offset:null}
 else if(p.endsWith('/consultations/directory'))data={items:[{thread_id:thread,member_id:member,agent_slug:'health-consultation',business_date:null,created_at:new Date().toISOString(),title:'浏览器合成历史问题',unavailable:false}],has_more:false,next_offset:null}
 else if(p.includes('/requests'))data={requests:[],queue:{status:'idle'}}
 else if(p.endsWith('/history'))data={thread:{id:p.includes(child)?child:thread},runs:[],related_threads:[],history:p.includes(child)?[{id:1,type:'human',content:'浏览器合成历史问题',created_at:'2026-11-03T12:00:00Z'},{id:2,type:'ai',content:'浏览器已授权历史正文',created_at:'2026-11-03T12:00:01Z'}]:[]}
 else if(p.endsWith('/daily-conversations'))data={days:[]}
 else if(p.includes('/daily-meal-plans')||p.includes('/daily-arrangements/'))data={status:'absent',version:0,meals:[]}
 else if(p.includes('/preparation'))data={status:'absent'}
 else {status=404;data={detail:'Synthetic fixture not provided'}}
 await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
})
const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message))
try{
 const ready=page.waitForResponse(response=>response.url().includes('/readiness'))
 await page.goto('http://127.0.0.1:'+server.address().port+'/#/pages/chat/index')
 await ready
 await page.locator('.history-button').waitFor();await page.waitForFunction(()=>!document.querySelector('.entry-status')?.textContent.includes('正在读取'))
 await page.locator('.history-button').click();await page.locator('.drawer-conversation').waitFor()
 assert.equal(reads.filter(p=>p.endsWith('/history')).length,0,'opening directory must not download any history')
 hold=true;await page.locator('.drawer-conversation').click()
 await page.getByText('浏览器已授权历史正文',{exact:true}).waitFor({timeout:5000})
 assert.equal(await page.getByText('正在核对续聊状态，历史记录可先阅读。',{exact:true}).isVisible(),true)
 assert.equal(await page.locator('.composer input').isDisabled(),true)
 assert.equal(reads.filter(p=>p.endsWith('/history')).length,2)
 await page.screenshot({path:path.join(evidence,'history-before-readiness.png'),fullPage:true})
 release();await page.waitForFunction(()=>!document.body.textContent.includes('正在核对续聊状态，历史记录可先阅读。'))
 assert.equal(await page.locator('.composer input').isDisabled(),false)
 assert.equal(writes.filter(p=>p.includes('/agent/runs')||p.endsWith('/task-entries')||p.endsWith('/consultations')).length,0)
 assert.deepEqual(errors,[])
 await fs.writeFile(path.join(evidence,'result.json'),JSON.stringify({passed:true,directoryHistoryReads:0,selectedHistoryReads:2,legacyTitleRecovered:true,bodyVisibleBeforeReadiness:true,sendingDisabledUntilVerified:true,businessWrites:0,pageErrors:errors},null,2))
 console.log('Browser history loading checks passed')
}catch(error){console.error(JSON.stringify({reads,writes,errors,body:(await page.locator('body').innerText()).slice(0,1800)}));await page.screenshot({path:path.join(evidence,'debug.png'),fullPage:true});throw error}finally{release();await browser.close();await new Promise(resolve=>server.close(resolve))}