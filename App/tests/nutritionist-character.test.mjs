import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {computed,ref,reactive,watch,toRefs,compile,createSSRApp} from 'vue'
import {renderToString} from 'vue/server-renderer'

const source=readFileSync(new URL('../src/components/NutritionistCharacter.vue',import.meta.url),'utf8')
const script=source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
const template=source.match(/<template>([\s\S]*?)<\/template>/)[1]
const render=compile(template,{isCustomElement:tag=>['view','image','text'].includes(tag)})

const layers=['head','blink','body','arm']
const rigAsset=/nutrition-boy-v3-(?:head|blink|body|arm)\.webp/

function character(values={},{media,document}={}) {
 const props=reactive({size:128,unit:'px',variant:'hero',state:'idle',decorative:false,animated:true,...values})
 const hooks={mounted:[],unmounted:[],show:[],hide:[]}
 const deps={computed,ref,watch,defineProps:()=>props,globalThis:{...(media?{matchMedia:()=>media}:{}),document},
  onMounted:fn=>hooks.mounted.push(fn),onUnmounted:fn=>hooks.unmounted.push(fn),onShow:fn=>hooks.show.push(fn),onHide:fn=>hooks.hide.push(fn)}
 const state=new Function('deps',`const {${Object.keys(deps)}}=deps;${script};return {stateLabels,visualState,frameStyle,showSprite,posterCovered,posterFailed,spriteFailed,spriteReady,spriteLoaded,spriteError}`)(deps)
 return {props,state,show:()=>hooks.show.forEach(fn=>fn()),hide:()=>hooks.hide.forEach(fn=>fn()),mount:()=>hooks.mounted.forEach(fn=>fn()),dispose:()=>hooks.unmounted.forEach(fn=>fn()),
  html:()=>renderToString(createSSRApp({render,setup:()=>({...toRefs(props),...state})}))}
}

function decode(c,names=layers){for(const name of names)c.state.spriteLoaded(name)}

test('a bundled PNG stays visible until all four layers decode, with explicit native dimensions',async(t)=>{
 const c=character(),html=await c.html()
 t.after(()=>c.dispose())
 assert.match(html,/nutrition-boy-v3-poster\.png/)
 assert.doesNotMatch(html,/poster-covered/)
 assert.deepEqual(c.state.frameStyle.value,{width:'128px',height:'128px'})
 for(const name of layers)assert.match(html,new RegExp(`nutrition-boy-v3-${name}\\.webp`))
 decode(c,['arm','head','blink','head','unknown'])
 assert.equal(c.state.spriteReady.value,false)
 assert.equal(c.state.posterCovered.value,false)
 assert.doesNotMatch(await c.html(),/poster-covered/)
 c.state.spriteLoaded('body')
 assert.equal(c.state.spriteReady.value,true)
 assert.equal(c.state.posterCovered.value,true)
 assert.match(await c.html(),/poster-covered/)
})

test('a failure in any layer keeps the complete static boy and ignores late loads',async(t)=>{
 for(const failed of layers)await t.test(failed,async(t)=>{
  const c=character();t.after(()=>c.dispose())
  decode(c,layers.filter(name=>name!==failed));c.state.spriteError();decode(c)
  const html=await c.html()
  assert.match(html,/nutrition-boy-v3-poster\.png/)
  assert.doesNotMatch(html,rigAsset)
  assert.doesNotMatch(html,/poster-covered/)
  assert.equal(c.state.spriteReady.value,false)
  assert.equal(c.state.visualState.value,'idle')
 })
 const c=character();t.after(()=>c.dispose());decode(c)
 assert.equal(c.state.posterCovered.value,true)
 c.state.spriteError()
 assert.equal(c.state.posterCovered.value,false)
 assert.doesNotMatch(await c.html(),rigAsset)
})

test('native page hide unloads the rig and showing it requires all layers to decode again',async(t)=>{
 const c=character();t.after(()=>c.dispose());c.mount();decode(c);c.hide();decode(c)
 assert.equal(c.state.spriteReady.value,false)
 assert.doesNotMatch(await c.html(),rigAsset)
 c.show();assert.equal(c.state.posterCovered.value,false)
 assert.match(await c.html(),/nutrition-boy-v3-poster\.png/)
 decode(c,layers.slice(0,3));assert.equal(c.state.posterCovered.value,false)
 decode(c);assert.equal(c.state.posterCovered.value,true)
})

test('H5 visibility and native lifecycle both gate rendering and unsubscribe on unmount',async()=>{
 let changed,removed=false
 const document={visibilityState:'visible',addEventListener:(name,fn)=>{assert.equal(name,'visibilitychange');changed=fn},removeEventListener:(name,fn)=>{removed=name==='visibilitychange'&&fn===changed}}
 const c=character({},{document});c.mount();decode(c)
 assert.equal(c.state.posterCovered.value,true)
 document.visibilityState='hidden';changed();decode(c)
 assert.equal(c.state.spriteReady.value,false)
 assert.doesNotMatch(await c.html(),rigAsset)
 c.show();assert.equal(c.state.showSprite.value,false)
 c.hide();document.visibilityState='visible';changed()
 assert.equal(c.state.showSprite.value,false)
 c.show();assert.equal(c.state.posterCovered.value,false)
 decode(c);assert.equal(c.state.posterCovered.value,true)
 c.dispose();assert.equal(removed,true)
 assert.doesNotMatch(await c.html(),rigAsset)
})

test('a page initially hidden in H5 does not load layers before becoming visible',async(t)=>{
 let changed
 const document={visibilityState:'hidden',addEventListener:(_name,fn)=>{changed=fn},removeEventListener:()=>{}}
 const c=character({},{document});t.after(()=>c.dispose());c.mount();decode(c)
 assert.doesNotMatch(await c.html(),rigAsset)
 assert.equal(c.state.spriteReady.value,false)
 document.visibilityState='visible';changed()
 assert.match(await c.html(),rigAsset)
 assert.equal(c.state.posterCovered.value,false)
})

test('reduced-motion changes keep a static boy and clean up the preference subscription',async()=>{
 let changed,removed=false
 const media={matches:true,addEventListener:(name,fn)=>{assert.equal(name,'change');changed=fn},removeEventListener:(name,fn)=>{removed=name==='change'&&fn===changed}}
 const c=character({},{media});c.mount();decode(c)
 assert.doesNotMatch(await c.html(),rigAsset)
 assert.equal(c.state.spriteReady.value,false)
 changed({matches:false});decode(c);assert.equal(c.state.posterCovered.value,true)
 changed({matches:true});assert.equal(c.state.posterCovered.value,false)
 assert.doesNotMatch(await c.html(),rigAsset)
 changed({matches:false});assert.equal(c.state.spriteReady.value,false)
 assert.match(await c.html(),rigAsset)
 c.dispose();assert.equal(removed,true)
 assert.equal(c.state.showSprite.value,false)
})

test('avatars and explicitly static heroes never load rig layers',async()=>{
 const avatar=character({variant:'avatar',size:48,unit:'rpx'}),still=character({animated:false})
 for(const c of [avatar,still]){c.mount();decode(c);assert.match(await c.html(),/nutrition-boy-v3-poster\.png/);assert.doesNotMatch(await c.html(),rigAsset);assert.equal(c.state.spriteReady.value,false);c.dispose()}
 assert.deepEqual(avatar.state.frameStyle.value,{width:'48rpx',height:'48rpx'})
})

test('even a poster decode failure retains a visible fallback and truthful activity label',async()=>{
 const c=character({state:'thinking'});c.state.posterFailed.value=true;c.state.spriteError()
 const html=await c.html();assert.match(html,/character-fallback/);assert.match(html,/正在认真思考/)
 assert.doesNotMatch(html,/status-check|poster-covered/)
 c.props.state='success';assert.match(await c.html(),/餐单准备好啦/)
 c.dispose()
})
