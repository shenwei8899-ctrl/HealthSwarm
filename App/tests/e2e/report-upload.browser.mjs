// Runs the real H5 page against synthetic endpoints. No real reports or providers are used.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import { createRequire } from 'node:module'
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || 'playwright')
assert.ok(process.env.REPORT_H5_BUILD && process.env.REPORT_BROWSER_EVIDENCE, 'REPORT_H5_BUILD and REPORT_BROWSER_EVIDENCE are required')
const root = path.resolve(process.env.REPORT_H5_BUILD), evidence = path.resolve(process.env.REPORT_BROWSER_EVIDENCE)
await fs.mkdir(evidence, { recursive: true })
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.webp': 'image/webp' }
const server = http.createServer(async (req, res) => {
  try {
    const name = decodeURIComponent(new URL(req.url, 'http://local').pathname)
    const file = path.resolve(root, '.' + (name === '/' ? '/index.html' : name))
    if (!file.startsWith(root + path.sep)) throw Error('path')
    res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream' }); res.end(await fs.readFile(file))
  } catch { res.writeHead(404); res.end() }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const browser = await chromium.launch({ headless: true, executablePath: process.env.REPORT_BROWSER_EXE })
const context = await browser.newContext({ viewport: { width: 390, height: 844 } })
const family = '11111111-1111-4111-8111-111111111111', member = '22222222-2222-4222-8222-222222222222', draftId = '33333333-3333-4333-8333-333333333333'
const writes = [], errors = []
const entryReads=[]
const sourceMember='44444444-4444-4444-8444-444444444444'
let mode = 'normal', version = 1, confirmed = false, failTaskOnce = false, taskCreated = false
let payload = { fields: [{ field_id: 'field-a', name: '空腹血糖', value_raw: '5.2', value_numeric: null, unit_raw: 'mmol/L', reference_raw: '3.9–6.1', source: 'manual', observation_code: 'unknown', evidence: null, excluded: false }], pages: [{ page_index: 0, upload_id: 'synthetic-upload', upload_page_index: 0, status: 'success' }, { page_index: 1, upload_id: 'synthetic-upload', upload_page_index: 1, status: 'failed' }], excluded_pages: [] }
const draft = () => ({ id: draftId, member_id: member, kind: 'report', version, review_status: confirmed ? 'confirmed' : 'pending_confirmation', created_at: '2026-11-04T08:00:00Z', payload })
await context.addInitScript(({ family }) => localStorage.setItem('fn-session-v2:api', JSON.stringify({ type: 'object', data: { accountId: '1', householdId: family, token: 'synthetic-token', authSource: 'wechat', expiresAt: Date.now() / 1000 + 86400, clientRevision: 'synthetic', families: [{ id: family, name: '合成家庭', isOwner: true, onboardingRequired: false }] } })), { family })
await context.route('**/api/**', async route => {
  const req = route.request(), p = new URL(req.url()).pathname
  if(mode==='entry'&&req.method()==='GET')entryReads.push(p)
  if (req.method() !== 'GET') writes.push({ path: p, method: req.method(), body: req.postData(), key: req.headers()['idempotency-key'] })
  let data, status = 200
  if (p === '/api/auth/wechat/session') data = { wechat_authenticated: true, account: { id: 1, name: '合成测试' }, families: [{ id: family, name: '合成家庭', is_owner: true, onboarding_required: false }] }
  else if(p.endsWith('/miniapp-profile'))data={source:'api',householdId:family,householdName:'合成家庭',familyVersion:1,usageMode:'个人使用',defaultDiners:[sourceMember],selfMemberId:sourceMember,isOwner:true,onboarded:true,completeProfile:true,members:[{id:sourceMember,healthMemberId:member,name:'我',relation:'本人',birthDate:'1990-01-01',gender:'女',height:165,weight:55,version:1,claimed:true,isSelf:true,confirmed:true,healthStatus:'none',conditions:[],goals:[],tastePreferences:[],cuisines:[],allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],doctorStatus:'none',clinicianGuidance:''}]}
  else if(p==='/api/family/'+family)data={id:family,members:[{id:sourceMember,is_active:true,is_self:true,is_guardian:false,version:1,relationship_version:1,editable_fields:['height_cm'],profile:{birth_date:'1990-01-01'}}]}
  else if (p === '/api/health/v1/members') {
    if (mode === 'network') { await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ message: '合成网络错误' }) }); return }
    data = mode === 'empty' ? [] : [{ id: member, display_name: '我', scopes: mode === 'readonly' ? ['report_view'] : ['report_view', 'report_upload', 'profile_edit', 'ai_use'] }]
  } else if (p.endsWith('/configuration')) {
    if (mode === 'configuration-failure') { status = 503; data = { message: '合成配置读取失败' } }
    else data = { policy_version: 'test-policy', report: { available: !['unavailable','entry'].includes(mode), processor: '合成测试处理方', reason: '识别服务暂未就绪，可手动录入。' }, limits: { image_mb: 10, pdf_mb: 20, report_pages: 20 } }
  } else if (p.endsWith('/vision/page')) data = { jobs: taskCreated ? [{ task_id: 'synthetic-task', execution_status: 'success' }] : [], drafts: taskCreated ? [draft()] : [], jobs_next_offset: null, drafts_next_offset: null }
  else if (p.endsWith('/processing-consents')) data = { accepted: true }
  else if (p.endsWith('/uploads')) data = { upload_id: 'synthetic-upload', purpose: 'report', status: 'ready' }
  else if (p.endsWith('/preview')) { await route.fulfill({ status: 200, contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64') }); return }
  else if (p.endsWith('/report-tasks')) {
    if (failTaskOnce) { failTaskOnce = false; status = 503; data = { message: '合成任务响应丢失' } }
    else { taskCreated = true; data = { task_id: 'synthetic-task', execution_status: 'success' } }
  } else if (p.endsWith('/report-page-tasks')) data = { task_id: 'synthetic-task', execution_status: 'success' }
  else if (p.endsWith('/vision-tasks/synthetic-task')) data = { task_id: 'synthetic-task', kind: 'report', execution_status: 'success', result_id: draftId }
  else if (p.endsWith('/manual-drafts')) { taskCreated = true; confirmed = false; data = { id: draftId } }
  else if (p.endsWith('/report-extractions/' + draftId)) {
    if (req.method() === 'PATCH') { payload = req.postDataJSON().report; version++ }
    data = draft()
  } else if (p.endsWith('/confirm')) { confirmed = true; data = { confirmation_id: 'synthetic-receipt', review_status: 'confirmed', target_ids: ['synthetic-observation'] } }
  else if (p.endsWith('/observations')) data = [{ id: 'synthetic-observation' }]
  else { status = 404; data = { detail: 'Synthetic endpoint not included' } }
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
})
const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message)); page.setDefaultTimeout(12000)
const url = 'http://127.0.0.1:' + server.address().port + '/#/pages/health/vision?kind=report&memberId=' + member
async function open(nextMode = 'normal', width = 390) {
  mode = nextMode; await page.setViewportSize({ width, height: 844 })
  await page.goto(url.split('#')[0]); await page.waitForURL('**/#/pages/chat/index')
  await page.evaluate(hash => { location.hash = hash }, url.split('#')[1])
  await page.getByText('上传体检报告', { exact: true }).waitFor()
}
async function screenshot(name) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, 'Page must not overflow horizontally')
  await page.screenshot({ path: path.join(evidence, name + '.png'), fullPage: true })
}
try {
  await open(); await page.locator('.member-name').filter({ hasText: '我' }).waitFor(); await screenshot('01-upload')
  const chooser = page.waitForEvent('filechooser')
  await page.getByText('从微信聊天导入', { exact: true }).click()
  await (await chooser).setFiles({ name: 'synthetic-report.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\nsynthetic report') })
  await page.getByText('synthetic-report.pdf', { exact: true }).waitFor()
  await page.getByText('同意本次报告识别的数据处理', { exact: true }).click()
  failTaskOnce = true; await page.getByText('开始识别', { exact: true }).click()
  await page.getByText('确认上次操作结果', { exact: true }).waitFor(); await screenshot('02-recovery')
  await page.getByText('确认上次操作结果', { exact: true }).click()
  await page.getByText('查看并核对结果', { exact: true }).click()
  await page.getByText('报告指标', { exact: true }).waitFor()
  await page.getByText('对照这一页原图', { exact: false }).first().click()
  await page.locator('.report-preview').waitFor()
  assert.equal(await page.getByText('排除此页，不保存该页指标', { exact: true }).count(), 2)
  await page.getByText('重新识别这一页', { exact: true }).click()
  assert.deepEqual(JSON.parse(writes.find(row => row.path.endsWith('/report-page-tasks')).body).page_indices, [1])
  await page.getByText('查看并核对结果', { exact: true }).click()
  await page.getByText('报告指标', { exact: true }).waitFor()
  await page.locator('.indicator-values textarea').first().fill('5.3')
  await page.locator('.review-actions textarea').fill('按原报告核对结果')
  await page.getByText('保存指标修改', { exact: true }).click()
  await page.getByText('已核对，保存到档案', { exact: true }).waitFor()
  await screenshot('03-review')
  await page.getByText('已核对，保存到档案', { exact: true }).click()
  await page.getByText('已保存 1 项报告指标', { exact: true }).waitFor(); await screenshot('04-saved')
  assert.equal(writes.filter(row => row.path.endsWith('/processing-consents')).length, 1)
  const taskWrites = writes.filter(row => row.path.endsWith('/report-tasks'))
  assert.equal(taskWrites.length, 2); assert.equal(taskWrites[0].key, taskWrites[1].key); assert.equal(taskWrites[0].body, taskWrites[1].body)
  await page.getByText('继续上传报告', { exact: false }).click(); await page.getByText('添加报告', { exact: true }).waitFor()
  assert.equal(await page.getByText('还有未保存的修改', { exact: true }).count(), 0, 'A confirmed report must not trigger a dirty form dialog')
  await open('empty'); await page.getByText('暂无可用的报告成员', { exact: true }).waitFor(); await screenshot('05-no-member')
  await open('network'); await page.getByText('暂时无法读取成员', { exact: true }).waitFor(); await screenshot('06-member-error')
  mode = 'normal'; await page.getByText('重新加载成员', { exact: true }).click(); await page.locator('.member-name').filter({ hasText: '我' }).waitFor()
  await open('readonly', 320); await page.getByText('当前成员仅开放报告查看。上传新报告需要报告上传授权。', { exact: true }).waitFor(); await screenshot('07-readonly-320')
  assert.equal(await page.getByText('也可以手动录入指标', { exact: false }).count(), 0)
  await open('configuration-failure'); await page.getByText('合成配置读取失败', { exact: true }).waitFor()
  await page.getByText('待核对与历史任务', { exact: false }).click(); await page.getByText('已核对报告', { exact: true }).waitFor(); await screenshot('08-history-without-configuration')
  await open('unavailable'); await page.getByText('识别服务暂未就绪，可手动录入。', { exact: true }).waitFor()
  await page.getByText('也可以手动录入指标', { exact: false }).click(); await page.getByText('报告指标', { exact: true }).waitFor(); await screenshot('09-manual')
  await open('normal', 320); await page.locator('.member-name').filter({ hasText: '我' }).waitFor(); await screenshot('10-upload-320')
  await open('normal', 430); await page.locator('.member-name').filter({ hasText: '我' }).waitFor(); await screenshot('11-upload-430')
  mode='entry';await page.setViewportSize({width:390,height:844});await page.goto(url.split('#')[0]);await page.waitForURL('**/#/pages/chat/index')
  await page.evaluate(hash=>{location.hash=hash},'/pages/profile/member?id='+sourceMember)
  await page.getByText('已核对',{exact:true}).waitFor()
  assert.equal(await page.getByText('资源不存在或无权访问',{exact:true}).count(),0)
  assert.equal(entryReads.some(p=>p.endsWith('/observations')),true)
  await screenshot('12-archive-report-entry')
  await page.getByText('体检报告',{exact:true}).click()
  await page.getByText('添加报告',{exact:true}).waitFor();await page.getByText('也可以手动录入指标',{exact:false}).waitFor()
  assert.equal(writes.filter(row=>row.path.endsWith('/report-access')).length,0)
  await screenshot('13-report-opened-from-archive')
  payload={fields:[{field_id:'checkbox-field',name:'中耳功能',value_raw:'☑正常 ☐异常\t☐正常 ☑异常',value_numeric:null,unit_raw:'',reference_raw:'',source:'ocr',evidence:{block_id:'synthetic-row',page_index:0,raw_text:'中耳功能\t☑正常 ☐异常\t☐正常 ☑异常'},review_flags:['manual_review_required','checkbox_layout_unverified'],excluded:false}],pages:[],excluded_pages:[]}
  await page.getByText('也可以手动录入指标',{exact:false}).click()
  await page.getByLabel('报告勾选结果',{exact:true}).waitFor()
  assert.equal(await page.getByLabel('报告勾选结果',{exact:true}).locator('textarea').inputValue(),'☑正常 ☐异常\t☐正常 ☑异常')
  await page.getByText('保留原表勾选文字，请对照原图核对左右耳及合并单元格。',{exact:true}).waitFor()
  await page.setViewportSize({width:390,height:844})
  await screenshot('14-checkbox-review')
  await page.setViewportSize({width:320,height:844})
  await screenshot('15-checkbox-review-320')
  await page.getByText('待核对与历史任务',{exact:false}).click()
  await page.locator('.history-row').getByText('查看 ›',{exact:true}).first().click()
  await page.getByText('报告指标',{exact:true}).waitFor()
  await page.waitForFunction(()=>document.querySelector('.report-title')?.getBoundingClientRect().top>=0,{},{timeout:1500})
  await screenshot('16-history-task-opened')
  await page.locator('.history-row').getByText('查看 ›',{exact:true}).last().click()
  await page.waitForFunction(()=>document.querySelector('.report-title')?.getBoundingClientRect().top>=0,{},{timeout:1500})
  await page.locator('.indicator-values textarea').fill('合成未保存修改')
  await page.locator('.history-row').getByText('查看 ›',{exact:true}).first().click()
  await page.getByText('还有未保存的修改',{exact:true}).waitFor()
  await page.locator('.uni-modal').getByText('取消',{exact:true}).click()
  assert.equal(await page.locator('.indicator-values textarea').inputValue(),'合成未保存修改')
  await page.locator('.history-row').getByText('查看 ›',{exact:true}).first().click()
  await page.getByText('放弃修改',{exact:true}).click()
  await page.waitForFunction(()=>document.querySelector('.report-title')?.getBoundingClientRect().top>=0,{},{timeout:1500})
  assert.equal(await page.locator('.indicator-values textarea').inputValue(),'☑正常 ☐异常\t☐正常 ☑异常')
  assert.deepEqual(errors, [])
  const result = { passed: true, scenarios: ['upload-and-consent', 'exact-task-recovery', 'private-original-preview', 'page-exclusion-controls', 'failed-page-retry', 'edit-and-confirm', 'confirmed-form-clean', 'empty-members', 'member-retry', 'readonly-320', 'configuration-failure-retains-history', 'unavailable-manual', 'upload-layout-320', 'upload-layout-430','archive-family-report-history','archive-direct-report-navigation','checkbox-text-review','history-task-and-draft-scroll','history-unsaved-edit-protection'], errors }
  await fs.writeFile(path.join(evidence, 'result.json'), JSON.stringify(result, null, 2)); console.log(JSON.stringify(result))
} catch (error) { await screenshot('failure'); console.error((await page.locator('body').innerText()).slice(-6000)); throw error }
finally { await browser.close(); await new Promise(resolve => server.close(resolve)) }
