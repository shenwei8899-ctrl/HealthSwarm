// Compiled H5 UI checks with synthetic data. No production service is contacted.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import {createRequire} from 'node:module'
import {spawnSync} from 'node:child_process'

const require=createRequire(import.meta.url)
const {chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright')
assert.ok(process.env.UI_POLISH_BUILD&&process.env.UI_POLISH_EVIDENCE,'UI_POLISH_BUILD and UI_POLISH_EVIDENCE are required')
const root=path.resolve(process.env.UI_POLISH_BUILD),evidence=path.resolve(process.env.UI_POLISH_EVIDENCE)
await fs.mkdir(evidence,{recursive:true})
const server=http.createServer(async(req,res)=>{
 try{
  let name=decodeURIComponent(new URL(req.url,'http://local').pathname)
  if(name==='/family-app')name='/'
  else if(name.startsWith('/family-app/'))name=name.slice('/family-app'.length)
  const file=path.resolve(root,'.'+(name==='/'?'/index.html':name))
  assert.ok(file.startsWith(root+path.sep))
  res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png','.webp':'image/webp','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream')
  res.end(await fs.readFile(file))
 }catch{res.writeHead(404);res.end()}
})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
const origin='http://127.0.0.1:'+server.address().port
const browser=await chromium.launch({headless:true,executablePath:process.env.UI_POLISH_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'})
const family='11111111-1111-4111-8111-111111111111',member='22222222-2222-4222-8222-222222222222',thread='33333333-3333-4333-8333-333333333333'
const health={birthDate:'1990-01-01',gender:'女',height:165,weight:55,version:1,claimed:true,confirmed:true,healthStatus:'none',conditions:[],goals:[],tastePreferences:[],cuisines:[],allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],doctorStatus:'none',clinicianGuidance:''}
function fixture({owner=true,empty=false}={}){
 const members=empty?[]:Array.from({length:8},(_,index)=>({...health,id:index?`22222222-2222-4222-8222-${String(222222222222+index)}`:member,healthMemberId:index?null:member,name:index?'家人'+index+'·'+('长姓名用于检验换行和边界'.repeat(4)):'我',relation:index?'家人':'本人',isSelf:index===0}))
 return {source:'api',householdId:family,householdName:'温暖的家·'+('完整家庭名称'.repeat(8)),familyVersion:1,usageMode:'家庭使用',defaultDiners:members.map(m=>m.id),selfMemberId:empty?null:member,isOwner:owner,onboarded:true,completeProfile:true,members}
}
const row={thread_id:thread,member_id:member,agent_slug:'health-consultation',business_date:null,feedback_selection:null}
const results=[]
function contrast(foreground,background){
 const luminance=color=>{const rgb=color.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]}
 const a=luminance(foreground),b=luminance(background);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)
}
async function renderedContrast(page,selector,file){
 const element=page.locator(selector).first()
 await element.waitFor()
 const geometry=await element.evaluate(el=>({box:el.getBoundingClientRect().toJSON(),foreground:getComputedStyle(el).color}))
 await page.screenshot({path:file,fullPage:true})
 const x=Math.max(0,Math.floor(geometry.box.left)-2),y=Math.floor(geometry.box.top+geometry.box.height/2)
 // Read a neighboring background pixel at the text's actual vertical position.
 const pixel=spawnSync(process.env.UI_POLISH_PYTHON||'python',['-c','from PIL import Image;import json,sys;im=Image.open(sys.argv[1]).convert("RGB");print(json.dumps(im.getpixel((int(sys.argv[2]),int(sys.argv[3])))))',file,String(x),String(y)],{encoding:'utf8'})
 assert.equal(pixel.status,0,pixel.stderr)
 const background=JSON.parse(pixel.stdout),foreground=geometry.foreground.match(/[\d.]+/g).slice(0,3).map(Number)
 return {foreground,background,ratio:contrast(foreground,background),sample:{x,y}}
}
async function noHorizontalOverflow(page){
 const metric=await page.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth,body:document.body.scrollWidth}))
 assert.ok(metric.scroll<=metric.viewport+1&&metric.body<=metric.viewport+1,JSON.stringify(metric))
 return metric
}
async function run(name,options,verify){
 const context=await browser.newContext({viewport:{width:options.width||390,height:options.height||844}}),errors=[],requests=[],external=[]
 const profile=fixture(options)
 let created=false,held=false,release
 const gate=new Promise(resolve=>release=resolve)
 await context.addInitScript(({family,owner})=>localStorage.setItem('fn-session-v2:api',JSON.stringify({type:'object',data:{accountId:'1',accountName:'合成界面验收',householdId:family,token:'synthetic-ui-polish',authSource:'wechat',expiresAt:Date.now()/1000+86400,clientRevision:'ui-polish',families:[{id:family,name:'合成家庭',isOwner:owner,onboardingRequired:false}]}})),{family,owner:options.owner!==false})
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url()),p=url.pathname,method=request.method()
  if(url.hostname!=='127.0.0.1'){external.push({origin:url.origin,blocked:true});await route.abort();return}
  if(!p.startsWith('/api/')&&!p.startsWith('/commerce-api/')){await route.continue();return}
  requests.push({path:p,method})
  let data,status=200
  if(p.endsWith('/session/exchange'))data={code:0,data:{user:{id:1,token:'synthetic-shop'},agent_account_id:'1'}}
  else if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'合成界面验收'},families:[{id:family,name:'合成家庭',is_owner:options.owner!==false,onboarding_required:false}]}
  else if(p.endsWith('/miniapp-profile'))data=profile
  else if(p.endsWith('/configuration'))data={policy_version:'synthetic',consultation:{available:true,processor:'synthetic'},meal_plan:{available:true,processor:'synthetic'}}
  else if(p==='/api/health/v1/members')data=[{id:member,display_name:'我',is_owner:true,scopes:['ai_use','profile_view','diet_edit']}]
  else if(p.endsWith('/readiness'))data={capabilities:{member_id:member},entries:[{entry_type:'consultation',status:'available'}]}
  else if(p.endsWith('/consultations')){if(method==='POST'){created=true;data=row}else data={items:created?[row]:[],has_more:false,next_offset:null}}
  else if(p.includes('/requests'))data={requests:[],queue:{status:'idle'}}
  else if(p.endsWith('/history'))data={thread:{id:thread,agent_id:'health-consultation'},runs:[],related_threads:[],history:[]}
  else if(p.endsWith('/chat-intent'))data=options.sendFailure?{route:'nutrition_consultation'}:{route:'needs_clarification',message:'合成确认：问题已经收到。'}
  else if(p==='/api/agent/runs'&&method==='POST'){held=true;await gate;status=422;data={detail:'合成校验：这条问题未完成，请重新编辑。'}}
  else if(p.endsWith('/daily-conversations'))data={days:[]}
  else if(p.includes('/daily-meal-plans/'))data={status:'absent',date:p.split('/').at(-1),version:0,meals:[]}
  else if(p.includes('/preparation'))data={status:'absent'}
  else if(p==='/api/family/'+family)data={id:family,owner_transfer:null}
  else if(p.includes('/invitations'))data={items:[]}
  else{status=404;data={detail:'Synthetic UI fixture not provided'}}
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
 })
 const page=await context.newPage();page.setDefaultTimeout(10000);page.on('pageerror',error=>errors.push(error.message))
 try{
  const details=await verify({page,context,profile,requests,release,held:()=>held})
  assert.deepEqual(errors,[]);assert.ok(external.every(request=>request.blocked))
  await page.screenshot({path:path.join(evidence,name+'.png'),fullPage:true})
  results.push({scenario:name,passed:true,...details,pageErrors:errors,blockedExternalRequests:external})
 }catch(error){
  await page.screenshot({path:path.join(evidence,name+'-failure.png'),fullPage:true}).catch(()=>{})
  const result={scenario:name,passed:false,error:error.message,pageErrors:errors,externalRequests:external,requests,body:(await page.locator('body').innerText()).slice(0,1800)}
  results.push(result);console.error(JSON.stringify(result))
 }finally{release();await context.close()}
}
async function home(page){
 await page.goto(origin+'/family-app/#/pages/chat/index')
 await page.locator('#chat-welcome-layer .prompt-grid > *').nth(3).waitFor()
 await page.waitForFunction(()=>document.querySelector('.camera-button')&&!document.querySelector('.camera-button').classList.contains('uni-button-disabled'))
 await page.locator('#chat-welcome-layer .character-rig.is-ready').waitFor()
 await page.waitForFunction(()=>getComputedStyle(document.querySelector('#chat-welcome-layer')).opacity==='1')
}
async function openFamily(page){
 // Initial API deep links are intentionally guarded; exercise the actual home entry.
 await page.goto(origin+'/family-app/#/pages/chat/index')
 await page.locator('#chat-welcome-layer .prompt-grid > *').nth(3).waitFor()
 await page.locator('.shortcut-family').click()
 await page.waitForURL(/pages\/profile\/index/)
 await page.locator('.family-overview').waitFor()
}
try{
 for(const [width,height] of [[320,640],[390,844],[430,932]])await run('home-'+width,{width,height},async({page})=>{
  await home(page)
  assert.equal(await page.locator('#chat-welcome-layer .prompt-grid > *').count(),4)
  assert.equal(await page.locator('#chat-welcome-layer .character-part').count(),4)
  assert.equal(await page.locator('#chat-welcome-layer .character-poster').evaluate(el=>getComputedStyle(el).opacity),'0')
  await page.screenshot({path:path.join(evidence,'home-'+width+'-idle.png'),fullPage:true})
  const layer=page.locator('#chat-welcome-layer'),cards=layer.locator('.prompt-grid > *')
  for(const card of await cards.all()){
   await card.scrollIntoViewIfNeeded()
   const cardBox=await card.boundingBox(),layerBox=await layer.boundingBox()
   assert.ok(cardBox.y>=layerBox.y-1&&cardBox.y+cardBox.height<=layerBox.y+layerBox.height+1,'all four prompt cards are reachable in the welcome scroll region')
   assert.equal(await card.isEnabled(),true)
  }
  const composerBox=await page.locator('.composer').boundingBox()
  assert.ok(composerBox.y>=0&&composerBox.y+composerBox.height<=height,'composer remains visible at the representative phone height')
  const input=page.locator('.composer input');await input.fill('准备一份清淡早餐')
  await page.getByLabel('发送',{exact:true}).waitFor()
  assert.equal(await page.getByLabel('发送',{exact:true}).isEnabled(),true)
  await input.fill('')
  return {width,height,allPromptsReachable:true,composerVisible:true,overflow:await noHorizontalOverflow(page)}
 })
 await run('keyboard-and-contrast',{},async({page})=>{
  await home(page)
  const contrastCheck=await renderedContrast(page,'#chat-welcome-layer .welcome-description',path.join(evidence,'welcome-contrast.png'))
  const input=page.locator('.composer input');await input.click();await input.fill('输入时保留这条草稿')
  await page.setViewportSize({width:390,height:544})
  await page.locator('.nutritionist-layout.keyboard-open').waitFor()
  await page.waitForFunction(()=>document.querySelector('.shortcut-reveal')?.getBoundingClientRect().height===0)
  const inputBox=await input.boundingBox();assert.ok(inputBox.y>=0&&inputBox.y+inputBox.height<=544,'focused input remains above keyboard')
  assert.equal(await input.inputValue(),'输入时保留这条草稿')
  await page.screenshot({path:path.join(evidence,'keyboard-open.png'),fullPage:true})
  await page.setViewportSize({width:390,height:844})
  await page.waitForFunction(()=>!document.querySelector('.nutritionist-layout.keyboard-open')&&document.querySelector('.shortcut-reveal')?.getBoundingClientRect().height>=44)
  assert.ok(contrastCheck.ratio>=4.5,JSON.stringify(contrastCheck))
  return {keyboardRestored:true,contrast:contrastCheck}
 })
 await run('family-long-names',{},async({page})=>{
  await openFamily(page)
  await page.waitForFunction(()=>document.querySelectorAll('.member-tab').length===8)
  const overflow=await noHorizontalOverflow(page)
  await page.locator('.member-tab').nth(1).click()
  await page.waitForFunction(()=>!document.querySelector('.deck-stage.is-switching'))
  assert.ok((await page.locator('.card-name').first().innerText()).length>30)
  const summaryContrast=await renderedContrast(page,'.switch-hint',path.join(evidence,'family-contrast.png'))
  assert.ok(summaryContrast.ratio>=4.5,JSON.stringify(summaryContrast))
  return {overflow,summaryContrast}
 })
 for(const owner of [true,false])await run('family-empty-'+(owner?'owner':'member'),{owner,empty:true},async({page})=>{
  await openFamily(page)
  await page.getByText('先为家人留一个位置',{exact:true}).waitFor()
  assert.equal(await page.getByText('添加家庭成员',{exact:true}).count(),owner?1:0)
  assert.equal(await page.locator('.member-add').count(),0)
  return {owner,overflow:await noHorizontalOverflow(page),addEntryVisible:owner}
 })
 await run('meal-long-diners',{},async({page,profile,requests})=>{
  await home(page);await page.locator('.shortcut-today').click()
  const sheet=page.locator('.tm-sheet');await sheet.waitFor()
  const edit=sheet.getByText('调整就餐成员',{exact:true});const editBox=await edit.boundingBox()
  assert.ok(editBox.height>=44,'meal edit target is at least44px')
  await edit.click();await sheet.locator('.tm-diner-tabs').getByText('早餐',{exact:true}).click()
  const rows=sheet.locator('.tm-diner-member');assert.equal(await rows.count(),profile.members.length)
  const bounds=await rows.evaluateAll(elements=>elements.map(el=>{const box=el.getBoundingClientRect(),check=el.querySelector('.tm-diner-check').getBoundingClientRect();return {left:box.left,right:box.right,height:box.height,checkLeft:check.left,checkRight:check.right}}))
  for(const bound of bounds){assert.ok(bound.left>=0&&bound.right<=390&&bound.height>=44);assert.ok(bound.checkLeft>=bound.left&&bound.checkRight<=bound.right)}
  await rows.first().click();assert.equal(await rows.first().getAttribute('aria-checked'),'false')
  await rows.first().click();assert.equal(await rows.first().getAttribute('aria-checked'),'true')
  assert.equal(requests.some(req=>req.path.includes('/daily-meal-plans/')&&req.method!=='GET'),false)
  return {members:profile.members.length,editHeight:editBox.height,bounds,overflow:await noHorizontalOverflow(page)}
 })
 await run('message-failure-target',{sendFailure:true},async({page,release,held})=>{
  await home(page);await page.locator('.composer input').fill('这条合成问题用于检查错误恢复')
  await page.getByLabel('发送',{exact:true}).click()
  await page.waitForFunction(()=>document.querySelector('.send-button.is-processing'))
  const busy=await page.locator('.send-button.is-processing').evaluate(el=>({opacity:getComputedStyle(el).opacity,disabled:el.classList.contains('uni-button-disabled')||el.getAttribute('disabled')==='true'}))
  assert.equal(busy.opacity,'1');assert.equal(busy.disabled,true)
  assert.equal(held(),true);release()
  const issue=page.locator('.message-issue').first();await issue.waitFor()
  const issueBox=await issue.boundingBox();assert.ok(issueBox.width>=44&&issueBox.height>=44)
  assert.equal(await issue.evaluate(el=>el.tagName),'UNI-BUTTON')
  assert.equal(await issue.getAttribute('role'),'button')
  assert.equal(await issue.getAttribute('tabindex'),'0')
  await issue.focus();await page.keyboard.press('Tab');await page.keyboard.press('Shift+Tab')
  const focus=await issue.evaluate(el=>({active:document.activeElement===el,visible:el.matches(':focus-visible'),style:getComputedStyle(el).outlineStyle,width:getComputedStyle(el).outlineWidth}))
  assert.equal(focus.active,true);assert.equal(focus.visible,true)
  assert.ok(focus.style!=='none'&&parseFloat(focus.width)>=2,'keyboard focus has a visible outline')
  await page.screenshot({path:path.join(evidence,'message-failure-keyboard-focus.png'),fullPage:true})
  const activations=[],preservedDraft=await page.locator('.composer input').inputValue()
  for(const activation of ['Enter','Space','click']){
   await issue.focus()
   assert.equal(await issue.evaluate(el=>document.activeElement===el),true,'failure control is keyboard-focusable')
   if(activation==='click')await issue.click()
   else await issue.press(activation)
   const modal=page.locator('.uni-modal:visible')
   await modal.getByText('消息状态',{exact:true}).waitFor()
   await page.waitForTimeout(150)
   assert.equal(await modal.count(),1,'one action opens one visible failure explanation')
   await modal.getByText('本次消息未被接受，原问题已保留，可以编辑后重试。',{exact:true}).waitFor()
   const cancel=modal.getByText('取消',{exact:true})
   if(await cancel.count())await cancel.click()
   else await modal.getByText('知道了',{exact:true}).click()
   await modal.waitFor({state:'hidden'})
   // Detect a queued duplicate after the platform dialog closes.
   await page.waitForTimeout(150)
   assert.equal(await page.locator('.uni-modal:visible').count(),0,'dismissal does not expose a duplicate dialog')
   assert.equal(await page.locator('.composer input').inputValue(),preservedDraft,'viewing a failure explanation preserves the draft')
   activations.push(activation)
  }
  return {busy,issueTarget:issueBox,control:'UNI-BUTTON',role:'button',focus,activations,overflow:await noHorizontalOverflow(page)}
 })
 await fs.writeFile(path.join(evidence,'result.json'),JSON.stringify({build:root,scenarios:results},null,2))
 console.log(JSON.stringify(results.map(({scenario,passed,error})=>({scenario,passed,...(error?{error}:{})}))))
 assert.ok(results.every(result=>result.passed),'One or more compiled UI scenarios failed; see result.json and failure screenshots')
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}
