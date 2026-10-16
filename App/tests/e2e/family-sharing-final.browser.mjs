import fs from 'node:fs/promises'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
const { chromium } = createRequire(import.meta.url)('playwright')
const dir=process.env.FORMAL_CLIENT_EVIDENCE
assert.ok(dir, 'FORMAL_CLIENT_EVIDENCE is required')
const fixture=JSON.parse(await fs.readFile(`${dir}/fixture.json`,'utf8'))
const browser=await chromium.launch({headless:true}),page=await browser.newPage({viewport:{width:420,height:900}})
const button=text=>page.locator('uni-button:not([disabled])').filter({hasText:new RegExp('^'+text+'$')})
const field=label=>page.locator('.archive-field').filter({has:page.locator('uni-text').filter({hasText:label})}).locator('input,textarea')
const errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/measurements'))writes.push(r.url())})
try{
 await page.goto('http://127.0.0.1:15187/')
 const account=page.locator('uni-input').filter({hasText:'业务账号 UID 或手机号'}).locator('input'),password=page.locator('uni-input').filter({hasText:'业务账号密码'}).locator('input')
 await account.fill('formal_owner');await password.fill('wrong-synthetic-password');await button('登录家庭档案').click()
 await page.locator('.business-login .login-error').waitFor();assert.ok(await page.locator('.business-login .login-error').isVisible())
 await page.screenshot({path:`${dir}/login-error.png`})
 await password.fill(fixture.password);await button('登录家庭档案').click();await page.waitForURL('**/pages/account/index')
 await button('合成共享家庭').click();await button('查看与维护家庭共享档案').click();await page.waitForURL('**/pages/family-shared/index')
 await button('共享验收成员 · 未认领').click();await button('记录体重').click()
 await field('体重（kg）').fill('62');await field('测量时间（本地时间 YYYY-MM-DDTHH:mm）').fill('2026-02-31T10:00');await button('保存实测记录').click()
 await page.getByText('测量日期或时间不存在，请核对后填写',{exact:true}).waitFor();assert.equal(writes.length,0)
 await page.screenshot({path:`${dir}/invalid-date.png`})
 await button('取消').click();await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:`${dir}/shared-final.png`})
 assert.deepEqual(errors,[])
 await fs.writeFile(`${dir}/final-browser-result.json`,JSON.stringify({status:'passed',loginErrorVisible:true,invalidDateBlockedBeforeNetwork:true,pageErrors:errors},null,2));console.log('final browser checks passed')
}finally{await browser.close()}
