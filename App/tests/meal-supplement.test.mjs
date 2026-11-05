import test from 'node:test'
import assert from 'node:assert/strict'
import {supplementCandidates,appendMealCandidates,preserveMealEvidence,createMealSupplementSaver} from '../src/services/meal-supplement.js'

const fish={item_id:'fish',name:'清蒸鱼',grams:150,portion_confirmed:true,photo_estimate:{draft_id:'original'}}
test('分次添加保留原份量与来源，待核对内容不进入原数组',()=>{
 const original=[structuredClone(fish)],rows=supplementCandidates(original,[{item_id:'rice',name:'米饭',grams:180}])
 assert.equal(original.length,1);rows[0].amount='120'
 const result=appendMealCandidates(original,rows)
 assert.deepEqual(result[0],fish);assert.equal(result[1].grams,120);assert.equal(original.length,1)
})
test('重复食物需要确认，同一份不添加，另吃一份保留独立来源',()=>{
 const rows=supplementCandidates([fish],[{...fish,item_id:'another',photo_estimate:{draft_id:'second'}}])
 assert.throws(()=>appendMealCandidates([fish],rows),/重复食物/)
 rows[0].choice='same';assert.equal(appendMealCandidates([fish],rows).length,1)
 rows[0].choice='extra';assert.equal(appendMealCandidates([fish],rows)[1].photo_estimate.draft_id,'second')
 assert.throws(()=>appendMealCandidates([fish],supplementCandidates([fish],[{...fish}]).map(r=>({...r,choice:'extra'}))),/已经加入/)
})
test('缺失份量不变成零，多批食物不受三张单次照片限制',()=>{
 const rows=supplementCandidates([fish],Array.from({length:4},(_,i)=>({item_id:`id-${i}`,name:`食物${i}`})))
 const result=appendMealCandidates([fish],rows)
 assert.equal(result.length,5);assert.equal(result[1].grams,null);assert.equal(result[1].portion_confirmed,false)
 rows[0].amount='-1';assert.throws(()=>appendMealCandidates([fish],rows),/有效/)
})
test('同名菜按项目ID保留原图证据，新增候选不冒用原图坐标',()=>{
 const result=preserveMealEvidence({items:[fish,{...fish,item_id:'second'}]}, {photos:[{upload_id:'a'}],items:[{...fish,locations:[{image_index:0}]}]})
 assert.equal(result.items[0].locations.length,1);assert.deepEqual(result.items[1].locations,[]);assert.equal(result.photos[0].upload_id,'a')
})
test('保存后补充只更正原记录，网络不确定后保持原幂等请求',async()=>{
 const cache=new Map(),calls=[];let lost=true
 const row={memberId:'member',record:{id:'record',source_version:2}},storage={getStorageSync:k=>cache.get(k),setStorageSync:(k,v)=>cache.set(k,structuredClone(v))}
 const saver=createMealSupplementSaver({storage,revision:()=>1,newId:()=> 'stable',send:async request=>{
   calls.push(request)
   if(request.method==='PATCH'){if(lost){lost=false;throw Object.assign(Error('lost'),{code:'NETWORK_ERROR'})}return {data:{}}}
   return {data:{records:[{id:'record',source_version:3,snapshot:{meal:{items:[fish]}}}]}}
 }})
 await assert.rejects(saver.save(row,{items:[fish]},false),/lost/)
 const saved=await saver.save(row,{items:[]},true)
 assert.equal(saved.record.id,'record');assert.equal(saved.record.source_version,3)
 assert.deepEqual(calls[0],calls[1]);assert.equal(saver.read(),null)
 assert(calls.every(c=>c.method==='PATCH'||!c.method))
})

test('原有被移除食物保留排除标记，不能因补充而重新计入',()=>{
 const result=preserveMealEvidence({items:[{...fish,item_id:'new'}]}, {photos:[],items:[fish]})
 assert.equal(result.items[0].excluded,true);assert.equal(result.items[1].excluded,false)
})
test('明确版本冲突释放原请求，允许重新读取后补充',async()=>{
 const cache=new Map(),storage={getStorageSync:k=>cache.get(k),setStorageSync:(k,v)=>cache.set(k,v)}
 const saver=createMealSupplementSaver({storage,revision:()=>1,newId:()=> 'conflict',send:async()=>{throw Object.assign(Error('changed'),{code:409})}})
 await assert.rejects(saver.save({memberId:'member',record:{id:'record',source_version:2}},{items:[fish]},false),/changed/)
 assert.equal(saver.read(),null)
})
test('离开或切换账号后的保存回执不能读取或覆盖新账号状态',async()=>{
 for(const leave of [false,true]){
  const cache=new Map(),calls=[];let revision=1,finish
  const storage={getStorageSync:k=>cache.get(revision+':'+k),setStorageSync:(k,v)=>cache.set(revision+':'+k,v)}
  const saver=createMealSupplementSaver({storage,revision:()=>revision,newId:()=> 'pending',send:r=>{calls.push(r);return new Promise(resolve=>finish=resolve)}})
  const saving=saver.save({memberId:'member',record:{id:'record',source_version:2}},{items:[fish]},false)
  if(leave)saver.hide();else revision++
  finish({data:{}});assert.equal(await saving,null);assert.equal(calls.length,1)
  assert(cache.get('1:meal-supplement-pending'));assert.equal(cache.has('2:meal-supplement-pending'),false)
 }
})
