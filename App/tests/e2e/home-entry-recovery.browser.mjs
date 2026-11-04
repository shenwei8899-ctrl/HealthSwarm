// Compiled H5: automatic entry recovery, isolated meal denial and expired login.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import {createRequire} from 'node:module'
const require=createRequire(import.meta.url),{chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright')
const root=path.resolve(process.env.ENTRY_RECOVERY_H5_BUILD),evidence=path.resolve(process.env.ENTRY_RECOVERY_EVIDENCE)
await fs.mkdir(evidence,{recursive:true})
const server=http.createServer(async(req,res)=>{try{const name=decodeURIComponent(new URL(req.url,'http://local').pathname),file=path.resolve(root,'.'+(name==='/'?'/index.html':name));if(!file.startsWith(root+path.sep))throw Error('path');res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png','.webp':'image/webp'})[path.extname(file)]||'application/octet-stream');res.end(await fs.readFile(file))}catch{res.writeHead(404);res.end()}})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
const browser=await chromium.launch({headless:true,executablePath:process.env.ENTRY_RECOVERY_CHROME_EXE})
const family='11111111-1111-4111-8111-111111111111',member='22222222-2222-4222-8222-222222222222',thread='33333333-3333-4333-8333-333333333333'
const profile={source:'api',householdId:family,householdName:'合成家庭',familyVersion:1,usageMode:'个人使用',defaultDiners:[member],selfMemberId:member,isOwner:true,onboarded:true,completeProfile:true,members:[{id:member,healthMemberId:member,name:'我',relation:'本人',birthDate:'2000-01-01',gender:'女',height:165,weight:55,version:1,claimed:true,isSelf:true,confirmed:true,healthStatus:'none',conditions:[],goals:[],tastePreferences:[],cuisines:[],allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],doctorStatus:'none',clinicianGuidance:''}]}

const results=[]
try {
 for(const scenario of ['recover','meal-denied','expired','member-link-pending','member-link-recovers','service-unavailable']){
  const context=await browser.newContext({viewport:{width:390,height:844}}),errors=[],requests=[]
  let profileReads=0,mealReads=0
  await context.addInitScript(({family})=>localStorage.setItem('fn-session-v2:api',JSON.stringify({type:'object',data:{accountId:'1',accountName:'合成测试',householdId:family,token:'synthetic-entry-test',authSource:'wechat',expiresAt:Date.now()/1000+86400,clientRevision:'entry-test',families:[{id:family,name:'合成家庭',isOwner:true,onboardingRequired:false}]}})),{family})
  await context.route('**/api/**',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname;let data,status=200
   requests.push({path:p,method:req.method()})
   if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'合成测试'},families:[{id:family,name:'合成家庭',is_owner:true,onboarding_required:false}]}
   else if(p.endsWith('/miniapp-profile')){
    if(req.method()==='GET')profileReads++
    if(scenario==='expired'){status=401;data={detail:'Synthetic expired login'}}
    else if(scenario==='recover'&&profileReads===1){status=403;data={code:'synthetic_recheck',message:'Synthetic authorization changed'}}
    else {data=structuredClone(profile);if(scenario==='member-link-pending'||scenario==='member-link-recovers'&&profileReads===1)delete data.members[0].healthMemberId}
   }
   else if(p.endsWith('/configuration'))data={policy_version:'synthetic',consultation:{available:scenario!=='service-unavailable',processor:'synthetic'},meal_plan:{available:true,processor:'synthetic'}}
   else if(p==='/api/health/v1/members')data=[{id:member,display_name:'我',is_owner:true,scopes:['ai_use','profile_view','diet_edit']}]
   else if(p.endsWith('/readiness'))data={capabilities:{member_id:member},entries:[{entry_type:'consultation',status:'available'}]}
   else if(p.endsWith('/consultations'))data={items:[],has_more:false,next_offset:null}
   else if(p.includes('/requests'))data={requests:[],queue:{status:'idle'}}
   else if(p.endsWith('/history'))data={thread:{id:thread},runs:[],related_threads:[],history:[]}
   else if(p.endsWith('/daily-conversations'))data={days:[]}
   else if(p.includes('/daily-meal-plans/')){
    mealReads++
    if(scenario==='meal-denied'){status=403;data={code:'scope_denied',message:'Synthetic denied meal'}}
    else data={status:'absent',date:p.split('/').at(-1),version:0,meals:[]}
   }
   else if(p.includes('/preparation'))data={status:'absent'}
   else if(p==='/api/auth/wechat/config')data={available:false}
   else {status=404;data={detail:'Synthetic fixture not provided'}}
   await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
  })
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message))
  try{
   const expiredRead=scenario==='expired'?page.waitForResponse(r=>r.url().includes('/miniapp-profile')&&r.status()===401):null
   const coreRead=!['expired','member-link-pending','service-unavailable'].includes(scenario)?page.waitForResponse(r=>r.url().includes('/readiness')&&r.status()===200):null
   await page.goto('http://127.0.0.1:'+server.address().port+'/#/pages/chat/index')
   if(scenario==='expired'){await expiredRead;await page.waitForURL(url=>['#/','#/pages/index/index'].includes(url.hash),{timeout:10000});await page.getByText('微信登录，开始使用',{exact:true}).waitFor()}
   else if(['member-link-pending','service-unavailable'].includes(scenario)){
    await page.getByText('你好，我是家庭营养师。',{exact:true}).waitFor()
    await page.waitForFunction(()=>document.querySelector('.composer')?.textContent.includes('连接暂不可用'))
   }else{
    await page.locator('.composer input').waitFor()
    if(scenario==='recover')await page.locator('.composer input').fill('保留我正在输入的问题')
    await coreRead
    await page.waitForFunction(()=>document.querySelector('.camera-button')&&!document.querySelector('.camera-button').classList.contains('uni-button-disabled')&&document.querySelector('.camera-button').getAttribute('disabled')!=='true',{},{timeout:10000})
    if(scenario==='recover')assert.equal(await page.locator('.composer input').inputValue(),'保留我正在输入的问题')
    if(scenario==='meal-denied'){
     await page.waitForFunction(()=>document.querySelector('.camera-button')&&!document.querySelector('.camera-button').classList.contains('uni-button-disabled'))
     assert.equal(mealReads,1,'denied optional meal must not cause an immediate request loop')
    }
   }
   const text=await page.locator('body').innerText()
   assert.equal(/身份或成员授权已变化|重试连接|重新读取咨询资料|查看该成员档案/.test(text),false)
   assert.equal(await page.locator('[aria-label="咨询未完成"]').count(),0)
   assert.deepEqual(errors,[])
   assert.equal(requests.some(r=>r.path==='/api/agent/runs'),false)
   await page.screenshot({path:path.join(evidence,scenario+'.png'),fullPage:true})
   results.push({scenario,passed:true,profileReads,mealReads,loginRoute:scenario==='expired',noBusinessSubmission:true,pageErrors:errors})
  }catch(error){await page.screenshot({path:path.join(evidence,scenario+'-debug.png'),fullPage:true});console.error(JSON.stringify({scenario,requests,errors,body:(await page.locator('body').innerText()).slice(0,1500)}));throw error}
  finally{await context.close()}
 }
 await fs.writeFile(path.join(evidence,'result.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results))
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}
