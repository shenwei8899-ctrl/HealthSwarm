import test from 'node:test'
import assert from 'node:assert/strict'
import config from '../vite.config.js'

test('WeChat build preserves the style path from chat through the layout composer slot',async()=>{
 const old=process.env.UNI_PLATFORM
 try {
  process.env.UNI_PLATFORM='mp-weixin'
  const options=await config({mode:'production'})
  const plugin=options.plugins.find(p=>p.name==='wechat-config')
  const bundle={}
  for(const name of ['CloudNutritionChat','NutritionistLayout','ChatWelcome']) {
   bundle[`components/${name}.json`]={type:'asset',source:JSON.stringify({component:true,usingComponents:{'app-icon':'./AppIcon'}})}
  }
  plugin.generateBundle({},bundle)
  const chat=JSON.parse(bundle['components/CloudNutritionChat.json'].source)
  const layout=JSON.parse(bundle['components/NutritionistLayout.json'].source)
  assert.equal(chat.styleIsolation,'shared')
  assert.equal(layout.styleIsolation,'apply-shared')
  assert.deepEqual(layout.usingComponents,{'app-icon':'./AppIcon'})
  assert.equal(JSON.parse(bundle['components/ChatWelcome.json'].source).styleIsolation,undefined)
 } finally {if(old===undefined)delete process.env.UNI_PLATFORM;else process.env.UNI_PLATFORM=old}
})
