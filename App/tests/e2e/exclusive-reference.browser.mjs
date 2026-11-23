import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import { createRequire } from 'node:module'
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE)
const root = path.resolve(process.env.EXCLUSIVE_H5)
const server = http.createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/family-app\//, '/')
    const file = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname))
    if (!file.startsWith(root + path.sep)) throw Error('invalid path')
    res.setHeader('Content-Type', {'.html':'text/html','.js':'application/javascript','.css':'text/css'}[path.extname(file)] || 'application/octet-stream')
    res.end(await fs.readFile(file))
  } catch { res.writeHead(404); res.end() }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const browser = await chromium.launch({executablePath:process.env.EXCLUSIVE_BROWSER,headless:true})
const family = '11111111-1111-4111-8111-111111111111'
const group = '22222222-2222-4222-8222-222222222222'
const errors = []
try {
  for (const width of [390, 320, 430]) {
    const context = await browser.newContext({viewport:{width,height:844}})
    await context.addInitScript(({family}) => localStorage.setItem('fn-session-v2:api', JSON.stringify({
      type:'object',data:{accountId:'1',accountName:'合成测试',householdId:family,token:'synthetic-exclusive-test',
        authSource:'wechat',expiresAt:Date.now()/1000+86400,clientRevision:'exclusive-test',
        families:[{id:family,name:'合成家庭',isOwner:true,onboardingRequired:false}]},
    })), {family})
    const pricing = {matched_subtotal_cent:null,unpriced_ingredients:[{ingredient:'菠菜适量'}],complete_estimate:false,
      notice:'小计不代表完整计划预算，不用于比较三档总费用。'}
    const detail = {group_id:group,tier_name:'标准型',difference:'以适中食材费用为目标；实际完整费用尚未核定',
      members:[{display_alias:'合成成员'}],notice:'当前沿用今日餐单口径，未作专业审核，个人营养量和家庭份量尚未核定。',pricing,
      days:Array.from({length:21},(_,index)=>index+1).map(day => ({day_no:day,plan_date:`2099-01-${String(day).padStart(2,'0')}`,
        meals:['breakfast','lunch','lunch'].map((type,index) => ({id:type+day+index,meal_type:type,recipe_name:type==='lunch'?(index===1?'清蒸鱼':'时蔬炒饭'):day===1?'鸡蛋蔬菜饭':'菠菜豆腐煲',
          recipe_snapshot:{image_url:'/family-app/static/food/'+(type==='breakfast'?'chat-meals/oatmeal.jpg':'family-meal.jpg')},ingredients:[day===1?'鸡蛋1个':'菠菜适量'],steps:['加热至熟。'],source:{filename:'合成原谱.md'}})),
        procurement:{ingredients:[{ingredient:day===1?'鸡蛋1个':'菠菜适量',recipe_name:day===1?'鸡蛋蔬菜饭':'菠菜豆腐煲',detail:'尚未匹配商品；可自行准备或待确认'}],
          purchase_gaps:[{ingredient:day===1?'鸡蛋1个':'菠菜适量',detail:'尚未匹配商品；可自行准备或待确认'}],matched_items:[],pricing}}))}
    detail.days[20].meals=Array.from({length:8},(_,i)=>({id:'long-dish-'+i,meal_type:'breakfast',recipe_name:i===7?'超长菜品名称用于验证小屏文字换行与底栏间距':'合成菜品'+i,
      recipe_snapshot:{},ingredients:Array.from({length:25},(_,n)=>'合成食材 '+n+' · 用量待确认'),steps:Array.from({length:35},(_,n)=>'合成步骤 '+n+'：保留原菜谱说明，不推断用量。')}))
    const productImage='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZlX8AAAAASUVORK5CYII='
    const purchasePaths=[]
    let emptyCatalog=false
    await context.route('**/api/**', route => {
      const p = new URL(route.request().url()).pathname
      let data = {}
      if(p.endsWith('/purchase')&&p.includes('/tiers/')){
        purchasePaths.push(p)
        data={scope_hash:'a'.repeat(64),available:!emptyCatalog,days:21,notice:'采购范围为整份21天计划；包装数量可调整，不代表已核定家庭21天用量。未匹配食材需自行准备。',
          items:emptyCatalog?[]:[{sku_id:'rice',quantity:5,quantity_confirmed:false,sku:{product_name:'合成大米',sku_name:'500克',image_url:productImage}},{sku_id:'egg',quantity:2,quantity_confirmed:true,sku:{product_name:'合成鸡蛋',sku_name:'6枚',image_url:productImage}}],gaps:[{ingredient:'菠菜',detail:'尚未匹配商品；可自行准备或待确认'}]}
      }
      else if (p.includes('/tiers/')) data = detail
      else if (p.endsWith('/exclusive-plans')) data = {status:'ready',group_id:group,preview_only:true,notice:detail.notice,
        plans:['economy','standard','premium'].map(tier_code => ({tier_code,difference:'按食材费用水平设定目标',pricing}))}
      else if (p === '/api/auth/wechat/session') data = {wechat_authenticated:true,account:{id:1,name:'合成测试'},families:[{id:family,name:'合成家庭',is_owner:true,onboarding_required:false}]}
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})
    })
    const page = await context.newPage()
    page.on('pageerror', error => errors.push(error.message))
    const base = 'http://127.0.0.1:'+server.address().port+'/family-app/'
    await page.goto(base+'#/pages/index/index')
    await page.waitForFunction(() => document.body.innerText.length > 0)
    await page.evaluate(url => { location.hash = '#' + url }, '/pages/exclusive-plans/detail?group_id='+group+'&tier=standard')
    try { await page.locator('.dish-name').filter({hasText:'鸡蛋蔬菜饭'}).waitFor({timeout:15000}) }
    catch (error) {
      console.log('Browser failure:', page.url(), errors, await page.locator('body').innerText())
      await page.screenshot({path:path.join(process.env.EXCLUSIVE_SCREENSHOTS,'failure.png'),fullPage:true})
      throw error
    }
    assert.equal(await page.locator('.detail-screen').filter({hasText:/费用为目标|未作专业审核|合成成员|原谱食材|做法|食材清单|已匹配食材小计|未计价食材|菜谱来源/}).count(),0)
    await page.locator('#plan-day-2').click()
    await page.locator('.dish-name').filter({hasText:'菠菜豆腐煲'}).waitFor()
    await page.locator('#plan-meal-lunch').click()
    assert.equal(await page.locator('.dish-name').count(),2)
    assert.match(await page.locator('.meal-list').innerText(),/清蒸鱼/)
    await page.getByLabel('查看清蒸鱼菜谱',{exact:true}).click()
    await page.locator('.detail-panel .single-dish').filter({hasText:'清蒸鱼'}).waitFor()
    await page.getByText('加热至熟。',{exact:true}).waitFor()
    await page.locator('.detail-panel-close').click()
    assert.equal(await page.locator('.detail-panel').count(),0)
    await page.locator('.meal-ingredients').click()
    assert.equal(await page.locator('.ingredient-group').count(),2)
    assert.match(await page.locator('.ingredient-group').first().innerText(),/菠菜适量/)
    await page.locator('.detail-panel-close').click()
    assert.equal(await page.locator('#plan-meal-lunch').getAttribute('aria-pressed'),'true')
    await page.waitForFunction(()=>[...document.querySelectorAll('.recipe-block img')].every(img=>img.complete&&img.naturalWidth>0))
    await page.screenshot({path:path.join(process.env.EXCLUSIVE_SCREENSHOTS,`detail-lunch-${width}.png`),fullPage:true})
    await page.locator('#plan-meal-dinner').click()
    await page.getByText('这一餐的菜品暂不可用',{exact:true}).waitFor()
    await page.locator('#plan-day-1').click()
    await page.locator('.dish-name').filter({hasText:'鸡蛋蔬菜饭'}).waitFor()
    assert.equal(await page.getByText('选择配送安排',{exact:false}).count(),0)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),false)
    await page.screenshot({path:path.join(process.env.EXCLUSIVE_SCREENSHOTS,`detail-${width}.png`),fullPage:true})

    await page.locator('#plan-day-21').click()
    assert.equal(await page.locator('.dish-name').count(),8)
    await page.evaluate(()=>window.scrollTo(0,document.documentElement.scrollHeight))
    const bottom=await page.locator('.meal-ingredients').evaluate(el=>({bottom:el.getBoundingClientRect().bottom,footer:document.querySelector('.plan-fixed').getBoundingClientRect().top}))
    assert.ok(bottom.bottom<=bottom.footer,'last meal row stays above the fixed purchase bar')
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false)
    await page.getByLabel('查看合成菜品0菜谱',{exact:true}).click()
    await page.locator('.detail-panel .recipe-step').last().waitFor()
    await page.waitForFunction(()=>{const s=document.querySelector('.detail-panel-scroll .uni-scroll-view-scrollbar-hidden');return s&&s.scrollHeight>s.clientHeight+100})
    const scrolling=await page.locator('.detail-panel-scroll').evaluate(el=>{const s=el.querySelector('.uni-scroll-view-scrollbar-hidden');s.scrollTop=s.scrollHeight;return {top:s.scrollTop,overflow:s.scrollHeight-s.clientHeight}})
    assert.ok(scrolling.overflow>100&&scrolling.top>100,'recipe panel scrolls independently')
    await page.screenshot({path:path.join(process.env.EXCLUSIVE_SCREENSHOTS,`recipe-panel-${width}.png`)})
    await page.locator('.detail-panel-close').click()
    await page.locator('.meal-ingredients').click()
    assert.equal(await page.locator('.ingredient-group').count(),8)
    await page.waitForFunction(()=>{const s=document.querySelector('.detail-panel-scroll .uni-scroll-view-scrollbar-hidden');return s&&s.scrollHeight>s.clientHeight+100})
    const ingredientScroll=await page.locator('.detail-panel-scroll').evaluate(el=>{const s=el.querySelector('.uni-scroll-view-scrollbar-hidden');s.scrollTop=s.scrollHeight;return s.scrollTop})
    assert.ok(ingredientScroll>100)
    await page.screenshot({path:path.join(process.env.EXCLUSIVE_SCREENSHOTS,`ingredients-panel-${width}.png`)})
    await page.locator('.detail-panel-backdrop').click({position:{x:5,y:5}})
    assert.equal(await page.locator('.detail-panel').count(),0)
    await page.locator('#plan-day-1').click()
    await page.evaluate(()=>window.scrollTo(0,0))
    assert.match((await page.locator('.plan-fixed .plan-primary').innerText()).trim(),/购买计划/)
    await page.locator('.plan-fixed .plan-primary').click()
    await page.getByText('整份 21 天计划',{exact:true}).waitFor()
    await page.getByText('合成大米',{exact:true}).waitFor()
    assert.equal(await page.locator('.check.selected').count(),2)
    assert.equal(await page.locator('.section-head').count(),0)
    assert.match(await page.locator('.purchase-coverage').innerText(),/不代表已核定家庭21天用量/)
    assert.match(await page.locator('.quantity-warning').innerText(),/包装数量待确认/)
    assert.match(await page.locator('.purchase-coverage-gaps').innerText(),/菠菜.*尚未匹配商品/s)
    assert.equal(await page.getByText(/参考餐单用量|家中已有可取消/).count(),0)
    await page.getByLabel('增加合成大米数量',{exact:true}).click()
    assert.match(await page.locator('.product').first().innerText(),/6 包/)
    await page.getByLabel('取消选择合成鸡蛋',{exact:true}).click()
    assert.equal(await page.locator('.check.selected').count(),1)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),false)
    assert.ok(purchasePaths.every(p=>p===`/api/health/v1/families/${family}/exclusive-plans/${group}/tiers/standard/purchase`))
    await page.waitForFunction(() => [...document.querySelectorAll('.product-image img')].length===2 && [...document.querySelectorAll('.product-image img')].every(image=>image.complete&&image.naturalWidth>0))
    const geometry=await page.locator('.product').evaluateAll(rows=>rows.map(row=>{
      const rect=selector=>{const {left,right,top,bottom,width}=row.querySelector(selector).getBoundingClientRect();return {left,right,top,bottom,width}}
      return {image:rect('.product-image'),name:rect('.product-name'),copy:rect('.product-copy'),price:rect('.product-price'),quantity:rect('.quantity-control')}
    }))
    for(const row of geometry){assert.equal(Math.round(row.image.width),52);assert.ok(row.image.right+8<=row.name.left);assert.ok(row.copy.right<=row.price.left);assert.ok(row.quantity.right<=row.price.left)}
    // Long names grow within their own column without covering adjacent controls.
    await page.locator('.product-name').first().evaluate(element=>element.textContent='新鲜有机蔬菜家庭装超长商品名称')
    const longLayout=await page.locator('.product').first().evaluate(row=>({image:row.querySelector('.product-image').getBoundingClientRect().right,name:row.querySelector('.product-name').getBoundingClientRect().left,scroll:row.querySelector('.product-copy').scrollWidth,width:row.querySelector('.product-copy').clientWidth}))
    assert.ok(longLayout.image+8<=longLayout.name);assert.ok(longLayout.scroll<=longLayout.width+1)
    const footer=await page.locator('.meal-bottom-bar').evaluate(bar=>[bar.querySelector('.selection-summary>uni-text:first-child'),bar.querySelector('.amount'),bar.querySelector('.checkout-button')].map(element=>({font:getComputedStyle(element).fontSize,center:element.getBoundingClientRect().top+element.getBoundingClientRect().height/2,text:element.innerText})))
    assert.equal(footer[0].text,'商品小计');assert.deepEqual(footer.map(item=>item.font),['14px','14px','14px']);assert.ok(Math.max(...footer.map(item=>item.center))-Math.min(...footer.map(item=>item.center))<=1)
    await page.screenshot({path:path.join(process.env.EXCLUSIVE_SCREENSHOTS,`purchase-${width}.png`),fullPage:true})
    emptyCatalog=true
    await page.evaluate(() => { location.hash = '#/pages/exclusive-plans/index' }); await page.locator('.plan-option').first().waitFor(); await page.locator('.plan-option').nth(1).click(); await page.locator('.dish-name').first().waitFor(); await page.locator('.plan-fixed .plan-primary').click()
    await page.getByText('暂无可购买商品',{exact:true}).waitFor()
    assert.equal(await page.locator('.checkout-button').count(),0)
    await page.evaluate(() => { location.hash = '#/pages/exclusive-plans/index' })
    await page.locator('.plan-option').first().waitFor()
    assert.equal(await page.locator('.plan-option').count(),3)
    await page.waitForFunction(() => {
      const images = [...document.querySelectorAll('.plan-option img')]
      return images.length === 3 && images.every(image => image.complete && image.naturalWidth > 0)
    })
    const artSources = await page.locator('.plan-option img').evaluateAll(images => images.map(image => image.src))
    assert.equal(new Set(artSources).size,3)
    assert.equal(await page.locator('.plan-option').filter({hasText:/费用为目标|已匹配食材小计|暂无可核算小计|未计价食材|完整费用未核定/}).count(),0)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),false)
    await page.screenshot({path:path.join(process.env.EXCLUSIVE_SCREENSHOTS,`overview-${width}.png`),fullPage:true})
    await page.locator('.plan-option').nth(1).click()
    await page.locator('.dish-name').filter({hasText:'鸡蛋蔬菜饭'}).waitFor()
    await context.close()
  }
  assert.deepEqual(errors,[])
  console.log('Passed: A-style details, 21-day and meal switching, saved recipe and ingredient panels, independent scrolling, long names, eight dishes, empty meals, images and whole-plan procurement at 320/390/430px; synthetic HTTP responses.')
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)) }
