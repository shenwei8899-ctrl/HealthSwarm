// Actual compiled H5 with synthetic recipe, nutrition and commerce data.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {createRequire} from 'node:module'
const require=createRequire(import.meta.url)
const {chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright')
assert.ok(process.env.TODAY_MENU_BROWSER_EVIDENCE,'TODAY_MENU_BROWSER_EVIDENCE is required')
const base=path.resolve(process.env.TODAY_MENU_BROWSER_EVIDENCE),root=path.resolve(process.env.TODAY_MENU_H5_BUILD||path.join(path.dirname(fileURLToPath(import.meta.url)),'../../output/today-menu-inline-20261106/h5'))
await fs.mkdir(base,{recursive:true})
const server=http.createServer(async(req,res)=>{try{const name=decodeURIComponent(new URL(req.url,'http://local').pathname);const file=path.resolve(root,'.'+(name==='/'?'/index.html':name));if(!file.startsWith(root+path.sep))throw Error('path');res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream');res.end(await fs.readFile(file))}catch{res.writeHead(404);res.end()}})
await new Promise(done=>server.listen(0,'127.0.0.1',done));const origin='http://127.0.0.1:'+server.address().port
const browser=await chromium.launch({headless:true,executablePath:process.env.MEAL_DISH_BROWSER_EXE})
const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1})
const family='11111111-1111-4111-8111-111111111111',member='22222222-2222-4222-8222-222222222222',source='33333333-3333-4333-8333-333333333333'
const today=new Date(Date.now()+8*3600000).toISOString().slice(0,10),writes=[],errors=[],reads=[]
const tomorrow=new Date(Date.now()+8*3600000+86400000).toISOString().slice(0,10)
const person={id:member,name:'我',relation:'本人',healthMemberId:member,birthDate:'2000-01-01',gender:'女',height:165,weight:55,version:1,claimed:true,isSelf:true,confirmed:true,healthStatus:'none',conditions:[],goals:[],tastePreferences:[],cuisines:[],allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],doctorStatus:'none',clinicianGuidance:''}
const profile={source:'api',householdId:family,householdName:'合成测试家庭',familyVersion:1,usageMode:'个人使用',defaultDiners:[member],selfMemberId:member,isOwner:true,onboarded:true,completeProfile:true,members:[person]}
const dish=(key,name)=>({dish_key:key,name,image_url:'/static/food/family-meal.jpg',ingredients:['三文鱼 150克','西兰花 100克'],steps:['清洗并处理食材。','将食材蒸熟后装盘。'],step_images:['/static/food/family-meal.jpg','/static/food/family-meal.jpg'],nutrition:{basis:'per_100g',foodState:'recipe_edible',cookingStateLabel:'熟制成品',source:'calculated',energyKcal:120,proteinG:20},nutrition_quote:'原食谱的合成营养说明。'})
const meal=(type,dishes)=>({meal_type:type,source:{kind:'reference',id:source},members:[{id:member,name:'我'}],meal:{meal_type:type,dishes,nutrition:{kcal:480,protein:36},memberNotes:[{memberId:member,name:'我',dishes:dishes.map(d=>({dishId:d.dish_key,grams:150}))}]}})
let plan={date:today,version:1,status:'ready',meals:[meal('breakfast',[dish('breakfast','皮塔饼披萨 | Pita Pizzas')]),meal('lunch',[dish('lunch','鸡肉细面 | Chicken Pasta')]),meal('dinner',[dish('rice','夏威夷快手米饭 | Wiki Rice'),dish('fish','亚洲风味清蒸三文鱼 | Asian-Style Steamed Salmon')])],purchase_options:[{kind:'reference',id:source,meal_types:['breakfast','lunch','dinner'],items:[]}]}
await context.addInitScript(({family})=>localStorage.setItem('fn-session-v2:api',JSON.stringify({type:'object',data:{accountId:'1',accountName:'合成测试',householdId:family,token:'synthetic-meal-test',authSource:'wechat',expiresAt:Date.now()/1000+86400,clientRevision:'meal-test',families:[{id:family,name:'合成测试家庭',isOwner:true,onboardingRequired:false}]}})),{family})
const purchaseFixture={available:true,items:[{sku_id:'101',quantity:1,sku:{sku_id:'101',product_id:'fish',product_name:'三文鱼',sku_name:'300克',net_content:{value:300,unit:'g'},price_cent:2500,available_quantity:20,sale_status:'available'}}],ingredient_requirements:[]}
const packageFixture={...purchaseFixture,scope:'daily_reference',package_sn:'synthetic-pack',package_version:1}
const cartFixture={items:[{cart_item_id:'synthetic-line',sku_id:'101',quantity:1,version:1,selected:true,source_type:'recommendation_package',source_ref:'synthetic-pack',source_version:1}]}
await context.route('**/api/**',async route=>{
 const req=route.request(),url=new URL(req.url()),p=url.pathname;let data,status=200
 if(req.method()!=='GET')writes.push({path:p,body:req.postDataJSON()});else reads.push(url.pathname+url.search)
 if(p.endsWith('/session/exchange'))data={code:0,data:{user:{id:1,token:'synthetic-shop'},agent_account_id:'1'}}
 else if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'合成测试'},families:[{id:family,name:'合成测试家庭',is_owner:true,onboarding_required:false}]}
 else if(p.endsWith('/miniapp-profile'))data=profile
 else if(p==='/api/health/v1/configuration')data={policy_version:'synthetic',consultation:{available:true,processor:'synthetic'},meal_plan:{available:true,processor:'synthetic'}}
 else if(p==='/api/health/v1/members')data=[{id:member,display_name:'我',scopes:['ai_use','profile_view','diet_edit'],is_owner:true}]
 else if(p.endsWith('/readiness'))data={capabilities:{member_id:member},entries:[{entry_type:'consultation',status:'available'},{entry_type:'reference_meal_preview',status:'available'}]}
 else if(p.endsWith('/daily-conversations'))data={days:[]}
 else if(p.endsWith('/consultations')&&req.method()==='POST')data={member_id:member,agent_slug:'health-consultation',thread_id:'44444444-4444-4444-8444-444444444444',business_date:null,feedback_selection:null}
 else if(p.includes('/consultations'))data={items:[],has_more:false,next_offset:null}
 else if(p.endsWith('/history'))data={history:[],runs:[]}
 else if(p.endsWith('/dishes')){const b=req.postDataJSON();const copy=structuredClone(plan);copy.version++;const target=copy.meals.find(m=>m.meal_type===b.meal_type);const d=copy.meals.find(m=>m.meal_type===b.source_meal).meal.dishes.find(d=>d.dish_key===b.dish_key);if(!target.meal.dishes.some(d=>d.dish_key===b.dish_key))target.meal.dishes.push(d);plan=copy;data=copy}
 else if(p.includes('/daily-meal-plans/')&&p.endsWith('/purchase'))data={version:plan.version,purchase:{...purchaseFixture,...(req.method()==='POST'?{package_sn:'synthetic-pack',package_version:1}:{})}}
 else if(p.includes('/api/v1/commerce/meals/packages/'))data={code:0,data:packageFixture}
 else if(p.endsWith('/api/v1/commerce/addresses'))data={code:0,data:{items:[{id:1,name:'合成收件人',phone:'13800000000',region:'合成区域',detail:'合成测试地址',isDefault:true}]}}
 else if(p.endsWith('/api/v1/commerce/delivery/slots'))data={code:0,data:{supported:true,items:[{id:1,name:'合成配送时段',available:true}]}}
 else if(p.endsWith('/api/v1/commerce/cart')||p.endsWith('/api/v1/commerce/meals/cart'))data={code:0,data:cartFixture}
 else if(p.endsWith('/api/v1/commerce/checkout/preview'))data={code:0,data:{checkout_token:'synthetic-quote',expires_at:new Date(Date.now()+60000).toISOString(),goods_amount_cent:2500,shipping_fee_cent:0,payable_amount_cent:2500,items:[{...cartFixture.items[0],line_amount_cent:2500}]}}
 else if(p.includes('/daily-meal-plans/'))data=p.endsWith('/'+tomorrow)?{...plan,date:tomorrow,version:7}:plan
 else if(p.includes('/onboarding-preparations'))data={status:'absent'}
 else if(p==='/api/family')data=[{id:family,name:'合成测试家庭',is_owner:true}]
 else {status=404;data={detail:'Synthetic endpoint not configured: '+p}}
 await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
})
const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message))
try {
 await page.goto(origin)
 const shortcut=page.locator('.shortcut-button').filter({hasText:'今日餐单'})
 await shortcut.waitFor({timeout:20000})
 const input=page.locator('uni-input input')
 await input.fill('请保留这段输入草稿')
 await page.locator('.tm-inline .tm-meal-entry').nth(2).waitFor()
 await page.waitForFunction(()=>!document.querySelector('.tm-inline .tm-meal-entry[disabled]'))
 assert.deepEqual(await page.locator('.tm-inline .tm-meal-entry').allTextContents(),['早餐','午餐','晚餐'])
 assert.equal(await page.locator('.tm-inline .meal-dish').count(),0)
 await page.locator('.tm-inline').screenshot({path:path.join(base,'today-menu-inline.png')})
 await shortcut.click()
 const sheet=page.locator('.tm-sheet')
 await sheet.waitFor()
 assert.equal(await sheet.locator('.tm-meal-entry').count(),3)
 const sheetBox=await sheet.boundingBox()
 assert.ok(sheetBox.height<350,`compact sheet should fit its content, actual ${sheetBox.height}`)
 await page.screenshot({path:path.join(base,'compact-menu.png')})
 await sheet.locator('.tm-meal-entry').nth(2).click()
 const cards=page.locator('.is-dish-grid')
 await cards.waitFor()
 assert.equal(await sheet.count(),0)
 assert.equal(await cards.count(),1)
 assert.equal(await cards.locator('.dish-tile').count(),2)
 assert.match(await page.locator('.message-turn').last().innerText(),/今天的晚餐安排了夏威夷快手米饭、亚洲风味清蒸三文鱼/)
 assert.equal(await input.inputValue(),'请保留这段输入草稿')
 assert.equal(writes.some(write=>/agent\/runs|daily-meal-plans.*purchase/.test(write.path)),false)
 for(const width of [320,390]) {
  await page.setViewportSize({width,height:844})
  const entryBoxes=await page.locator('.tm-inline .tm-meal-entry').evaluateAll(nodes=>nodes.map(node=>{const b=node.getBoundingClientRect();return {top:b.top,left:b.left,right:b.right}}))
  assert.ok(entryBoxes.every(box=>Math.abs(box.top-entryBoxes[0].top)<1))
  const overflow=await cards.evaluate(node=>node.scrollWidth>node.clientWidth+1)
  assert.equal(overflow,false)
  await cards.screenshot({path:path.join(base,`dinner-dishes-${width}.png`)})
 }
 await page.locator('.tm-inline .tm-meal-entry').nth(2).click()
 assert.equal(await cards.count(),1)
 await cards.locator('.meal-ingredients').click()
 await page.locator('.meal-detail-panel.is-page').waitFor()
 await page.waitForFunction(()=>!document.querySelector('.detail-status'))
 assert.match(await page.locator('.detail-title').innerText(),/晚餐/)
 assert.match(await page.locator('.detail-section-heading').innerText(),/本餐菜品\s*共 2 道/)
 await page.screenshot({path:path.join(base,'dinner-arrangement.png')})
 await page.locator('.detail-footer .detail-primary').click()
 await page.locator('.mp-sheet-panel').waitFor()
 await page.screenshot({path:path.join(base,'dinner-purchase.png')})
 assert.ok(reads.some(url=>url.includes('/daily-meal-plans/'+today+'/meals/dinner/purchase')))
 await page.getByLabel('关闭采购页',{exact:true}).click()
 await page.locator('.detail-back').click()
 await page.locator('.tm-inline .tm-meal-entry').nth(2).waitFor()
 await page.waitForFunction(()=>!document.querySelector('.tm-inline .tm-meal-entry[disabled]'))
 assert.equal(await page.locator('.is-dish-grid').count(),1)
 assert.equal(await input.inputValue(),'请保留这段输入草稿')
 await page.screenshot({path:path.join(base,'returned-to-chat.png')})
 console.log(JSON.stringify({status:'passed',widths:[320,390],sheetHeight:sheetBox.height,errors,writes,reads},null,2))
 assert.deepEqual(errors,[])
} catch(error) {
 await page.screenshot({path:path.join(base,'failure.png')})
 console.error(JSON.stringify({url:page.url(),errors,reads,writes,body:(await page.locator('body').innerText()).slice(-4000)},null,2))
 throw error
} finally {
 await context.close();await browser.close();await new Promise(done=>server.close(done))
}
