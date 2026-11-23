import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {join} from 'node:path'
import vm from 'node:vm'
import {parse,compileScript} from 'vue/compiler-sfc'

for(const name of ['MealRecordSheet','CloudMealCapture']){
 test(name+' preserves its virtual-host option through Vue compilation',()=>{
  const source=readFileSync(new URL('../src/components/'+name+'.vue',import.meta.url),'utf8')
  const {descriptor}=parse(source)
  const script=compileScript(descriptor,{id:'native-sheet-host'}).content
  assert.match(script,/virtualHost\s*:\s*true/)
 })
 test(name+' registers without a flex-breaking native host in the real WeChat build',{skip:!process.env.MEAL_RECORD_MINIAPP},()=>{
  const script=readFileSync(join(process.env.MEAL_RECORD_MINIAPP,'components',name+'.js'),'utf8')
  let registered=null
  const vendor={_export_sfc:(component)=>component,defineComponent:component=>component}
  vm.runInNewContext(script,{require:name=>name.includes('vendor')?vendor:{},wx:{createComponent:component=>{registered=component}},exports:{},Math})
  assert.equal(registered?.options?.virtualHost,true)
 })
}
