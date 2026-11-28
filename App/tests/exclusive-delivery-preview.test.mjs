import test from 'node:test'
import assert from 'node:assert/strict'
import {exclusiveDeliveryPreview} from '../src/services/exclusive-delivery-preview.js'

const products=[{id:'rice',name:'合成大米',packLabel:'500g/包',quantity:2},{id:'greens',name:'合成青菜',packLabel:'500g/包',quantity:1}]
const food=(id,days,weekly=false)=>({product:{sku_id:id,quantity:99},use_days:days,
  schedule_basis:weekly?'storage_rule':'daily',storage_max_days:weekly?7:null})
const source={status:'suggested',batches:[
  {day_no:7,items:[food('greens',[7])]},
  {day_no:1,items:[food('rice',[1,7],true),food('greens',[1])]},
  {day_no:4,items:[food('greens',[4,5])]},
]}

test('server usage suggestions are visible without an address, slot ID, quote or fees',()=>{
 const rows=exclusiveDeliveryPreview(source,products,['rice','greens'],'2026-12-01','11:00–12:00')
 assert.deepEqual(rows.map(row=>row.delivery_date),['2026-11-30','2026-12-03','2026-12-06'])
 assert.deepEqual(rows.map(row=>row.batch_no),[1,2,3])
 assert.ok(rows.every(row=>row.slot_name==='11:00–12:00'))
 assert.equal(rows[0].contains_weekly_staples,true)
 assert.ok(rows.flatMap(row=>row.items).every(item=>!('quantity' in item)))
 assert.ok(rows.every(row=>!('shipping_fee_cent' in row)))
})

test('deselecting a product filters all its deliveries and renumbers remaining trips',()=>{
 const rows=exclusiveDeliveryPreview(source,products,['rice'],'2026-12-01','10:00–11:00')
 assert.equal(rows.length,1);assert.deepEqual(rows[0].items.map(item=>item.sku_id),['rice'])
 assert.deepEqual(exclusiveDeliveryPreview(source,products,[],'2026-12-01','10:00–11:00'),[])
})

test('new dates and times shift the existing usage schedule across year boundaries',()=>{
 const rows=exclusiveDeliveryPreview(source,products,['greens'],'2027-01-01','12:00–13:00')
 assert.deepEqual(rows.map(row=>row.delivery_date),['2026-12-31','2027-01-03','2027-01-06'])
 assert.ok(rows.every(row=>row.slot_name==='12:00–13:00'))
 assert.ok(rows.every(row=>row.contains_weekly_staples===false))
})

test('missing or invalid inputs do not invent a delivery plan',()=>{
 for(const value of ['',undefined,'2026-02-30'])assert.deepEqual(exclusiveDeliveryPreview(source,products,['rice'],value,'10:00–11:00'),[])
 assert.deepEqual(exclusiveDeliveryPreview(null,products,['rice'],'2026-12-01','10:00–11:00'),[])
 const invalid={status:'suggested',batches:[{day_no:8,items:[food('rice',[7])]},{day_no:1,items:[food('unknown',[1]),food('rice',[])]}]}
 assert.deepEqual(exclusiveDeliveryPreview(invalid,products,['rice'],'2026-12-01','10:00–11:00'),[])
})
