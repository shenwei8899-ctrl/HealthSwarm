import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {reactive,ref,nextTick,compile,createSSRApp} from 'vue'
import {renderToString} from 'vue/server-renderer'
import {createDishSwap,dishSwapState,watchDishSwap} from '../src/services/dish-swap.js'

const day='2026-11-18',dish={dish_key:'dish-1',name:'合成炒饭'}
const item={meal_type:'lunch',source:{kind:'reference',id:'source-1'},meal:{dishes:[dish]}}
const plan={date:day,status:'ready',version:3,meals:[item]}
const settle=async()=>{await nextTick();await nextTick()}
function harness(){
 let owner='A',date=day,reads=0,deny=false,resolve
 const state=reactive(dishSwapState()),value=ref(plan),enabled=ref(true)
 const client=createDishSwap({state,context:()=>owner,day:()=>date,family:()=> 'family',send:async()=>{
  reads++;if(deny)throw Error('合成网络错误')
  const reply={data:{date:day,version:value.value.version,meals:[{meal_type:'lunch',dishes:[{dish_key:'dish-1',candidates:[{candidate_id:'c1',dish:{name:'合成替换菜'}}]}]}]}}
  if(resolve)await new Promise(r=>{resolve=r});return reply
 }})
 const stop=watchDishSwap({client,plan:()=>value.value,enabled:()=>enabled.value})
 return {state,value,enabled,client,stop,reads:()=>reads,deny:v=>{deny=v},owner:v=>{owner=v},date:v=>{date=v}}
}
test('same-version return reloads candidates across repeated detail navigation',async()=>{
 const h=harness();try{
  await settle();assert.equal(h.state.entries.length,1)
  for(let i=0;i<3;i++){
   h.enabled.value=false;await settle();assert.equal(h.state.entries.length,0)
   h.value.value=structuredClone(plan);h.enabled.value=true;await settle()
   assert.equal(h.client.candidates(item,dish,h.value.value).length,1)
  }
  assert.equal(h.reads(),4)
 }finally{h.stop()}
})
test('same-version reload after verification and updated plan both refresh candidates',async()=>{
 const h=harness();try{
  await settle();h.value.value=structuredClone(plan);await settle();assert.equal(h.reads(),2)
  h.value.value={...plan,version:4};await settle()
  assert.equal(h.state.version,4);assert.equal(h.client.candidates(item,dish,plan).length,0)
 }finally{h.stop()}
})
test('read errors can retry; account changes and midnight invalidate old candidates',async()=>{
 const h=harness();try{
  await settle();h.deny(true);h.enabled.value=false;await settle();h.enabled.value=true;await settle()
  assert.equal(h.state.error,'');assert.equal(h.state.entries.length,1)
  h.deny(false);await h.client.load(h.value.value);assert.equal(h.state.entries.length,1)
  h.owner('B');assert.equal(h.client.candidates(item,dish,plan).length,0)
  h.owner('A');h.date('2026-11-19');assert.equal(h.client.candidates(item,dish,plan).length,0)
 }finally{h.stop()}
})
test('grid card reacts to candidate data and emits swap only from its own button',async()=>{
 const text=readFileSync(new URL('../src/components/DailyMealPlanCard.vue',import.meta.url),'utf8')
 const props=reactive({plan,dishGrid:true,workspace:false,compact:false,busy:false,swapBusy:false,interactive:true,swapEntries:[],swapVersion:3,swapDate:day})
 const events=[]
 const script=text.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const {computed}=await import('vue')
 const panel=new Function('computed','defineProps','defineEmits','dishKey','localDate','allTypes',script+';return {swapOptions,visibleTypes,names,openDish,openDetail}')(computed,()=>props,()=> (...args)=>events.push(args),d=>d.dish_key,()=>day,['lunch'])
 const render=compile(text.match(/<template>([\s\S]*?)<\/template>\s*<style/)[1])
 const context=()=>({...props,...panel,visibleTypes:panel.visibleTypes.value,dishTitle:d=>d.name,dishKey:d=>d.dish_key,recipeCover:()=>null,localDate:()=>day,$emit:(...args)=>events.push(args)})
 const html=()=>renderToString(createSSRApp({render,setup:context}))
 assert.doesNotMatch(await html(),/换一换/)
 props.swapEntries=[{mealType:'lunch',dishKey:'dish-1',candidates:[{candidate_id:'c1'}]}]
 assert.match(await html(),/换一换/)
 const node=render(context(),[])
 function find(n){if(n?.type==='button'&&n.props?.['aria-label']==='替换合成炒饭')return n;for(const child of Array.isArray(n?.children)?n.children:[]){const found=find(child);if(found)return found}}
 const button=find(node);assert.ok(button);button.props.onClick();assert.equal(events[0][0],'swap')
 props.swapVersion=2;assert.doesNotMatch(await html(),/换一换/)
 props.swapVersion=3;props.interactive=false;assert.doesNotMatch(await html(),/换一换/)
 const detail=readFileSync(new URL('../src/components/MealDetailSheet.vue',import.meta.url),'utf8')
 assert.doesNotMatch(detail,/换一换|DishSwapSheet|createDishSwap/)
})

test('leaving the watched page cancels scheduled recovery',async()=>{
 let pending=null,reads=0
 const state=reactive(dishSwapState()),enabled=ref(true)
 const client=createDishSwap({state,context:()=> 'A',day:()=>day,family:()=> 'family',
  schedule:fn=>(pending=fn,1),cancel:()=>{pending=null},send:async()=>{reads++;throw Error('网络错误')}})
 const stop=watchDishSwap({client,plan:()=>plan,enabled:()=>enabled.value})
 await settle();assert.equal(state.error,'');assert.equal(typeof pending,'function')
 enabled.value=false;await settle();assert.equal(pending,null)
 enabled.value=true;await settle();assert.equal(typeof pending,'function')
 stop();assert.equal(pending,null);assert.equal(reads,2)
})
