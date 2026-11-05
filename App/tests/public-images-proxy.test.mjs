import test from 'node:test'
import assert from 'node:assert/strict'
import http from 'node:http'
import {spawn} from 'node:child_process'
import {once} from 'node:events'
import {fileURLToPath} from 'node:url'

test('local proxy serves exact public covers without forwarding account credentials or private paths',async()=>{
 const calls=[]
 const upstream=http.createServer((req,res)=>{calls.push({path:req.url,method:req.method,authorization:req.headers.authorization,cookie:req.headers.cookie});res.writeHead(200,{'Content-Type':'image/jpeg'});res.end('synthetic proxy transport')})
 upstream.listen(0,'127.0.0.1');await once(upstream,'listening')
 const child=spawn(process.execPath,[fileURLToPath(new URL('../scripts/health-api-proxy.mjs',import.meta.url))],{env:{...process.env,HEALTH_PROXY_PORT:'0',HEALTH_PROXY_TARGET:'http://127.0.0.1:'+upstream.address().port},stdio:['ignore','pipe','pipe'],windowsHide:true})
 try{
  const base=await new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>reject(new Error('Proxy did not start')),10000)
   child.once('error',e=>{clearTimeout(timer);reject(e)})
   child.once('exit',code=>{clearTimeout(timer);reject(new Error('Proxy exited '+code))})
   child.stdout.on('data',chunk=>{const match=String(chunk).match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0])}})
  })
  const cover='/minio/public/recipe-covers/nhlbi/'+'a'.repeat(64)+'.jpg'
  const headers={Authorization:'Bearer synthetic-account',Cookie:'synthetic=private',Origin:'http://localhost:5173'}
  assert.equal((await fetch(base+cover,{headers})).status,200)
  assert.deepEqual(calls[0],{path:cover,method:'GET',authorization:undefined,cookie:undefined})
  assert.equal((await fetch(base+cover,{method:'HEAD'})).status,200)
  const count=calls.length
  for(const [method,path] of [['POST',cover],['GET','/minio/health-private/anything'],['GET','/minio/public/recipe-covers/nhlbi/not-a-hash.jpg'],['GET','/minio/public/recipe-covers/nhlbi/%2e%2e/private']]){
   assert.equal((await fetch(base+path,{method})).status,404)
  }
  assert.equal(calls.length,count)
  assert.equal((await fetch(base+'/api/synthetic',{headers})).status,200)
  assert.equal(calls.at(-1).authorization,headers.Authorization)
 }finally{child.kill();await new Promise(resolve=>upstream.close(resolve))}
})
