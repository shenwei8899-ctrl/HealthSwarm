import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || 'playwright')
const root = path.resolve(process.env.ONBOARDING_REPORT_H5)
const mime = {'.html':'text/html','.js':'application/javascript','.css':'text/css'}
const server = http.createServer(async (req, res) => {
  try {
    const name = decodeURIComponent(new URL(req.url, 'http://local').pathname)
    const file = path.resolve(root, '.' + (name === '/' ? '/index.html' : name))
    if (!file.startsWith(root + path.sep)) throw new Error('Invalid path')
    res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream')
    res.end(await fs.readFile(file))
  } catch { res.writeHead(404); res.end() }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
let browser
const family = '11111111-1111-4111-8111-111111111111'
const person = '22222222-2222-4222-8222-222222222222'
const health = '33333333-3333-4333-8333-333333333333'
const member = {
  id:person, name:'合成成员', relation:'本人', birthDate:'2000-01-01', gender:'女', height:165, weight:55,
  version:1, claimed:true, isSelf:true, confirmed:false, healthStatus:'none', conditions:[],
  goals:['饮食均衡'], tastePreferences:['不限口味'], cuisines:['不限菜系'],
  allergyStatus:'none', allergies:[], intoleranceStatus:'none', intolerances:[],
  avoidanceStatus:'none', avoidances:[], doctorStatus:'none', clinicianGuidance:'',
}
const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/jOYAAAAASUVORK5CYII=','base64')

try {
  browser = await chromium.launch({executablePath:process.env.ONBOARDING_REPORT_BROWSER,headless:true})
  for (const continueUpload of [true, false]) {
    const context = await browser.newContext({viewport:{width:390,height:844}})
    let saves = 0, uploads = 0
    await context.addInitScript(({family}) => localStorage.setItem('fn-session-v2:api', JSON.stringify({
      type:'object', data:{accountId:'1', accountName:'合成测试', householdId:family, token:'synthetic-report-test',
        authSource:'wechat', expiresAt:Date.now()/1000+86400, clientRevision:'report-test',
        families:[{id:family,name:'合成家庭',isOwner:true,onboardingRequired:false}]},
    })), {family})
    await context.route('**/api/**', async route => {
      const p = new URL(route.request().url()).pathname
      let data = {}, status = 200
      if (p.endsWith('/miniapp-profile')) {
        const write = route.request().method() === 'POST'
        if (write) saves++
        data = {source:'api', householdId:family, householdName:'合成家庭', familyVersion:1, usageMode:'个人使用',
          defaultDiners:[person], selfMemberId:person, isOwner:true, onboarded:!!saves, completeProfile:!!saves,
          members:[{...member,healthMemberId:saves?health:null,confirmed:!!saves}],
          ...(write?{memberRefs:{[person]:person}}:{})}
      } else if (p === '/api/health/v1/members') {
        data = saves ? [{id:health, display_name:member.name, scopes:['report_view','report_upload','profile_edit']}] : []
      } else if (p.endsWith('/configuration')) {
        data = {policy_version:'synthetic', report:{available:true,processor:'synthetic'}}
      } else if (p.includes('/vision/page')) data = {jobs:[],drafts:[],jobs_has_more:false,drafts_has_more:false}
      else if (p.endsWith('/uploads')) { uploads++; status = 500 }
      else if (p === '/api/auth/wechat/session') data = {wechat_authenticated:true,account:{id:1,name:'合成测试'},families:[{id:family,name:'合成家庭',is_owner:true,onboarding_required:false}]}
      await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
    })
    const page = await context.newPage(), errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.goto('http://127.0.0.1:'+server.address().port+'/#/pages/onboarding/index')
    try {
      await page.locator('.onboarding-next').click()
      await page.locator('.onboarding-next').click()
      await page.locator('.report-later').click()
      await page.getByText('选择体检报告',{exact:true}).waitFor()
      const chooser = page.waitForEvent('filechooser')
      await page.getByText('拍照或从相册选择',{exact:true}).click()
      await (await chooser).setFiles({name:'synthetic-report.png',mimeType:'image/png',buffer:image})
      await page.getByText('保留已选文件',{exact:true}).click()
      await page.getByText('已选 1 个文件，待上传',{exact:true}).waitFor()
      assert.equal(saves,0)
      await page.locator(continueUpload?'.onboarding-next':'.skip-report').click()
      if (continueUpload) {
        await page.waitForURL('**/pages/health/vision?kind=report&onboarding=upload&memberId='+health)
        await page.locator('.selected-file').waitFor()
        assert.match(await page.locator('.report-member').innerText(), /合成成员/)
        await page.getByLabel('返回',{exact:true}).click()
      }
      await page.waitForURL('**/pages/chat/index')
      assert.equal(saves,1)
      assert.equal(uploads,0)
      assert.deepEqual(errors,[])
      console.log(continueUpload?'selected files reach the exact report member':'skipping selected files completes onboarding')
    } catch (error) {
      console.error(page.url(), (await page.locator('body').innerText()).slice(0,1200), errors)
      throw error
    } finally { await context.close() }
  }
} finally {
  await browser?.close()
  await new Promise(resolve => server.close(resolve))
}
