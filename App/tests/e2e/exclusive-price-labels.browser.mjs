import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE)
const root = path.resolve(process.env.EXCLUSIVE_H5)
const output = path.resolve(process.env.EXCLUSIVE_SCREENSHOTS)
await fs.mkdir(output, { recursive: true })
const server = http.createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/family-app\//, '/')
    const file = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname))
    assert.ok(file.startsWith(root + path.sep))
    res.setHeader('Content-Type', { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.webp': 'image/webp' }[path.extname(file)] || 'application/octet-stream')
    res.end(await fs.readFile(file))
  } catch { res.writeHead(404); res.end() }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const browser = await chromium.launch({ executablePath: process.env.EXCLUSIVE_BROWSER, headless: true })
const family = '11111111-1111-4111-8111-111111111111'
const group = '22222222-2222-4222-8222-222222222222'
const tiers = ['economy', 'standard', 'premium']
const names = ['经济型', '标准型', '品质型']
const prices = ['约 ¥10–20 /人/天', '约 ¥30–50 /人/天', '约 ¥50–100 /人/天']
const results = []
try {
  for (const width of [320, 390, 430]) {
    const context = await browser.newContext({ viewport: { width, height: 844 } })
    await context.addInitScript(({ family }) => localStorage.setItem('fn-session-v2:api', JSON.stringify({
      type: 'object', data: { accountId: '1', accountName: '合成测试', householdId: family, token: 'synthetic-price-test',
        authSource: 'wechat', expiresAt: Date.now() / 1000 + 86400, clientRevision: 'price-test',
        families: [{ id: family, name: '合成家庭', isOwner: true, onboardingRequired: false }] },
    })), { family })
    let status = 'ready', posts = 0
    await context.route('**/api/**', route => {
      const pathname = new URL(route.request().url()).pathname
      let data = {}
      if (pathname.endsWith('/exclusive-plans')) {
        if (route.request().method() === 'POST') { posts++; status = 'generating' }
        data = { status, group_id: status === 'empty' ? null : group, preview_only: true,notice:'当前沿用今日餐单口径且未作专业审核',
          plans: status === 'ready' ? tiers.map(tier_code => ({ tier_code })) : [] }
      } else if (pathname.includes('/tiers/')) {
        data = { group_id: group, tier_name: names[tiers.indexOf(pathname.split('/tiers/')[1])], days: [] }
      } else if (pathname === '/api/auth/wechat/session') {
        data = { wechat_authenticated: true, account: { id: 1, name: '合成测试' },
          families: [{ id: family, name: '合成家庭', is_owner: true, onboarding_required: false }] }
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
    })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const base = 'http://127.0.0.1:' + server.address().port + '/family-app/'
    await page.goto(base + '#/pages/index/index')
    await page.waitForFunction(() => document.body.innerText.length > 0)
    const open = async (enabled=true) => {
      await page.evaluate(() => { location.hash = '#/pages/exclusive-plans/index' })
      await page.locator(enabled?'.plan-option:not([disabled])':'.plan-option').first().waitFor()
    }
    await open()
    assert.equal(await page.locator('.plan-option').count(), 3)
    const readyCopy=await page.locator('.exclusive-overview').innerText()
    for(const removed of ['参考区间，实际费用以采购结算为准','配图为示意，具体菜品以实际计划为准','当前沿用今日餐单口径','换一套计划'])assert.equal(readyCopy.includes(removed),false)
    await page.waitForFunction(()=>{
      const images=[...document.querySelectorAll('.plan-option img')]
      return images.length===3&&images.every(image=>image.complete&&image.naturalWidth===300&&image.naturalHeight===210)
    })
    for (let index = 0; index < tiers.length; index++) {
      const card = page.locator('.plan-option').nth(index)
      assert.equal((await card.locator('.option-title').innerText()).trim(),names[index])
      assert.equal((await card.locator('.option-action-label').innerText()).trim(),'查看计划')
      assert.equal(await card.getAttribute('aria-label'),'查看计划，'+names[index]+'，'+prices[index])
      const geometry = await card.locator('.option-reference').evaluate(el => {
        const box = el.getBoundingClientRect(), card = el.closest('.plan-option').getBoundingClientRect()
        return { right: box.right, cardRight: card.right, scroll: el.scrollWidth, client: el.clientWidth }
      })
      assert.ok(geometry.right <= geometry.cardRight)
      assert.ok(geometry.scroll <= geometry.client + 1)
      const contentGeometry=await card.evaluate(el=>{
        const rect=selector=>el.querySelector(selector).getBoundingClientRect()
        return {copyRight:rect('.option-copy').right,imageLeft:rect('.option-art-frame').left,
          priceRight:rect('.option-reference').right,actionLeft:rect('.option-action').left,
          imageRight:rect('.option-art-frame').right,cardRight:el.getBoundingClientRect().right}
      })
      assert.ok(contentGeometry.copyRight<=contentGeometry.imageLeft,'copy does not overlap the gradient art')
      assert.ok(contentGeometry.priceRight+4<=contentGeometry.actionLeft,'reference price and action remain separate')
      assert.ok(contentGeometry.imageRight<=contentGeometry.cardRight)
    }
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
    await page.screenshot({ path: path.join(output, `cards-${width}.png`), fullPage: true })
    for (const tier of tiers) {
      await page.locator('.tier-' + tier).click()
      await page.waitForURL(url => url.hash.includes('tier=' + tier))
      await open()
    }
    assert.equal(posts, 0)
    status = 'empty'
    await page.goto(base + '#/pages/index/index')
    await page.waitForFunction(() => document.body.innerText.length > 0)
    await open()
    assert.equal(await page.locator('.option-caption').count(), 3)
    await page.locator('.tier-economy').click()
    await page.getByText('正在为家人准备计划，可以离开页面，稍后回来查看。', { exact: true }).waitFor()
    assert.equal(await page.locator('.option-action-label').filter({hasText:'正在生成'}).count(),3)
    assert.equal(await page.locator('.plan-option[disabled]').count(),3)
    assert.equal(posts, 1)
    status='failed'
    await page.goto(base+'#/pages/index/index')
    await page.waitForFunction(()=>document.body.innerText.length>0)
    await open(false)
    await page.getByText('计划暂时无法读取',{exact:true}).waitFor()
    assert.equal(await page.locator('.option-action-label').filter({hasText:'待重试'}).count(),3)
    assert.equal(await page.locator('.plan-option[disabled]').count(),3)
    await page.locator('.overview-retry').click()
    await page.getByText('正在为家人准备计划，可以离开页面，稍后回来查看。',{exact:true}).waitFor()
    assert.equal(posts,2)
    assert.deepEqual(errors, [])
    results.push({ width, cardCount: 3, overflow: false, tierNavigation: true, generationRequests: posts, errors })
    await context.close()
  }
  await fs.writeFile(path.join(output, 'browser-results.json'), JSON.stringify(results, null, 2) + '\n')
  console.log(JSON.stringify(results))
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)) }
