// Reuse the existing synthetic session/API fixture; test the compiled page layout.
import fs from 'node:fs'
import path from 'node:path'
const source=fs.readFileSync(new URL('./history-preview.browser.mjs',import.meta.url),'utf8')
const prefix=source.split('try{\n  await page.goto')[0]
  // Default-deny every external request. The later API handler fulfills synthetic
  // responses locally; even its event stream must never continue to the server.
  .replace("await context.route('**/api/**'", "await context.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort())\nawait context.route('**/api/**'")
  .replace("if(p.endsWith('/events'))return route.continue()", "if(p.endsWith('/events'))return route.fulfill({status:200,contentType:'text/event-stream',body:': synthetic\\n\\n'})")
if(!prefix.includes('const page=await context.newPage()'))throw new Error('Fixture prefix changed')
const checks=String.raw`
const results=[]
const networkErrors=[]
page.on('requestfailed',r=>networkErrors.push({url:r.url(),error:r.failure()}))
page.on('response',r=>{if(r.status()>=400)networkErrors.push({url:r.url(),status:r.status()})})
try{
  await page.goto('http://127.0.0.1:'+server.address().port+'/#/pages/chat/index')
  await page.locator('.history-button').waitFor()
  const pages=[
    ['records','/pages/records/index','饮食记录'],
    ['record-detail','/pages/records/detail?id=synthetic&memberId='+member,'饮食记录详情'],
    ['memories','/pages/memories/index','AI 记住的事'],
    ['feedback','/pages/feedback/index','饮食反馈'],
    ['plans','/pages/exclusive-plans/index','AI 专属计划'],
    ['plan-detail','/pages/exclusive-plans/detail?id=synthetic','计划详情'],
    ['schedule','/pages/exclusive-plans/schedule?id=synthetic','配送安排'],
    ['meal-plans','/pages/health/plans?memberId='+member,'我的餐单'],
    ['indicators','/pages/indicators/index?memberId='+member,'实测记录回顾'],
    ['shared','/pages/family-shared/index?memberId='+member,'实测指标与修改历史'],
    ['report-upload','/pages/health/vision?kind=report&memberId='+member,'上传报告'],
    ['meal-photo','/pages/meal-photo/index?memberId='+member,'拍照记餐'],
    ['orders','/pages/orders/index','我的订单'],
    ['settings','/pages/settings/index','设置'],
    ['addresses','/pages/address/index','收货地址'],
  ]
  for(const width of [320,375,390,430]){
    await page.setViewportSize({width,height:844})
    for(const [name,url,title] of pages){
      await page.evaluate(()=>{location.hash='#/pages/chat/index'})
      await page.locator('.history-button').waitFor()
      await page.evaluate(url=>{location.hash='#'+url},url)
      const heading=page.locator('.app-nav-title:visible').filter({hasText:title}).first()
      await heading.waitFor({timeout:10000})
      await page.waitForFunction(title=>Array.from(document.querySelectorAll('.app-nav-title')).some(el=>{
        const r=el.getBoundingClientRect()
        return el.textContent===title&&r.width>0&&el.parentElement.style.getPropertyValue('--nav-title-width')&&Math.abs(r.x+r.width/2-innerWidth/2)<=1
      }),title)
      const box=await heading.boundingBox()
      const error=Math.abs(box.x+box.width/2-width/2)
      assert.ok(error<=1, name+' at '+width+' has center error '+error)
      assert.equal(await heading.evaluate(el=>getComputedStyle(el).textOverflow),'ellipsis')
      results.push({name,width,title,centerError:error})
      if(width===390&&['records','memories','orders'].includes(name))await page.screenshot({path:path.join(evidence,name+'-390.png')})
    }
  }
  // A resize of an already mounted page must update the measured center too.
  await page.setViewportSize({width:1024,height:844})
  await page.waitForFunction(()=>{
    const el=Array.from(document.querySelectorAll('.app-nav-title')).find(el=>el.textContent==='收货地址'&&el.getBoundingClientRect().width>0),r=el?.getBoundingClientRect()
    return r&&Math.abs(r.x+r.width/2-innerWidth/2)<=1
  })
  assert.deepEqual(errors,[])
  await fs.writeFile(path.join(evidence,'results.json'),JSON.stringify({checks:results.length,results,errors},null,2))
  console.log(JSON.stringify({checks:results.length,errors}))
}catch(error){
  await page.screenshot({path:path.join(evidence,'failure.png')})
  await fs.writeFile(path.join(evidence,'failure.json'),JSON.stringify({url:page.url(),text:await page.locator('body').innerText(),errors,requests,networkErrors,results},null,2))
  throw error
}finally{
  for(const stream of streams)stream.end()
  await browser.close()
  await new Promise(resolve=>server.close(resolve))
}
`
const target=path.resolve(process.env.HISTORY_BROWSER_EVIDENCE||path.resolve(import.meta.dirname,'../../output/nav-centering'),'nav-browser-runner.mjs')
fs.mkdirSync(path.dirname(target),{recursive:true})
fs.writeFileSync(target,prefix+checks)
await import('node:url').then(({pathToFileURL})=>import(pathToFileURL(target)))
