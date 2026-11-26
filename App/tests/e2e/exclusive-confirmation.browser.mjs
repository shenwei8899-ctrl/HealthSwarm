import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import {createRequire} from 'node:module'
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_PACKAGE)
const root=path.resolve(process.env.EXCLUSIVE_H5),output=path.resolve(process.env.EXCLUSIVE_SCREENSHOTS)
await fs.mkdir(output,{recursive:true})
const server=http.createServer(async(req,res)=>{
 try{
  const pathname=decodeURIComponent(new URL(req.url,'http://local').pathname).replace(/^\/family-app\//,'/')
  const file=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname))
  if(!file.startsWith(root+path.sep))throw Error('Invalid path')
  res.setHeader('Content-Type',{'.html':'text/html','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml'}[path.extname(file)]||'application/octet-stream')
  res.end(await fs.readFile(file))
 }catch{res.writeHead(404);res.end()}
})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
const browser=await chromium.launch({headless:true,executablePath:process.env.EXCLUSIVE_BROWSER})
const family='11111111-1111-4111-8111-111111111111',group='22222222-2222-4222-8222-222222222222'
const errors=[],results=[]
async function chooseDate(page, value, daySteps) {
 await page.locator('.date-control').click()
 const input=page.locator('input.uni-picker-system_input[type="date"]')
 if(await input.count())await input.fill(value)
 else {
  const popup=page.locator('.uni-picker-toggle')
  await popup.waitFor()
  const days=popup.locator('uni-picker-view-column').last()
  for(let i=0;i<daySteps;i++){await days.hover();await page.mouse.wheel(0,40);await page.waitForTimeout(350)}
  if(page.viewportSize().width===390)await page.screenshot({path:path.join(output,'calendar-open-390.png')})
  await popup.locator('.uni-picker-action-confirm').click()
  await page.waitForFunction(()=>[...document.querySelectorAll('.uni-picker-container')].every(el=>getComputedStyle(el).display==='none'))
 }
 await page.waitForFunction(value=>document.querySelector('.date-control')?.dataset.date===value,value)
}
try{
 for(const width of [320,390,430]){
  const context=await browser.newContext({viewport:{width,height:844},locale:'zh-CN',deviceScaleFactor:2})
  await context.addInitScript(({family})=>localStorage.setItem('fn-session-v2:api',JSON.stringify({type:'object',data:{accountId:'1',accountName:'合成测试',householdId:family,token:'synthetic-exclusive-test',authSource:'wechat',expiresAt:Date.now()/1000+86400,clientRevision:'exclusive-test',families:[{id:family,name:'合成家庭',isOwner:true,onboardingRequired:false}]}})),{family})
  const sku=(id,name,price)=>({sku_id:id,product_id:id,product_name:name,sku_name:'500g/包',price_cent:price,available_quantity:100,sale_status:'available',net_content:{value:500,unit:'g'},ingredients:[],image_url:''})
  const items=[{sku_id:'rice',food:'大米',quantity:2,quantity_confirmed:false,sku:sku('rice','大米',500)},{sku_id:'greens',food:'青菜',quantity:5,quantity_confirmed:false,sku:sku('greens','青菜',300)}]
  const purchase={scope_hash:'a'.repeat(64),tier_name:'经济型',members:[{id:'m1'},{id:'m2'}],days:7,period_days:7,available:true,items,gaps:[{label:'姜',detail:'需自行准备'}],notice:'包装数量请按家庭实际需要核对。'}
  purchase.delivery_suggestions={status:'suggested',batches:[
   {day_no:1,items:[{product:{sku_id:'rice'},use_days:[1,7],schedule_basis:'storage_rule',storage_max_days:7},{product:{sku_id:'greens'},use_days:[1,2,3]}]},
   {day_no:4,items:[{product:{sku_id:'greens'},use_days:[4,5,6]}]},
   {day_no:7,items:[{product:{sku_id:'greens'},use_days:[7]}]},
  ]}
  let pendingRules=false,quoteCount=0,noAddress=false,noSlots=false
  await context.route('**/api/**',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname,body=req.postDataJSON()||{}
   let data={}
   if(p.includes('/api/v1/commerce/')){
    if(p.endsWith('/session/exchange'))data={agent_account_id:'1',identity_namespace:'synthetic',user:{id:301,token:'synthetic-commerce'}}
    else if(p.endsWith('/addresses'))data={items:noAddress?[]:[{id:'address-1',name:'合成收件人',phone:'13800000000',region:'上海市 徐汇区',detail:'仅供测试的较长街道地址，春和花园三号楼六零二室',isDefault:true}]}
    else if(p.endsWith('/delivery/slots')){
     assert.equal(url.searchParams.get('purpose'),'plan')
     data={supported:true,items:noSlots?[]:[{id:10,name:'10:00–11:00',available:true},{id:20,name:'12:00–13:00',available:true}]}
    }else if(p.endsWith('/checkout/exclusive-dates')){
     if(pendingRules)return route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({code:40963,message:'青菜的储存规则待核对，暂不能确认配送',data:{reason:'storage_rule_pending'}})})
     data={items:['2026-12-01','2026-12-03']}
    }else if(p.endsWith('/checkout/preview')){
     quoteCount++;assert.ok(body.first_meal_date)
     const selected=body.items.map(line=>({...line,unit_price_cent:items.find(item=>item.sku_id===line.sku_id).sku.price_cent,snapshot:items.find(item=>item.sku_id===line.sku_id).sku}))
     const fresh=selected.find(item=>item.sku_id==='greens'),rice=selected.find(item=>item.sku_id==='rice')
     const shifts=fresh?[0,3,6]:[0]
     const batches=shifts.map((offset,index)=>{
      const date=new Date(body.first_meal_date+'T00:00:00Z');date.setUTCDate(date.getUTCDate()+offset-1)
      const contents=[...(index===0&&rice?[{...rice,food:'大米',use_days:[6,7]}]:[]),...(fresh?[{...fresh,food:'青菜',quantity:index<2?2:fresh.quantity-4,use_days:index===0?[1,2,3]:index===1?[4,5,6]:[7]}]:[])]
      return{menu_day_start:offset+1,batch_no:index+1,delivery_date:date.toISOString().slice(0,10),slot_name:body.delivery_slot_id===10?'10:00–11:00':'12:00–13:00',contains_weekly_staples:index===0&&!!rice,items:contents}
     })
     const goods=selected.reduce((sum,line)=>sum+line.quantity*line.unit_price_cent,0)
     data={checkout_token:'synthetic-quote',expires_at:new Date(Date.now()+60000).toISOString(),items:selected.map(line=>({...line,line_amount_cent:line.quantity*line.unit_price_cent})),exclusive_delivery:{first_meal_date:body.first_meal_date,last_meal_date:body.first_meal_date==='2026-12-01'?'2026-12-07':'2026-12-09'},delivery_batches:batches,goods_amount_cent:goods,shipping_fee_cent:batches.length*600,discount_amount_cent:0,payable_amount_cent:goods+batches.length*600}
    }else if(p.includes('/orders'))throw Error('Browser must not place an order')
    else data={}
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({code:0,data})})
   }
   if(p==='/api/auth/wechat/session')data={wechat_authenticated:true,account:{id:1,name:'合成测试'},service_notice:{version:'test',content_hash:'a'.repeat(64),acknowledged:true},families:[{id:family,name:'合成家庭',is_owner:true,onboarding_required:false}]}
   else if(p.includes('/tiers/')&&p.endsWith('/purchase'))data={...purchase,...(req.method()==='POST'?{package:{package_sn:'weekly-synthetic',package_version:1,expires_at:new Date(Date.now()+600000).toISOString()}}:{})}
   else if(p==='/api/account/service-notice')data={version:'test',content_hash:'a'.repeat(64),acknowledged:true}
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})
  })
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message))
  try{
   await page.goto('http://127.0.0.1:'+server.address().port+'/family-app/#/pages/index/index')
   await page.waitForURL('**/#/pages/chat/index')
   await page.evaluate(url=>{location.hash='#'+url},'/pages/exclusive-plans/detail?group_id='+group+'&tier=economy&purchase=1')
   assert.equal(await page.locator('.checkout-button').count(),0)
   const screen=page.locator('.exclusive-confirmation')
   await screen.locator('.delivery-trip').first().waitFor()
   assert.equal(await screen.locator('.delivery-tab').count(),3)
   assert.equal(await screen.locator('.ingredient-lines').count(),0)
   assert.equal(await screen.locator('.trip-items').count(),1)
   assert.equal(await screen.locator('.footer-amount').innerText(),'¥43.00')
   assert.equal(await screen.locator('.footer-button').getAttribute('disabled'),'true')
   assert.equal(await screen.evaluate(el=>el.scrollWidth<=el.clientWidth),true,await screen.evaluate(el=>JSON.stringify({root:{width:el.clientWidth,scroll:el.scrollWidth},overflow:[...el.querySelectorAll('*')].filter(child=>child.getBoundingClientRect().right>el.getBoundingClientRect().right+1).slice(0,12).map(child=>({tag:child.tagName,class:child.className,width:child.clientWidth,scroll:child.scrollWidth,rect:child.getBoundingClientRect().toJSON()}))})))
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true)
   await page.screenshot({path:path.join(output,'confirmation-'+width+'.png')})
   const beforeTabs=quoteCount
   await screen.getByRole('tab',{name:'查看第2趟配送',exact:true}).click()
   assert.equal(await screen.locator('.delivery-trip').count(),1)
   assert.doesNotMatch(await screen.locator('.trip-items').innerText(),/大米/)
   assert.equal(quoteCount,beforeTabs)
   await chooseDate(page,'2026-12-03',2)
   assert.match(await screen.locator('.delivery-tab.selected').innerText(),/12\/05/)
   await page.waitForFunction(()=>document.querySelector('.period')?.textContent.includes('12月3日'))
   assert.match(await screen.locator('.trip-items').innerText(),/大米|青菜/)
   await screen.locator('.ingredients-heading').click()
   assert.equal(await screen.locator('.ingredient-line').count(),2)
   await screen.locator('.ingredient-lines').scrollIntoViewIfNeeded()
   assert.match(await screen.locator('.ingredient-lines').innerText(),/500g\/包/)
   await screen.locator('.fees-heading').click()
   await screen.locator('.fee-card').scrollIntoViewIfNeeded()
   assert.match(await screen.locator('.fee-card').innerText(),/整周配送费（3次）/)
   if(width===390)await page.screenshot({path:path.join(output,'confirmation-fees-390.png')})
   await screen.getByLabel('增加大米数量').click()
   await page.waitForFunction(()=>document.querySelector('.footer-amount')?.textContent==='¥48.00')
   await screen.getByLabel('取消选择青菜',{exact:true}).click()
   await page.waitForFunction(()=>document.querySelectorAll('.delivery-tab').length===1)
   assert.equal(await screen.locator('.ingredient-line').count(),2)
   assert.match(await screen.locator('.ingredients-heading').innerText(),/共1项/)
   await screen.getByLabel('选择青菜',{exact:true}).click()
   await page.waitForFunction(()=>document.querySelectorAll('.delivery-tab').length===3)
   if(width===390){await screen.locator('.ingredient-lines').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'editable-ingredients-390.png')})}
   assert.equal(await screen.locator('.edit-ingredients').count(),0)
   assert.equal(await screen.locator('.preparation-card').count(),1)

   await screen.locator('.slot-option').last().click()
   await screen.locator('.trip-time').first().filter({hasText:'12:00–13:00'}).waitFor()
   assert.ok(quoteCount>=2)
   await screen.getByLabel('返回计划').click()
   await page.locator('.exclusive-confirmation').waitFor({state:'detached'})
   await page.waitForURL('**/#/pages/chat/index')
   pendingRules=true
   await page.goto('http://127.0.0.1:'+server.address().port+'/family-app/#/pages/index/index')
   await page.waitForURL('**/#/pages/chat/index')
   await page.evaluate(url=>{location.hash='#'+url},'/pages/exclusive-plans/detail?group_id='+group+'&tier=economy&purchase=1')
   await page.locator('.error-card').filter({hasText:'储存规则待核对'}).waitFor()
   assert.equal(await page.locator('.exclusive-confirmation .delivery-tab').count(),3)
   assert.match(await page.locator('.delivery-card .count-label').innerText(),/预览/)
   assert.match(await page.locator('.trip-items').innerText(),/大米|青菜/)
   assert.match(await page.locator('.trip-items').innerText(),/包装数量待分配/)
   assert.match(await page.locator('.readonly-note').innerText(),/尚未预约/)
   assert.equal(await page.locator('.footer-amount').innerText(),'待确认')
   await chooseDate(page,'2026-12-04',1)
   assert.equal(await page.locator('.footer-amount').innerText(),'待确认')
   assert.equal(await page.locator('.date-control').getAttribute('data-date'),'2026-12-04')
   if(width===390){await page.locator('.settings-card').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'date-selected-pending-390.png')})}
   noAddress=true;noSlots=true
   await page.goto('http://127.0.0.1:'+server.address().port+'/family-app/#/pages/index/index')
   await page.waitForURL('**/#/pages/chat/index')
   await page.evaluate(url=>{location.hash='#'+url},'/pages/exclusive-plans/detail?group_id='+group+'&tier=economy&purchase=1')
   await page.locator('.recipient').filter({hasText:'选择收货地址'}).waitFor()
   assert.equal(await page.locator('.slot-option').count(),3)
   assert.equal(await page.locator('.slot-option.selected').innerText(),'12:00–13:00')
   await page.locator('.slot-option').filter({hasText:'11:00–12:00'}).click()
   assert.equal(await page.locator('.slot-option.selected').innerText(),'11:00–12:00')
   assert.doesNotMatch(await page.locator('.settings-card').innerText(),/选择地址后查看|尚未配置/)
   if(width===390)await page.screenshot({path:path.join(output,'default-slots-without-address-390.png')})
   assert.equal(await page.locator('.delivery-tab').count(),3)
   assert.match(await page.locator('.delivery-card .count-label').innerText(),/预览/)
   if(width===390){await page.locator('.delivery-card').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'delivery-preview-without-address-390.png')})}
   noAddress=false
   await page.goto('http://127.0.0.1:'+server.address().port+'/family-app/#/pages/index/index')
   await page.waitForURL('**/#/pages/chat/index')
   await page.evaluate(url=>{location.hash='#'+url},'/pages/exclusive-plans/detail?group_id='+group+'&tier=economy&purchase=1')
   await page.locator('.recipient').filter({hasText:'合成收件人'}).waitFor()
   assert.equal(await page.locator('.slot-option').count(),3)
   assert.equal(await page.locator('.slot-option.selected').innerText(),'11:00–12:00')
   assert.equal(await page.locator('.footer-amount').innerText(),'待确认')
   // Synthetic long-week fixture exercises horizontal tabs and list expansion.
   items.push({sku_id:'oil',food:'食用油',quantity:1,quantity_confirmed:false,sku:sku('oil','食用油',100)},{sku_id:'eggs',food:'鸡蛋',quantity:1,quantity_confirmed:false,sku:sku('eggs','鸡蛋',100)})
   for(const item of items)item.sku.image_url='http://127.0.0.1:'+server.address().port+'/family-app/static/bundles/'+({rice:'grains',greens:'cucumber',oil:'oats',eggs:'eggs'}[item.sku_id])+'.webp'
   purchase.delivery_suggestions.batches=Array.from({length:7},(_,i)=>({day_no:i+1,items:(i===0?items:[items[1]]).map(item=>({product:{sku_id:item.sku_id},use_days:[i+1]}))}))
   await page.evaluate(ids=>{for(const key of Object.keys(localStorage).filter(k=>k.includes('meal-purchase-selection'))){const record=JSON.parse(localStorage.getItem(key)),data=record.data||record;data.known=ids;data.selected=ids;data.firstMealDate='2026-12-04';localStorage.setItem(key,JSON.stringify(record))}},items.map(item=>item.sku_id))
   await page.goto('http://127.0.0.1:'+server.address().port+'/family-app/#/pages/index/index')
   await page.waitForURL('**/#/pages/chat/index')
   await page.evaluate(url=>{location.hash='#'+url},'/pages/exclusive-plans/detail?group_id='+group+'&tier=economy&purchase=1')
   await page.locator('.delivery-tab').nth(6).waitFor()
   assert.equal(await page.locator('.trip-item').count(),3)
   await page.locator('.detail-toggle').click();assert.equal(await page.locator('.trip-item').count(),4)
   await page.locator('.detail-toggle').click();assert.equal(await page.locator('.trip-item').count(),3)
   await page.getByRole('tab',{name:'查看第7趟配送',exact:true}).click()
   assert.equal(await page.locator('.trip-item').count(),1)
   assert.match(await page.locator('.delivery-tab.selected').innerText(),/第07趟/)
   await page.getByRole('tab',{name:'查看第1趟配送',exact:true}).click()
   assert.equal(await page.locator('.trip-item').count(),3)
   await page.locator('.preparation-heading').click()
   assert.match(await page.locator('.preparation-items').innerText(),/姜/)
   await page.locator('.preparation-heading').click()
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true)
   if(width===390){await page.locator('.date-control').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'b-delivery-tabs-390.png')})}
   results.push({width,readOnly:true,collapsedIngredients:true,inlineEditing:true,deselectionRestorable:true,wholeWeekFees:true,slotRequote:true,calendarSelection:true,calendarSelectionWithoutRules:true,defaultSlotsWithoutAddress:true,slotSelectionRestored:true,deliveryPreviewWithoutQuote:true,previewItemsExpandable:true,sevenTabs:true,selectionStableAcrossDates:true,collapsedReviewSections:true,unknownFeesNotZero:true,noOverflow:true})
  }catch(error){await page.screenshot({path:path.join(output,'failure-'+width+'.png')});console.error(page.url(),await page.locator('body').innerText());throw error}
  await context.close()
 }
 assert.deepEqual(errors,[])
 await fs.writeFile(path.join(output,'verification.json'),JSON.stringify({results,errors,provider:'synthetic API fixtures; built production components'},null,2)+'\n')
 console.log(JSON.stringify({results,errors}))
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}
