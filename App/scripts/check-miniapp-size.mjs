import {readFileSync,readdirSync,statSync} from 'node:fs'
import {resolve,join,relative} from 'node:path'
import assert from 'node:assert/strict'

const root=resolve(process.argv[2]||'dist/build/mp-weixin')
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
const budget=Math.floor(1.8*1024*1024)
assert.ok(bytes<=budget,`Mini-program upload files use ${bytes} bytes; budget is ${budget}`)
console.log(JSON.stringify({upload_bytes:bytes,budget_bytes:budget,limit_bytes:2*1024*1024,
 included_files:included.length,excluded:files.filter(f=>excluded.has(f.name)).map(({name,bytes})=>({name,bytes}))}))
