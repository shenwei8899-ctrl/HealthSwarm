import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import { createCommerceClient } from '../src/services/commerce-client.js'

const backend = process.env.HEALTHFLOW_LINK_ROOT
if (!backend) throw new Error('Set HEALTHFLOW_LINK_ROOT to the isolated Healthflow2 checkout')
const fixture = JSON.parse(readFileSync(resolve(backend,'runtime/local-link/credentials.json'),'utf8'))
const base = 'http://127.0.0.1:18081'
function client() {
  const values = new Map(), calls = []
  const c = createCommerceClient({baseUrl:base,authMode:'member',
    parent:{read:()=>null,scope:()=> 'link-test',storageScope:()=> 'link-test'},
    storage:{get:k=>values.get(k),set:(k,v)=>values.set(k,v)},randomKey:()=>crypto.randomUUID(),
    transport:async options=>{
      calls.push(options)
      const response = await fetch(options.url,{method:options.method,headers:options.header,body:options.data ? JSON.stringify(options.data) : undefined,signal:AbortSignal.timeout(15000)})
      return {statusCode:response.status,data:await response.json()}
    },
  })
  return {c,calls}
}
function db(sql) {
  const result=spawnSync('docker',['exec','healthflow-link-db-20261013','psql','-U','healthflow_link','-d','healthflow_link_test','-tAc',sql],{encoding:'utf8',windowsHide:true})
  assert.equal(result.status,0,result.stderr)
  return result.stdout.trim()
}

test('frontend commerce adapter reaches real PHP HTTP and PostgreSQL', async () => {
  const {c:a,calls} = client(), {c:b} = client()
  await assert.rejects(a.login({account:fixture.members[0].account,password:'wrong'}),e=>Number(e.code)===40100)
  await a.login(fixture.members[0]); await b.login(fixture.members[1])
  assert.notEqual(a.session().userId,b.session().userId)
  const baseline = Number(db(`SELECT reserved_stock FROM fa_shop_goods_sku WHERE id=${fixture.sku_id}`))
  const products=await a.products(); assert(products.items.some(p=>Number(p.sku_id)===Number(fixture.sku_id)))
  const tree=await a.areas(); assert(tree.length>3000)
  const unauthenticatedUpload=await fetch(base+'/api/v1/commerce/media/evidence',{method:'POST'})
  assert.equal(unauthenticatedUpload.status,401)
  const invalidImage = new FormData(); invalidImage.append('file',new Blob(['not an image'],{type:'image/png'}),'fake.png')
  const invalidUpload=await fetch(base+'/api/v1/commerce/media/evidence',{method:'POST',headers:{token:a.session().token},body:invalidImage})
  assert.equal(invalidUpload.status,400)
  const validImage = new FormData()
  validImage.append('file',new Blob([Buffer.concat([Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a6b8AAAAASUVORK5CYII=','base64'), Buffer.from(crypto.randomUUID())])],{type:'image/png'}),'test.png')
  const validUpload=await fetch(base+'/api/v1/commerce/media/evidence',{method:'POST',headers:{token:a.session().token},body:validImage})
  const uploaded = await validUpload.json(); assert.equal(uploaded.code,0,JSON.stringify(uploaded)); assert.equal((await fetch(uploaded.data.url)).status,200)
  for (const line of (await a.cart()).items) await a.remove(line)
  await a.add(fixture.sku_id,2)
  const cart=await a.cart(); assert.equal(cart.items[0].quantity,2)
  assert.equal((await b.cart()).items.length,0)
  const address=await a.saveAddress({name:'HTTP TEST',phone:'13800000000',region:'上海市 徐汇区',detail:'SYNTHETIC ADDRESS'})
  await assert.rejects(b.selectAddress(address.id),e=>Number(e.code)===40407)
  const quote=await a.quote(cart.items,address.id)
  assert.equal(quote.payable_amount_cent,2468)
  const order=await a.createOrder(quote.checkout_token)
  const original=calls.findLast(o=>o.url.endsWith('/orders')&&o.method==='POST')
  const replay=await a.request('/orders',{method:'POST',data:original.data,key:original.header['Idempotency-Key']})
  assert.equal(replay.order_sn,order.order_sn)
  const detail=await a.order(order.order_sn)
  assert.equal(detail.totalCents,2468); assert(detail.allowedActions.includes('cancel'))
  assert.equal(detail.address.detail,'SYNTHETIC ADDRESS')
  assert.equal(db(`SELECT count(*) FROM fa_shop_order WHERE order_sn='${order.order_sn}'`),'1')
  assert.equal(db(`SELECT reserved_stock FROM fa_shop_goods_sku WHERE id=${fixture.sku_id}`),String(baseline + 2))
  for (const op of [()=>b.order(order.order_sn),()=>b.afterSales(order.order_sn),()=>b.logistics(order.order_sn)])
    await assert.rejects(op,e=>Number(e.code)===40409)
  await assert.rejects(a.action(order.order_sn,'receipt'),e=>Number(e.code)===40910)
  const item=detail.items[0].id
  await assert.rejects(a.submitAfterSale({order_sn:order.order_sn,type:'refund_only',reason_code:'quality_issue',items:[{order_item_id:item,quantity:1}]}),e=>Number(e.code)===40910)
  await a.action(order.order_sn,'cancel')
  assert.equal(db(`SELECT reserved_stock FROM fa_shop_goods_sku WHERE id=${fixture.sku_id}`),String(baseline))
  assert.equal((await a.order(order.order_sn)).status,'cancelled')

  // A clearly synthetic paid fixture verifies the application contract, never a payment gateway.
  await a.add(fixture.sku_id,1)
  const quote2=await a.quote((await a.cart()).items,address.id)
  const second=await a.createOrder(quote2.checkout_token)
  db(`UPDATE fa_shop_order SET paystate=1,shippingstate=1 WHERE order_sn='${second.order_sn}'; UPDATE fa_shop_order_ext SET payment_status='paid',business_status='paid' WHERE order_sn='${second.order_sn}'; UPDATE fa_shop_goods_sku SET reserved_stock=reserved_stock-1,stocks=stocks-1 WHERE id=${fixture.sku_id}; UPDATE fa_shop_inventory_reservation SET status='confirmed' WHERE source_ref=(SELECT checkout_token_hash FROM fa_shop_order_ext WHERE order_sn='${second.order_sn}') AND status='active'`)
  const paid=await a.order(second.order_sn)
  const after=await a.submitAfterSale({order_sn:second.order_sn,type:'refund_only',reason_code:'quality_issue',description:'SYNTHETIC TEST ONLY',evidence_urls:[],items:[{order_item_id:paid.items[0].id,quantity:1}]})
  assert(after.items[0].aftersale_sn)
  assert((await a.afterSales(second.order_sn)).some(r=>r.aftersale_sn===after.items[0].aftersale_sn))
  assert.equal(db(`SELECT count(*) FROM fa_shop_order_aftersales WHERE order_id=(SELECT id FROM fa_shop_order WHERE order_sn='${second.order_sn}') AND status=1`),'1')
  await assert.rejects(b.request('/aftersales/'+after.items[0].aftersale_sn),e=>Number(e.code)===40413)
  await a.mutate('/aftersales/'+after.items[0].aftersale_sn+'/cancel')
  await a.action(second.order_sn,'receipt')
  assert.equal((await a.order(second.order_sn)).status,'delivered')
  const token=a.session().token; await a.logout()
  const revoked=await fetch(base+'/api/v1/commerce/session',{headers:{token}})
  assert.equal(revoked.status,401)
  console.log('Verified durable order replay, inventory, snapshots, ownership, cancellation, synthetic paid aftersales and token revocation.')
})

