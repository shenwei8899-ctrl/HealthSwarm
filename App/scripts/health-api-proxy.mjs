// 本机微信开发者工具入口；只转发到明确配置的真实服务，不生成任何业务数据。
import http from 'node:http'
import https from 'node:https'

const target = new URL(process.env.HEALTH_PROXY_TARGET || 'http://8.136.134.29')
if (!['http:', 'https:'].includes(target.protocol) || target.username || target.password) throw new Error('健康服务地址无效')
const port = Number(process.env.HEALTH_PROXY_PORT || 15050)
const server = http.createServer((incoming, outgoing) => {
  const origin = incoming.headers.origin
  if (origin && !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) { outgoing.writeHead(403); outgoing.end(); return }
  const cors = origin ? {'Access-Control-Allow-Origin':origin,'Vary':'Origin','Access-Control-Allow-Headers':'Authorization, Content-Type, Idempotency-Key, If-Match','Access-Control-Allow-Methods':'GET, POST, PUT, PATCH, DELETE, OPTIONS'} : {}
  if (incoming.method === 'OPTIONS') { outgoing.writeHead(204,cors); outgoing.end(); return }
  if (!incoming.url?.startsWith('/api/') || incoming.url.startsWith('//')) { outgoing.writeHead(404,cors);outgoing.end();return }
  const path = incoming.url.startsWith('/api/v1/commerce/') ? '/commerce-api' + incoming.url : incoming.url
  const headers = {...incoming.headers,host:target.host}
  delete headers.origin
  const remote = (target.protocol === 'https:' ? https : http).request(new URL(path,target),{method:incoming.method,headers,timeout:30000}, response => {
    outgoing.writeHead(response.statusCode,{...response.headers,...cors,'Cache-Control':'no-store'})
    response.pipe(outgoing)
  })
  remote.on('timeout',()=>remote.destroy(new Error('upstream timeout')))
  remote.on('error',()=>{if(!outgoing.headersSent)outgoing.writeHead(502,{'Content-Type':'application/json',...cors});outgoing.end(JSON.stringify({message:'真实后端暂时无法连接，请稍后重试。',retryable:true}))})
  incoming.on('aborted',()=>remote.destroy())
  incoming.pipe(remote)
})
server.listen(port,'127.0.0.1',()=>process.stdout.write(`Health API proxy: http://127.0.0.1:${port} -> ${target.origin}\n`))
