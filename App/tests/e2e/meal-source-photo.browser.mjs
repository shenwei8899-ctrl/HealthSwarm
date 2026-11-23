import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import {createHash} from 'node:crypto'
import path from 'node:path'
import http from 'node:http'
import {createRequire} from 'node:module'
const require=createRequire(import.meta.url)
const {chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright')
const evidence=path.resolve(process.env.MEAL_RECORD_EVIDENCE),root=path.resolve(process.env.MEAL_RECORD_H5)
const workspaceModule='/family-app/assets/'+(await fs.readdir(path.join(root,'assets'))).find(n=>/^meal-workspace\..*\.js$/.test(n))
const server=http.createServer(async(req,res)=>{try{const pathname=decodeURIComponent(req.url.split('?')[0]).replace(/^\/family-app\//,'/');const file=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname));assert.ok(file.startsWith(root+path.sep));res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream');res.end(await fs.readFile(file))}catch{res.writeHead(404);res.end()}})
await new Promise(ok=>server.listen(0,'127.0.0.1',ok))
const origin='http://127.0.0.1:'+server.address().port,browser=await chromium.launch({headless:true,executablePath:process.env.MEAL_RECORD_BROWSER})
const family='11111111-1111-4111-8111-111111111111',self='22222222-2222-4222-8222-222222222222',mom='33333333-3333-4333-8333-333333333333'
const today=new Date(Date.now()+8*3600000).toISOString().slice(0,10)
const meal={type:'dinner',members:[{id:self,name:'我'}],dishes:[{dish_key:'eggs',name:'番茄炒蛋',ingredients:['番茄','鸡蛋'],steps:['鸡蛋炒熟后加入番茄'],grams:300}]}
const results=[]
try{
 for(const width of [320,390,430]){
  const context=await browser.newContext({viewport:{width,height:844},deviceScaleFactor:1}),page=await context.newPage(),errors=[],writes=[]
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!/favicon|503|404/.test(m.text()))errors.push(m.text())})
  await context.addInitScript(({family})=>localStorage.setItem('fn-session-v2:api',JSON.stringify({type:'object',data:{accountId:'1',householdId:family,token:'synthetic-test',clientRevision:'record-entry',authSource:'wechat',families:[{id:family,name:'合成家庭',isOwner:true,onboardingRequired:false}],expiresAt:Date.now()/1000+86400}})),{family})
  const drafts=new Map(),records=[],receipts=new Map();let failConfirm=width===390,taskCount=0
  const nutrition=body=>({complete:false,items:body.items.map(i=>({item_id:i.item_id,nutrients:{energy_kcal:null}})),totals:{energy_kcal:null,protein_g:null,carbohydrate_g:null,fat_g:null},sources:[]})
  await context.route('**/api/**',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname,method=req.method();let data={},status=200
   const body=(req.headers()['content-type']||'').includes('application/json')?req.postDataJSON():{}
   if(method!=='GET')writes.push({path:p,body,headers:req.headers()})
   if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'我'},families:[{id:family,name:'合成家庭',is_owner:true,onboarding_required:false}]}
   else if(p.includes('/daily-arrangements/'))data={arrangement_id:'saved',version:2,meal}
   else if(p.endsWith('/miniapp-profile'))data={source:'api',householdId:family,householdName:'合成家庭',completeProfile:true,onboarded:true,members:[],defaultDiners:[]}
   else if(p==='/api/family')data=[{id:family,name:'合成家庭',is_owner:true}]
   else if(p.endsWith('/members'))data=[{id:self,display_name:'我',scopes:['diet_edit','ai_use']},{id:mom,display_name:'妈妈',scopes:['diet_edit','ai_use']}]
   else if(p.endsWith('/configuration'))data={policy_version:'synthetic',meal:{available:true,processor:'synthetic'}}
   else if(p.endsWith('/processing-consents'))data={accepted:true,policy_version:'synthetic',processor:'synthetic'}
   else if(p.endsWith('/meal-nutrition-preview'))data={member_id:p.includes(self)?self:mom,...nutrition(body)}
   else if(p.endsWith('/meal-nutrition-sources')||p.endsWith('/portion-references'))data=[]
   else if(p.endsWith('/uploads'))data={upload_id:'66666666-6666-4666-8666-666666666666',purpose:'meal'}
   else if(p.endsWith('/meal-photo-tasks')){taskCount++;data={task_id:'synthetic-photo',execution_status:'pending'}}
   else if(p.endsWith('/vision-tasks/synthetic-photo'))data={task_id:'synthetic-photo',execution_status:'success',result_id:'photo-draft'}
   else if(p.endsWith('/meal-drafts/photo-draft')&&method==='PATCH'){data={id:'photo-draft',member_id:self,version:2,kind:'meal',review_status:'pending_confirmation',payload:body.meal};drafts.set('photo-draft',data)}
   else if(p.endsWith('/meal-drafts/photo-draft'))data={id:'photo-draft',member_id:self,kind:'meal',version:1,review_status:'pending_confirmation',payload:{meal_type:'dinner',eaten_at:today+'T18:30:00+08:00',photos:[],items:[{item_id:'photo-eggs',name:'番茄炒蛋',grams:null,share_ratio:null,portion_source:'unknown'},{item_id:'photo-rice',name:'米饭',grams:null,share_ratio:null,portion_source:'unknown'}]}}
   else if(p.endsWith('/vision/page'))data={jobs:[],drafts:[],jobs_next_offset:null,drafts_next_offset:null}
   else if(p.endsWith('/manual-drafts')){const id='draft-'+drafts.size;data={id,member_id:body.member_id,version:1,kind:'meal',review_status:'pending_confirmation',payload:body.meal};drafts.set(id,data)}
   else if(p.endsWith('/calculate')){const id=p.split('/').at(-2),d=drafts.get(id);data={draft_version:d.version,calculation_id:'calc-'+id,...nutrition(d.payload)}}
   else if(p.endsWith('/confirm')){
    const id=p.split('/').at(-2),draft=drafts.get(id),key=body.client_request_id
    if(!receipts.has(key)){const record={id:'record-'+records.length,member_id:draft.member_id,source_version:1,snapshot:{meal:draft.payload,nutrition:nutrition(draft.payload)}};records.push(record);receipts.set(key,{review_status:'confirmed',target_ids:[record.id]})}
    data=receipts.get(key)
    if(failConfirm){failConfirm=false;status=503;data={detail:'synthetic lost confirmation response'}}
   }
   else if(p.endsWith('/diet-logs/page'))data={records:records.filter(r=>p.includes(r.member_id)),next_offset:null}
   else if(p.includes('/meal-drafts/'))data=drafts.get(p.split('/').at(-1))
   else {status=404;data={detail:'unmocked '+p}}
   await route.fulfill({status,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'},contentType:'application/json',body:JSON.stringify(data)})
  })
  await page.goto(origin+'/family-app/#/pages/meals/detail');await page.waitForTimeout(700)
  await page.evaluate(async({workspaceModule,family,today,meal})=>{const ws=await import(workspaceModule);ws.o({familyId:family,date:today,mealType:'dinner',kind:'formal',sourceId:'saved',version:2,dailyPlanVersion:2,seed:meal,purchaseReady:true,initialView:'dish'})},{workspaceModule,family,today,meal})
  await page.locator('.dish-actions .detail-primary').last().waitFor()
  await page.locator('.dish-actions .detail-primary').last().click()
  await page.locator('.record-dish-copy').waitFor();await page.waitForFunction(()=>document.querySelectorAll('.record-members uni-button').length===2)
  await page.waitForFunction(()=>!document.querySelector('.record-photo-entry')?.hasAttribute('disabled'))
  assert.equal(await page.locator('.record-dish-copy>uni-text').first().innerText(),'番茄炒蛋')
  assert.equal(await page.locator('.record-weight input').inputValue(),'');assert.equal(await page.locator('.record-context').getByText('餐次',{exact:true}).count(),1);assert.equal(await page.locator('.record-context>uni-view').count(),2)
  assert.equal(await page.locator('.record-portions .selected').innerText(),'不确定')
  const recordButton=page.locator('.record-capture .save-primary');assert.equal(await recordButton.innerText(),'保存饮食记录')
  const box=await recordButton.boundingBox();assert.ok(box.y>=0&&box.y+box.height<=845,JSON.stringify(box))
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
  await page.screenshot({path:path.join(evidence,'record-'+width+'.png')})
  const panel=page.locator('.record-panel'),dragArea=page.locator('.record-drag-area')
  const initialPanel=await panel.boundingBox(),area=await dragArea.boundingBox()
  await page.locator('.record-weight input').fill('30')
  await page.mouse.move(area.x+area.width/2,area.y+15);await page.mouse.down();await page.mouse.move(area.x+area.width/2,area.y-55,{steps:10});await page.mouse.up()
  const raised=await panel.boundingBox();assert.ok(Math.abs(raised.height-initialPanel.height-70)<5,JSON.stringify({initialPanel,raised}))
  assert.ok(Math.abs(raised.y+raised.height-initialPanel.y-initialPanel.height)<2)
  await page.screenshot({path:path.join(evidence,'drag-up-'+width+'.png')})
  const nextArea=await dragArea.boundingBox()
  await page.mouse.move(nextArea.x+nextArea.width/2,nextArea.y+15);await page.mouse.down();await page.mouse.move(nextArea.x+nextArea.width/2,nextArea.y+125,{steps:10});await page.mouse.up()
  const lowered=await panel.boundingBox();assert.ok(Math.abs(raised.height-lowered.height-110)<5)
  await page.mouse.click(10,Math.max(2,lowered.y-10));assert.equal(await panel.count(),1,'release tap must not dismiss')
  await page.screenshot({path:path.join(evidence,'drag-down-'+width+'.png')})
  await page.getByLabel('关闭记一餐',{exact:true}).click();await panel.waitFor({state:'detached'})
  await page.locator('.dish-actions .detail-primary').last().click();await page.locator('.record-weight input').waitFor()
  assert.equal(await page.locator('.record-weight input').inputValue(),'30')
  assert.ok(Math.abs((await panel.boundingBox()).height-initialPanel.height)<2)
  await page.waitForFunction(()=>!document.querySelector('.record-photo-entry')?.hasAttribute('disabled'))
  const touchArea=await dragArea.boundingBox(),touchX=touchArea.x+touchArea.width/2,touchY=touchArea.y+5,cdp=await context.newCDPSession(page)
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:touchX,y:touchY}]})
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:touchX,y:touchY-50}]})
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})
  assert.ok(Math.abs((await panel.boundingBox()).height-initialPanel.height-50)<5)
  await page.locator('.record-portions uni-button').first().click();await page.locator('.record-portions uni-button').nth(2).click()
  assert.equal(await panel.count(),1);assert.equal(await page.locator('.record-portions .selected').innerText(),'较多')

  // Full photo page receives the same draft; back restores the sheet without an inline photo editor.
  await page.waitForFunction(()=>{const button=document.querySelector('.record-photo-entry');return button&&!button.hasAttribute('disabled')});
  await page.locator('.record-photo-entry').click();await page.waitForFunction(()=>location.hash.includes('/pages/scan/index?captureNavigation='));await page.locator('.source-photo-title').waitFor()
  assert.match(page.url(),/pages\/scan\/index\?captureNavigation=/)
  assert.equal(await page.locator('.source-photo-title').innerText(),'这次来拍：番茄炒蛋')
  assert.equal(await page.locator('.upload-card').count(),1)
  assert.equal(await page.locator('.supplement-card:visible').count(),0)
  await page.screenshot({path:path.join(evidence,'source-photo-'+width+'.png')})
  await page.locator('.capture-fixed-header').getByLabel('返回',{exact:true}).click()
  await page.locator('.record-dish').waitFor();assert.equal(await page.locator('.record-weight input').inputValue(),'30')
  assert.equal(await page.locator('.record-capture .supplement-card').count(),0);assert.match(await page.locator('.record-photo-entry').innerText(),/拍照补充/);assert.doesNotMatch(await page.locator('.record-photo-entry').innerText(),/继续/)
  await page.waitForFunction(()=>{const button=document.querySelector('.record-photo-entry');return button&&!button.hasAttribute('disabled')});
  await page.locator('.record-photo-entry').click();await page.waitForFunction(()=>location.hash.includes('/pages/scan/index?captureNavigation='));await page.locator('.source-photo-title').waitFor()
  await page.waitForFunction(()=>{const button=document.querySelector('.upload-card .capture-secondary');return button&&!button.hasAttribute('disabled')&&!document.querySelector('.capture-loading')});
  const choosing=page.waitForEvent('filechooser');await page.locator('.upload-card').getByText('从相册选择',{exact:true}).click()
  await (await choosing).setFiles({name:'meal.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64')})
  await page.locator('.duplicate-choices:visible').waitFor({timeout:15000})
  await page.locator('.duplicate-choices:visible uni-button').first().click()
  const task=writes.find(w=>w.path.endsWith('/meal-photo-tasks'))
  assert.equal(task.body.source_context.dish_key,'eggs');assert.equal(task.body.source_context.family_id,family)
  assert.equal(task.body.source_context.meal_type,'dinner');assert.equal(task.body.source_context.plan_version,2)
  assert.ok(!JSON.stringify(task.body.source_context).includes('300'))
  await page.locator('.supplement-confirm:visible').click();await page.waitForTimeout(500)
  assert.equal(await page.locator('.scan-screen:visible .nutrition-dish').count(),2)
  await page.locator('.scan-screen:visible .incomplete-toggle').click()
  const savePhoto=page.locator('.scan-screen:visible .save-primary');await savePhoto.click()
  if(width===390){await page.getByText('恢复原保存请求',{exact:true}).waitFor();await page.getByText('恢复原保存请求',{exact:true}).click()}
  await page.locator('.scan-screen:visible .saved-receipt').waitFor();assert.equal(records.length,1)
  await page.locator('.capture-fixed-header:visible').getByLabel('返回',{exact:true}).click()
  await page.locator('.record-capture .saved-receipt').waitFor()
  assert.equal(await page.locator('.record-capture .save-primary').innerText(),'问问营养师')
  assert.equal(records.length,1);assert.equal(records[0].snapshot.meal.items[0].grams,30)
  assert.equal(writes.filter(w=>w.path.endsWith('/dishes')).length,0)
  await page.locator('.record-capture').getByText('查看饮食记录 ›',{exact:true}).click()
  await page.locator('.dj37').first().waitFor();assert.match(await page.locator('.dj37').first().innerText(),/\d{2}:\d{2}/)
  assert.deepEqual(errors,[])
  results.push({width,records:records.length,taskCount,headerMouseDrag:true,headerTouchDrag:true,reopenPreservesInput:true,selectionStaysOpen:true,noMenuMutation:true,noPlannedIntake:true,photoReused:width===390,lostReceiptRetry:width===390,errors})
  await context.close()
 }
 await fs.writeFile(path.join(evidence,'browser-result.json'),JSON.stringify({status:'passed',build_dir:root,index_sha256:createHash('sha256').update(await fs.readFile(path.join(root,'index.html'))).digest('hex'),results},null,2));console.log(JSON.stringify(results))
}catch(e){console.error(e);throw e}finally{await browser.close();server.close()}
