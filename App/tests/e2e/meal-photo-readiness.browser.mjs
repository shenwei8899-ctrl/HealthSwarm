// Actual H5 build with synthetic APIs and a synthetic image; no cloud model is called.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import {createRequire} from 'node:module'
const require=createRequire(import.meta.url)
const {chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright')
assert.ok(process.env.MEAL_PHOTO_BROWSER_EVIDENCE&&process.env.MEAL_PHOTO_H5_BUILD,'MEAL_PHOTO_BROWSER_EVIDENCE and MEAL_PHOTO_H5_BUILD are required')
const base=path.resolve(process.env.MEAL_PHOTO_BROWSER_EVIDENCE),root=path.resolve(process.env.MEAL_PHOTO_H5_BUILD)
await fs.mkdir(base,{recursive:true})
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.png':'image/png','.jpg':'image/jpeg','.svg':'image/svg+xml'}
const server=http.createServer(async(req,res)=>{
 try{const name=decodeURIComponent(new URL(req.url,'http://local').pathname),file=path.resolve(root,'.'+(name==='/'?'/index.html':name));if(!file.startsWith(root+path.sep))throw Error('path');res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream'});res.end(await fs.readFile(file))}catch{res.writeHead(404);res.end()}
})
await new Promise(r=>server.listen(0,'127.0.0.1',r))
const browser=await chromium.launch({headless:true,executablePath:process.env.MEAL_PHOTO_BROWSER_EXE})
const context=await browser.newContext({viewport:{width:390,height:844}})
const family='11111111-1111-4111-8111-111111111111',member='22222222-2222-4222-8222-222222222222',writes=[],errors=[]
let available=false,version='v1'
await context.addInitScript(({family})=>localStorage.setItem('fn-session-v2:api',JSON.stringify({type:'object',data:{accountId:'1',accountName:'合成测试',householdId:family,token:'synthetic-token',authSource:'wechat',expiresAt:Date.now()/1000+86400,clientRevision:'synthetic',families:[{id:family,name:'合成家庭',isOwner:true,onboardingRequired:false}]}})),{family})
await context.route('**/api/**',async route=>{
 const req=route.request(),p=new URL(req.url()).pathname
 if(req.method()!=='GET')writes.push(p)
 let data
 if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'合成测试'},families:[{id:family,name:'合成家庭',is_owner:true,onboarding_required:false}]}
 else if(p.endsWith('/miniapp-profile'))data={source:'api',householdId:family,householdName:'合成家庭',familyVersion:1,usageMode:'个人使用',defaultDiners:[member],selfMemberId:member,isOwner:true,onboarded:true,completeProfile:true,members:[{id:member,name:'我',relation:'本人',birthDate:'2000-01-01',gender:'女',height:165,weight:55,version:1,claimed:true,isSelf:true,confirmed:true,healthStatus:'none',conditions:[],goals:[],tastePreferences:[],cuisines:[],allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],doctorStatus:'none',clinicianGuidance:''}]}
 else if(p==='/api/health/v1/members')data=[{id:member,display_name:'我',scopes:['diet_edit','ai_use']}]
 else if(p.endsWith('/configuration'))data={policy_version:version,meal:{available,processor:'synthetic-'+version,reason:available?null:'视觉模型价格尚未配置，请联系管理员',reason_code:available?null:'budget_price_unavailable'}}
 else if(p.endsWith('/vision/page'))data={jobs:[],drafts:[],jobs_next_offset:null,drafts_next_offset:null}
 else if(p.endsWith('/uploads'))data={upload_id:'synthetic-upload',purpose:'meal'}
 else if(p.endsWith('/processing-consents'))data={accepted:true}
 else if(p.endsWith('/meal-photo-tasks'))data={task_id:'synthetic-task',execution_status:'pending'}
 else if(p.endsWith('/vision-tasks/synthetic-task'))data={task_id:'synthetic-task',execution_status:'pending'}
 else {await route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({detail:'Synthetic endpoint not included'})});return}
 await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})
})
const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message))
try{
 await page.goto('http://127.0.0.1:'+server.address().port+'/#/pages/scan/index')
 await page.getByText('拍照记餐',{exact:true}).click()
 await page.getByText('记录这一餐',{exact:true}).waitFor()
 const chooser=page.waitForEvent('filechooser');await page.getByText('从相册选择',{exact:true}).click();await (await chooser).setFiles({name:'synthetic-meal.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64')})
 await page.getByText('视觉模型价格尚未配置，请联系管理员',{exact:true}).waitFor()
 await page.screenshot({path:path.join(base,'01-service-unavailable.png'),fullPage:true})
 const photo=page.locator('.photo-preview img');await photo.waitFor();const source=await photo.getAttribute('src')
 available=true;await page.getByText('重新检查识别服务',{exact:true}).click()
 await page.getByText('同意本次照片识别',{exact:true}).waitFor()
 assert.equal(await photo.getAttribute('src'),source)
 await page.getByText('同意本次照片识别',{exact:true}).click()
 version='v2';await page.getByText('识别照片',{exact:true}).click()
 await page.getByText('请核对当前处理方和政策后重新勾选同意',{exact:true}).waitFor()
 assert.equal(writes.filter(p=>p.endsWith('/meal-photo-tasks')).length,0)
 await page.screenshot({path:path.join(base,'02-policy-reconfirmation.png'),fullPage:true})
 await page.getByText('同意本次照片识别',{exact:true}).click()
 await page.getByText('识别照片',{exact:true}).click()
 await page.getByText('照片识别：等待识别',{exact:true}).waitFor()
 assert.equal(writes.filter(p=>p.endsWith('/processing-consents')).length,1)
 assert.equal(writes.filter(p=>p.endsWith('/meal-photo-tasks')).length,1)
 assert.deepEqual(errors,[])
 await page.screenshot({path:path.join(base,'03-task-submitted.png'),fullPage:true})
 console.log(JSON.stringify({passed:true,scenarios:['unavailable-reason','refresh-preserves-photo','policy-change-invalidates-consent','new-toggle-submits-once'],errors}))
}catch(error){await page.screenshot({path:path.join(base,'browser-failure.png'),fullPage:true});console.error(await page.locator('body').innerText());throw error}
finally{await browser.close();await new Promise(r=>server.close(r))}
