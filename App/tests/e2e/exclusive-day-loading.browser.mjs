import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import {createHash} from 'node:crypto'
import path from 'node:path'
import http from 'node:http'
import {createRequire} from 'node:module'
const require=createRequire(import.meta.url)
const {chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright')
const evidence=path.resolve(process.env.PLAN_BROWSE_EVIDENCE),root=path.resolve(process.env.PLAN_BROWSE_H5)
const indexModule=(await fs.readFile(path.join(root,'index.html'),'utf8')).match(/src="([^"]+\.js)"/)[1]
await fs.mkdir(evidence,{recursive:true})
const server=http.createServer(async(req,res)=>{try{const pathname=decodeURIComponent(req.url.split('?')[0]).replace(/^\/family-app\//,'/'),file=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname));assert.ok(file.startsWith(root+path.sep));res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream');res.end(await fs.readFile(file))}catch{res.writeHead(404);res.end()}})
await new Promise(ok=>server.listen(0,'127.0.0.1',ok))
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAN_BROWSE_BROWSER})
const origin='http://127.0.0.1:'+server.address().port,family='11111111-1111-4111-8111-111111111111',group='77777777-7777-4777-8777-777777777777',results=[]
let lastPage,diagnostic
try{
 for(const width of [320,390,430]){
  const context=await browser.newContext({viewport:{width,height:844}}),page=await context.newPage(),errors=[],calls=[]
  lastPage=page;diagnostic={errors,calls}
  let failThird=true,denied=false,directoryWait=0,firstRelease
  const firstGate=new Promise(resolve=>firstRelease=resolve)
  page.on('pageerror',e=>errors.push(e.message))
  await context.addInitScript(({family})=>localStorage.setItem('fn-session-v2:api',JSON.stringify({type:'object',data:{accountId:'1',householdId:family,token:'synthetic-test',clientRevision:'browse-entry',authSource:'wechat',families:[{id:family,name:'合成家庭',isOwner:true,onboardingRequired:false}],expiresAt:Date.now()/1000+86400}})),{family})
  await context.route('**/api/**',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname;let data={},status=200
   calls.push(p+url.search)
   if(p.includes('/exclusive-plans/'))assert.equal(req.method(),'GET','浏览计划不能发起写请求')
   if(p.endsWith('/commerce/session/exchange'))data={code:0,data:{agent_account_id:1,user:{id:1,token:'synthetic-commerce'},identity_namespace:'synthetic'}}
   else if(p==='/api/service-notice')data={version:'synthetic',content_hash:'a'.repeat(64),title:'合成声明',sections:[],checkbox_text:'合成确认'}
   else if(p==='/api/account/service-notice')data={version:'synthetic',acknowledged:true}
   else if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'我'},families:[{id:family,name:'合成家庭',is_owner:true,onboarding_required:false}]}
   else if(p.endsWith('/miniapp-profile'))data={source:'api',householdId:family,householdName:'合成家庭',completeProfile:true,onboarded:true,members:[],defaultDiners:[]}
   else if(p==='/api/family')data=[{id:family,name:'合成家庭',is_owner:true}]
   else if(p.endsWith('/directory')){
    if(directoryWait)await new Promise(r=>setTimeout(r,directoryWait))
    if(denied){status=403;data={detail:'合成授权已撤销'}}
    else data={group_id:group,tier_code:'standard',tier_name:'标准型',days:Array.from({length:21},(_,i)=>({day_no:i+1,plan_date:'2026-11-'+String(i+1).padStart(2,'0'),available:true,content_version:'c'+i,version:'s'+i}))}
   }
   else if(/\/days\/\d+$/.test(p)){
    const n=Number(p.split('/').at(-1))
    if(n===1)await firstGate
    if(n===3&&failThird){failThird=false;status=503;data={detail:'当天原谱暂不可用'}}
    else data={day_no:n,version:String(n).repeat(64),unchanged:url.searchParams.has('known_version'),day:{day_no:n,meals:['breakfast','lunch','dinner'].map(meal_type=>({id:meal_type+n,meal_type,recipe_name:`第${n}天${meal_type==='lunch'?'午餐':'餐品'}`,ingredients:['大米100克','菠菜适量'],steps:['加热至熟'],source:{file_id:'f'+n},recipe_snapshot:{}}))}}
   }
   else if(p.endsWith('/images'))data={status:'ready',images:[]}
   else {status=404;data={detail:'未模拟 '+p}}
   await route.fulfill({status,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'},contentType:'application/json',body:JSON.stringify(data)})
  })
  const selector='.detail-screen:visible'
  const current=()=>page.locator(selector)
  await page.goto(origin+'/family-app/#/pages/index/index')
  await page.waitForTimeout(1000)
  await page.evaluate(async({indexModule,group})=>{const app=await import(indexModule);window.__browseNavigate=url=>app.Z({url});window.__browseBack=()=>app.Y();window.__browseNavigate('/pages/exclusive-plans/detail?group_id='+group+'&tier=standard')},{indexModule,group})
  await current().locator('.day-tabs uni-button').first().waitFor()
  assert.equal(await current().locator('.day-tabs uni-button').count(),21)
  assert.equal(await current().locator('.dish-name').count(),0)
  assert.equal(await current().locator('.plan-primary').getAttribute('disabled'),'true')
  assert.equal(calls.filter(p=>/\/days\/\d+/.test(p)).length,1)
  await page.screenshot({path:path.join(evidence,'directory-'+width+'.png')})
  firstRelease()
  await current().locator('.dish-name').first().waitFor()
  await page.waitForTimeout(650)
  assert.deepEqual(calls.filter(p=>/\/days\/\d+/.test(p)).map(p=>Number(p.match(/days\/(\d+)/)[1])),[1,2])
  await current().locator('#plan-day-3').click()
  await current().getByText('重试当天菜谱',{exact:true}).waitFor()
  assert.equal(await current().locator('.day-tabs uni-button').count(),21)
  await current().getByText('重试当天菜谱',{exact:true}).click()
  await current().getByText('第3天餐品',{exact:true}).waitFor()
  await current().locator('#plan-meal-lunch').click()
  await current().getByText('第3天午餐',{exact:true}).waitFor()
  await page.screenshot({path:path.join(evidence,'day-three-'+width+'.png')})
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
  directoryWait=1200
  await page.evaluate(()=>window.__browseNavigate('/pages/settings/privacy'))
  await page.waitForTimeout(300)
  await page.evaluate(()=>window.__browseBack())
  await current().getByText('第3天午餐',{exact:true}).waitFor()
  assert.equal(await current().locator('#plan-day-3').getAttribute('aria-pressed'),'true')
  assert.equal(await current().locator('#plan-meal-lunch').getAttribute('aria-pressed'),'true')
  assert.equal(await current().locator('.plan-primary').getAttribute('disabled'),'true')
  await page.screenshot({path:path.join(evidence,'return-preserved-'+width+'.png')})
  await page.waitForFunction(()=>!document.querySelector('.detail-screen .plan-primary')?.hasAttribute('disabled'))
  assert.ok(calls.some(p=>p.includes('/days/3?known_version=')))
  denied=true;directoryWait=0
  await page.evaluate(()=>window.__browseNavigate('/pages/settings/privacy'));await page.waitForTimeout(300);await page.evaluate(()=>window.__browseBack())
  await current().getByText('合成授权已撤销',{exact:true}).waitFor()
  assert.equal(await current().locator('.dish-name').count(),0)
  assert.equal(await current().locator('.day-tabs').count(),0)
  assert.deepEqual(errors,[])
  results.push({width,directoryBeforeDay:true,oneDayPrefetch:true,dayRetry:true,returnPreservesMeal:true,conditionalRead:true,permissionClearsContent:true,calls,errors})
  await context.close()
 }
 await fs.writeFile(path.join(evidence,'browser-result.json'),JSON.stringify({status:'passed',build_dir:root,index_sha256:createHash('sha256').update(await fs.readFile(path.join(root,'index.html'))).digest('hex'),results},null,2))
 console.log(JSON.stringify(results.map(({calls,...r})=>r)))
}catch(error){if(lastPage&&!lastPage.isClosed()){await lastPage.screenshot({path:path.join(evidence,'failure.png')});await fs.writeFile(path.join(evidence,'failure.json'),JSON.stringify({...diagnostic,url:lastPage.url(),body:await lastPage.locator('body').innerText()},null,2))}throw error}finally{await browser.close();server.close()}
