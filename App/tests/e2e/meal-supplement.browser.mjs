// Actual built page, synthetic APIs and a generated test image; no cloud model or production data.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import {createRequire} from 'node:module'
const require=createRequire(import.meta.url)
const {chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright')
const root=path.resolve(process.env.MEAL_SUPPLEMENT_H5),out=path.resolve(process.env.MEAL_SUPPLEMENT_EVIDENCE)
await fs.mkdir(out,{recursive:true})
const server=http.createServer(async(req,res)=>{try{const url=new URL(req.url,'http://local'),file=path.resolve(root,'.'+(url.pathname==='/'?'/index.html':decodeURIComponent(url.pathname)));if(!file.startsWith(root+path.sep))throw Error('path');res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png'})[path.extname(file)]||'application/octet-stream');res.end(await fs.readFile(file))}catch{res.writeHead(404);res.end()}})
await new Promise(r=>server.listen(0,'127.0.0.1',r))
const browser=await chromium.launch({headless:true,executablePath:process.env.MEAL_SUPPLEMENT_BROWSER})
const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:2})
const family='11111111-1111-4111-8111-111111111111',member='22222222-2222-4222-8222-222222222222'
const firstDraft='33333333-3333-4333-8333-333333333333',nextDraft='44444444-4444-4444-8444-444444444444',recordId='55555555-5555-4555-8555-555555555555'
const fish={item_id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',name:'清蒸鱼',grams:150,share_ratio:1,portion_source:'manual',food_id:'fish',locations:[],excluded:false,uncertainties:[]}
const rice={item_id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',name:'米饭',grams:120,share_ratio:1,portion_source:'manual',food_id:'rice',locations:[],excluded:false,uncertainties:[]}
const secondFish={...fish,item_id:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',grams:80}
let payload={meal_type:'dinner',eaten_at:'2026-11-04T18:00:00+08:00',items:[fish],photos:[]},version=1,record=null,taskCount=0,failUpload=false
const writes=[],errors=[]
const draft=(id=firstDraft)=>({id,kind:'meal',member_id:member,version,review_status:'pending_confirmation',payload:id===firstDraft?payload:{...payload,items:[rice,secondFish],photos:[]}})
const foodName={fish:'清蒸鱼',rice:'米饭',broccoli:'西兰花',egg:'鸡蛋'}
function nutrition(meal){const entries=meal.items.filter(i=>!i.excluded).map(i=>{const n=i.name==='清蒸鱼'?1.1:i.name==='米饭'?1.3:i.name==='鸡蛋'?1.4:.35;return {item_id:i.item_id,nutrients:{energy_kcal:i.grams==null?null:Math.round(i.grams*n),protein_g:i.grams==null?null:Math.round(i.grams*.15),carbohydrate_g:i.grams==null?null:Math.round(i.grams*.2),fat_g:i.grams==null?null:Math.round(i.grams*.04)}}});return {complete:entries.every(i=>i.nutrients.energy_kcal!=null),items:entries,totals:Object.fromEntries(['energy_kcal','protein_g','carbohydrate_g','fat_g'].map(k=>[k,entries.reduce((n,i)=>n+(i.nutrients[k]||0),0)])),sources:[]}}
await context.addInitScript(({family,member,fish,firstDraft,payload})=>{
 const put=(key,data)=>{if(!localStorage.getItem(key))localStorage.setItem(key,JSON.stringify({type:'object',data}))}
 put('fn-session-v2:api',{accountId:'1',accountName:'我',householdId:family,token:'synthetic',authSource:'wechat',expiresAt:Date.now()/1000+86400,clientRevision:'test',families:[{id:family,name:'演示家庭',isOwner:true,onboardingRequired:false}]})
 put(`fn:v2:api:1:${family}:cloud-capture-ui`,{people:[{memberId:member,name:'我',selected:true,dishes:['清蒸鱼'],portion:'一般',grams:'',noneConfirmed:false}],dishes:[{...fish,portion_confirmed:true,source_basis:'per100g'}],captureScope:'单人餐盘',mealType:'dinner',date:'2026-11-04',time:'18:00',oil:'不确定',photo:'',source:'照片识别后核对',saved:null,origin:{memberId:member,draft:{id:firstDraft,version:1},meal:payload},manualDraft:null})
},{family,member,fish,firstDraft,payload})
await context.route('**/api/**',async route=>{
 const req=route.request(),p=new URL(req.url()).pathname,body=(req.headers()['content-type']||'').includes('application/json')?(req.postDataJSON()||{}):{},method=req.method();if(method!=='GET')writes.push({path:p,method,body})
 let data,status=200
 if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'我'},families:[{id:family,name:'演示家庭',is_owner:true,onboarding_required:false}]}
 else if(p.endsWith('/miniapp-profile'))data={source:'api',householdId:family,householdName:'演示家庭',familyVersion:1,usageMode:'个人使用',defaultDiners:[member],selfMemberId:member,isOwner:true,onboarded:true,completeProfile:true,members:[{id:member,name:'我',relation:'本人',birthDate:'2000-01-01',gender:'女',height:165,weight:55,version:1,claimed:true,isSelf:true,confirmed:true,healthStatus:'none',conditions:[],goals:[],tastePreferences:[],cuisines:[],allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],doctorStatus:'none',clinicianGuidance:''}]}
 else if(p.endsWith('/members'))data=[{id:member,display_name:'我',scopes:['diet_edit','ai_use']}]
 else if(p.endsWith('/configuration'))data={policy_version:'test',meal:{available:true,processor:'synthetic'}}
 else if(p.endsWith('/processing-consents'))data={accepted:true,policy_version:'test',processor:'synthetic'}
 else if(p.endsWith('/vision/page'))data={jobs:[],drafts:[],jobs_next_offset:null,drafts_next_offset:null}
 else if(p.endsWith('/meal-nutrition-preview'))data={member_id:member,...nutrition(body)}
 else if(p.endsWith('/meal-nutrition-sources')){const q=new URL(req.url()).searchParams.get('q');const id=Object.keys(foodName).find(k=>foodName[k]===q);data=id?[{id,type:'food',name:q,basis:'per100g'}]:[]}
 else if(p.endsWith('/portion-references'))data=[]
 else if(p.endsWith('/uploads')&&failUpload){failUpload=false;status=503;data={detail:'测试上传失败'}}
 else if(p.endsWith('/uploads'))data={upload_id:'dddddddd-dddd-4ddd-8ddd-dddddddddddd',purpose:'meal'}
 else if(p.endsWith('/meal-photo-tasks')){taskCount++;if(process.env.MEAL_SUPPLEMENT_QUOTA_TEST==='1'){status=429;data={code:'budget_exceeded',message:'任务额度已达上限，可使用人工录入'}}else data={task_id:'synthetic-task',execution_status:'pending'}}
 else if(p.endsWith('/vision-tasks/synthetic-task'))data={task_id:'synthetic-task',execution_status:'success',result_id:nextDraft}
 else if(p.endsWith('/meal-drafts/'+nextDraft))data=draft(nextDraft)
 else if(p.endsWith('/meal-drafts/'+firstDraft)){if(method==='PATCH'){payload=body.meal;version++}data=draft()}
 else if(p.endsWith('/calculate'))data={draft_version:version,calculation_id:'test-calc',...nutrition(payload)}
 else if(p.endsWith('/confirm')){record={id:recordId,source_version:version,snapshot:{meal:payload,nutrition:nutrition(payload)}};data={review_status:'confirmed',target_ids:[recordId]}}
 else if(p.endsWith('/diet-logs/page'))data={records:record?[record]:[],next_offset:null}
 else if(p.endsWith('/diet-logs/'+recordId)&&method==='PATCH'){assert.equal(body.expected_version,record.source_version);record={...record,source_version:record.source_version+1,snapshot:{meal:body.meal,nutrition:nutrition(body.meal)}};data=record}
 else {status=404;data={detail:'Unmocked '+p}}
 await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
})
const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message))
try{
 await page.goto('http://127.0.0.1:'+server.address().port+'/#/pages/scan/index')
 await page.getByText('拍照记餐',{exact:true}).click()
 await page.locator('.supplement-entry').waitFor()
 await page.waitForFunction(()=>document.querySelector('.energy-value')?.textContent?.trim()==='165')
 await page.screenshot({path:path.join(out,'01-补充本餐入口.png'),fullPage:false})
 await page.locator('.supplement-entry').click()
 await page.getByText('手动填写 ›',{exact:true}).click()
 await page.locator('.supplement-card textarea').fill('待取消的食物')
 await page.locator('.supplement-card').getByText('取消',{exact:true}).click()
 assert.equal(await page.locator('.nutrition-dish').count(),1)
 await page.locator('.supplement-entry').click()
 failUpload=true
 const failedChooser=page.waitForEvent('filechooser');await page.getByText('从相册选择',{exact:true}).click()
 await (await failedChooser).setFiles({name:'failed.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64')})
 await page.getByText('重新选择照片',{exact:true}).waitFor()
 assert.equal(await page.locator('.nutrition-dish').count(),1)
 await page.locator('.supplement-card').getByText('取消',{exact:true}).click()
 await page.locator('.supplement-entry').click()
 assert.equal(await page.locator('.energy-value').innerText(),'165')
 const chooser=page.waitForEvent('filechooser');await page.getByText('从相册选择',{exact:true}).click()
 const picked=await chooser;assert.equal(picked.isMultiple(),false)
 await picked.setFiles({name:'synthetic-food.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64')})
 if(process.env.MEAL_SUPPLEMENT_QUOTA_TEST==='1'){
  await page.locator('.supplement-card').getByText('任务额度已达上限，可使用人工录入',{exact:true}).waitFor()
  await page.getByText('重试识别',{exact:true}).waitFor()
  assert.equal(await page.locator('.energy-value').innerText(),'165')
  assert.equal(await page.locator('.nutrition-dish').count(),1)
  await page.locator('.supplement-card').evaluate(el=>el.scrollIntoView({block:'center'}))
  await page.locator('.supplement-card').screenshot({path:path.join(out,'05-额度拦截提示.png')})
  await page.getByText('改为手动补充',{exact:true}).click()
  await page.locator('.supplement-card textarea').waitFor()
  assert.equal(await page.locator('.energy-value').innerText(),'165');assert.equal(taskCount,1)
  assert.deepEqual(errors,[]);console.log('PASS: quota error visible in supplement, explicit retry and manual recovery, original meal preserved')
 }else{
 await page.getByText('加入这一餐',{exact:true}).waitFor()
 await page.reload()
 await page.getByText('拍照记餐',{exact:true}).click()
 await page.getByText('加入这一餐',{exact:true}).waitFor()
 await page.waitForFunction(()=>document.querySelector('.energy-value')?.textContent?.trim()==='165')
 assert.equal(await page.locator('.nutrition-dish').count(),1)
 assert.equal(await page.locator('.energy-value').innerText(),'165')
 await page.screenshot({path:path.join(out,'02-新食物核对.png'),fullPage:true})
 await page.locator('.supplement-card').evaluate(el=>el.scrollIntoView({block:'center'}))
 await page.screenshot({path:path.join(out,'02-核对页面.png'),fullPage:false})
 await page.locator('.supplement-card').screenshot({path:path.join(out,'02-核对区域.png')})
 await page.getByText('加入这一餐',{exact:true}).click()
 await page.getByText('请确认重复食物是否又吃了一份',{exact:true}).waitFor()
 await page.getByText('同一份，不再添加',{exact:true}).click()
 await page.getByText('加入这一餐',{exact:true}).click()
 await page.waitForFunction(()=>document.querySelectorAll('.nutrition-dish').length===2&&document.querySelector('.energy-value')?.textContent?.trim()==='321')
 await page.evaluate(()=>window.scrollTo(0,0))
 await page.screenshot({path:path.join(out,'03-加入后的整餐.png'),fullPage:false})
 await page.getByText('确认并记录这一餐',{exact:true}).click()
 await page.getByText('这一餐已记录',{exact:true}).waitFor()
 const confirmedId=record.id
 await page.locator('.supplement-entry').click()
 await page.getByText('手动填写 ›',{exact:true}).click()
 await page.waitForFunction(()=>document.querySelector('.energy-value')?.textContent?.trim()==='321')
 await page.locator('.supplement-card textarea').fill('西兰花')
 await page.getByText('核对食物',{exact:true}).click()
 await page.locator('.supplement-weight input').fill('80')
 await page.getByText('加入这一餐',{exact:true}).click()
 await page.getByText('保存本餐修改',{exact:true}).waitFor()
 await page.waitForFunction(()=>document.querySelectorAll('.nutrition-dish').length===3&&document.querySelector('.energy-value')?.textContent?.trim()==='349')
 await page.getByText('保存本餐修改',{exact:true}).click()
 await page.getByText('已补充到原来的这一餐。',{exact:true}).waitFor()
 assert.equal(record.id,confirmedId);assert.equal(record.snapshot.meal.items.length,3)
 assert.equal(writes.filter(w=>w.path.endsWith('/confirm')).length,1)
 assert.equal(writes.filter(w=>w.method==='PATCH'&&w.path.includes('/diet-logs/')).length,1)
 assert.equal(taskCount,1);assert.deepEqual(errors,[])
 await page.evaluate(()=>window.scrollTo(0,0))
 await page.screenshot({path:path.join(out,'04-保存后补充完成.png'),fullPage:false})
 await fs.writeFile(path.join(out,'browser-result.json'),JSON.stringify({passed:true,taskCount,recordId:record.id,items:record.snapshot.meal.items.length,errors},null,2))
 console.log('PASS: single-photo addition, pending totals, duplicate decision, original-record update')
 }
}catch(e){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});console.log((await page.locator('body').innerText()).slice(0,6500));throw e}
finally{await browser.close();await new Promise(r=>server.close(r))}
