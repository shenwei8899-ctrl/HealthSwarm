import {readFileSync,readdirSync,statSync} from 'node:fs'
import {resolve,join,relative} from 'node:path'
import assert from 'node:assert/strict'

const root=resolve(process.argv[2]||'dist/build/mp-weixin')
const extra=process.argv.slice(3)
assert.ok(extra.length===0||(extra.length===2&&extra[0]==='--wechat-info'),'Usage: check-miniapp-size.mjs [root] [--wechat-info preview-info.json]')
const project=JSON.parse(readFileSync(join(root,'project.config.json'),'utf8'))
const exclusions=project.packOptions?.ignore||[]
assert.ok(exclusions.every(item=>item.type==='file'),'Size check only supports exact file exclusions')
const excluded=new Set(exclusions.map(item=>item.value))
const files=[]
function walk(dir){for(const item of readdirSync(dir,{withFileTypes:true})){
 const path=join(dir,item.name)
 if(item.isDirectory())walk(path)
 else files.push({path,name:relative(root,path).replaceAll('\\','/'),bytes:statSync(path).size})
}}
walk(root)
const included=files.filter(f=>!excluded.has(f.name))
// Fail if a future page starts using an asset excluded from the upload.
for(const file of included.filter(f=>/\.(js|wxml|wxss|json)$/.test(f.name)&&f.name!=='project.config.json')){
 const text=readFileSync(file.path,'utf8')
 for(const name of excluded)assert.ok(!text.includes(name),`${file.name} references excluded ${name}`)
}
const bytes=included.reduce((sum,f)=>sum+f.bytes,0)
// Leave room for WeChat's own compilation and packaging overhead.
// 1.8 MiB of source produced a 2053 KiB main package in WeChat 2.02.2608080.
// This source budget is a warning gate, not proof that the compiled upload fits.
const budget=Math.floor(1.7*1024*1024)
const app=JSON.parse(readFileSync(join(root,'app.json'),'utf8'))
const roots=(app.subPackages||app.subpackages||[]).map(item=>item.root.replace(/\/+$/,'')+'/')
assert.equal(new Set(roots).size,roots.length,'Subpackage roots must be unique')
assert.ok(roots.every(name=>name!=='/'&&!name.startsWith('/')&&!name.split('/').includes('..')),'Subpackage roots must be relative')
const packages=[{name:'main',upload_bytes:included.filter(f=>!roots.some(name=>f.name.startsWith(name))).reduce((sum,f)=>sum+f.bytes,0)},
 ...roots.map(name=>({name,upload_bytes:included.filter(f=>f.name.startsWith(name)).reduce((sum,f)=>sum+f.bytes,0)}))]
for(const entry of packages)assert.ok(entry.upload_bytes<=budget,`${entry.name} uses ${entry.upload_bytes} bytes; package budget is ${budget}`)
assert.ok(bytes<=20*1024*1024,'Total mini-program upload exceeds 20MB')
let wechat=null
if(extra.length){
 const info=JSON.parse(readFileSync(resolve(extra[1]),'utf8'))
 const compiled=info.size?.packages
 assert.ok(Array.isArray(compiled)&&compiled.length>0,'WeChat preview information must contain package sizes')
 const expected=new Set(['main',...roots.map(name=>'/'+name)])
 const actual=compiled.filter(entry=>entry.name!=='TOTAL')
 assert.equal(new Set(actual.map(entry=>entry.name)).size,actual.length,'WeChat preview package names must be unique')
 assert.deepEqual(new Set(actual.map(entry=>entry.name)),expected,'WeChat preview packages do not match app.json')
 for(const entry of actual){
  assert.ok(Number.isSafeInteger(entry.size)&&entry.size>=0,`Invalid WeChat size for ${entry.name}`)
  assert.ok(entry.size<=2*1024*1024,`WeChat compiled ${entry.name} uses ${entry.size} bytes; limit is ${2*1024*1024}`)
 }
 assert.ok(Number.isSafeInteger(info.size.total)&&info.size.total>=0&&info.size.total<=20*1024*1024,'WeChat compiled total exceeds 20MB or is invalid')
 assert.equal(info.size.total,actual.reduce((sum,entry)=>sum+entry.size,0),'WeChat compiled total does not match package sizes')
 wechat={total_bytes:info.size.total,packages:actual}
}
console.log(JSON.stringify({upload_bytes:bytes,budget_bytes:budget,limit_bytes:2*1024*1024,
 verification:wechat?'wechat-compiled':'source-estimate-only',wechat,
 packages,included_files:included.length,excluded:files.filter(f=>excluded.has(f.name)).map(({name,bytes})=>({name,bytes}))}))
