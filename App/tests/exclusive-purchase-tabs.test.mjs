import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,computed,reactive,watch,effectScope,nextTick} from 'vue'
import {deliveryBatchKey,deliveryBatchItems} from '../src/services/exclusive-delivery-preview.js'
import {mealDateStart,PLAN_DELIVERY_TIMES} from '../src/services/meal-commerce-state.js'

const products=Array.from({length:4},(_,i)=>({id:String(i+1),name:'合成食材'+(i+1),packLabel:'500g/包',imageUrl:'/product-'+i+'.png'}))
const batch=(day,date,ids)=>({menu_day_start:day,delivery_date:date,items:ids.map(id=>({sku_id:String(id),use_days:[day],food:'旧名称'}))})
function mount(){
 const props=reactive({open:true,products:structuredClone(products),picked:['1','2','3','4'],quote:null,previewBatches:[batch(1,'2026-11-30',[1,2,3,4]),batch(4,'2026-12-03',[2])]})
 const emissions=[],scope=effectScope(),deps={ref,computed,watch,deliveryBatchKey,deliveryBatchItems,mealDateStart,PLAN_DELIVERY_TIMES,defineProps:()=>props,defineEmits:()=> (...args)=>emissions.push(args)}
 const source=readFileSync(new URL('../src/components/ExclusivePurchaseConfirmation.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const view=scope.run(()=>new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {activeBatchKey,activeBatch,activeItems,visibleItems,selectBatch,batchItemsOpen,isPreview}`)(deps))
 return {...view,props,emissions,dispose:()=>scope.stop()}
}

test('delivery tabs only change the viewed batch; updated dates preserve the selected usage day',async()=>{
 const f=mount();try{
  assert.equal(f.activeBatch.value.menu_day_start,1)
  f.selectBatch(f.props.previewBatches[1]);await nextTick()
  assert.equal(f.activeItems.value[0].name,'合成食材2');assert.deepEqual(f.emissions,[])
  f.props.previewBatches=[batch(1,'2026-12-02',[1]),batch(4,'2026-12-05',[2])];await nextTick()
  assert.equal(f.activeBatch.value.menu_day_start,4);assert.equal(f.activeBatch.value.delivery_date,'2026-12-05')
  f.props.previewBatches=[batch(1,'2026-12-02',[1])];await nextTick()
  assert.equal(f.activeBatch.value.menu_day_start,1)
  f.props.previewBatches=[];await nextTick();assert.equal(f.activeBatch.value,undefined);assert.deepEqual(f.visibleItems.value,[])
 }finally{f.dispose()}
})

test('a confirmed quote retains the selected tab and supplies authoritative quantities',async()=>{
 const f=mount();try{
  f.selectBatch(f.props.previewBatches[1]);await nextTick()
  f.props.quote={delivery_batches:[batch(1,'2026-11-30',[1]),{...batch(4,'2026-12-03',[2]),items:[{sku_id:'2',quantity:2,use_days:[4],snapshot:{product_name:'确认后的名称',sku_name:'1kg/包'}}]}]}
  await nextTick();assert.equal(f.activeBatch.value.menu_day_start,4);assert.equal(f.isPreview.value,false)
  assert.equal(f.activeItems.value[0].quantity,2);assert.equal(f.activeItems.value[0].name,'确认后的名称')
  assert.equal(f.activeItems.value[0].image,'/product-1.png')
 }finally{f.dispose()}
})

test('long ingredient lists start at three rows and changing tabs resets expansion',async()=>{
 const f=mount();try{
  assert.equal(f.activeItems.value.length,4);assert.equal(f.visibleItems.value.length,3)
  f.batchItemsOpen.value=true;assert.equal(f.visibleItems.value.length,4)
  f.selectBatch(f.props.previewBatches[1]);await nextTick()
  f.selectBatch(f.props.previewBatches[0]);await nextTick()
  assert.equal(f.visibleItems.value.length,3)
 }finally{f.dispose()}
})

test('item presentation uses real product images and preserves unknown quantities',()=>{
 const rows=deliveryBatchItems({items:[{sku_id:'1',use_days:[3,1,3],snapshot:{image_url:'/snapshot.png'}},{sku_id:'2',use_days:[]}]},products)
 assert.equal(rows[0].image,'/snapshot.png');assert.equal(rows[0].uses,'用于第1、3天');assert.equal(rows[0].quantity,null)
 assert.equal(rows[1].image,'/product-1.png');assert.equal(rows[1].uses,'使用日待核对')
 assert.equal(deliveryBatchKey(batch(4,'2026-12-03',[])),deliveryBatchKey(batch(4,'2027-01-03',[])))
})
