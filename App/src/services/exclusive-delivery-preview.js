// 只展示服务端已返回的使用日建议；不生成预约、运费或未经核对的分包数量。
export function exclusiveDeliveryPreview(suggestions, products, picked, firstMealDate, time) {
  const stamp = Date.parse(firstMealDate+'T00:00:00Z')
  if (!Number.isFinite(stamp) || new Date(stamp).toISOString().slice(0,10) !== firstMealDate ||
      suggestions?.status !== 'suggested' || !Array.isArray(suggestions.batches)) return []
  const selected = new Set(picked.map(String))
  const catalog = new Map(products.filter(p => selected.has(String(p.id))).map(p => [String(p.id),p]))
  return suggestions.batches.filter(batch => Number.isInteger(batch.day_no) && batch.day_no>=1 && batch.day_no<=7)
    .slice().sort((a,b)=>a.day_no-b.day_no).map(batch=>({
      menu_day_start:batch.day_no,
      delivery_date:new Date(stamp+(batch.day_no-2)*86400000).toISOString().slice(0,10),
      slot_name:time,
      items:(batch.items||[]).flatMap(item=>{
        const product=catalog.get(String(item.product?.sku_id))
        const days=[...new Set((item.use_days||[]).filter(day=>Number.isInteger(day)&&day>=1&&day<=7))].sort((a,b)=>a-b)
        return product&&days.length ? [{sku_id:String(product.id),food:product.name,
          snapshot:{product_name:product.name,sku_name:product.packLabel,image_url:product.imageUrl||''},use_days:days,
          weekly:batch.day_no===1&&item.schedule_basis==='storage_rule'&&item.storage_max_days>=7}] : []
      }),
    })).filter(batch=>batch.items.length).map((batch,index)=>({...batch,batch_no:index+1,
      contains_weekly_staples:batch.items.some(item=>item.weekly)}))
}

export const deliveryBatchKey = batch => Number.isInteger(batch.menu_day_start) ? 'day-'+batch.menu_day_start : 'date-'+batch.delivery_date

export function deliveryBatchItems(batch, products) {
  const catalog=new Map(products.map(product=>[String(product.id),product]))
  return (batch?.items||[]).map((item,index)=>{
    const product=catalog.get(String(item.sku_id))
    const days=[...new Set((item.use_days||[]).filter(day=>Number.isInteger(day)&&day>=1&&day<=7))].sort((a,b)=>a-b)
    return {key:String(item.sku_id)+'-'+index,name:item.snapshot?.product_name||product?.name||item.food||'食材',
      spec:item.snapshot?.sku_name||product?.packLabel||'原包装',image:item.snapshot?.image_url||product?.imageUrl||'',
      uses:days.length?'用于第'+days.join('、')+'天':'使用日待核对',
      quantity:Number.isSafeInteger(item.quantity)&&item.quantity>0?item.quantity:null}
  })
}
