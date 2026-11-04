import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {computed,ref,reactive,watch,toRefs,compile,createSSRApp} from 'vue'
import {renderToString} from 'vue/server-renderer'

const source=readFileSync(new URL('../src/components/NutritionistCharacter.vue',import.meta.url),'utf8')
const script=source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
const template=source.match(/<template>([\s\S]*?)<\/template>/)[1]
const render=compile(template,{isCustomElement:tag=>['view','image','text'].includes(tag)})

function character(values={},media) {
 const props=reactive({size:128,unit:'px',variant:'hero',state:'idle',decorative:false,animated:true,...values})
 const hooks={mounted:[],unmounted:[],show:[],hide:[]}
 const deps={computed,ref,watch,defineProps:()=>props,globalThis:media?{matchMedia:()=>media}:{},
  onMounted:fn=>hooks.mounted.push(fn),onUnmounted:fn=>hooks.unmounted.push(fn),onShow:fn=>hooks.show.push(fn),onHide:fn=>hooks.hide.push(fn)}
 const state=new Function('deps',`const {${Object.keys(deps)}}=deps;${script};return {stateLabels,visualState,frameStyle,spriteStyle,showSprite,posterCovered,posterFailed,spriteFailed,spriteReady,spriteLoaded,spriteError}`)(deps)
 return {props,state,show:()=>hooks.show.forEach(fn=>fn()),hide:()=>hooks.hide.forEach(fn=>fn()),mount:()=>hooks.mounted.forEach(fn=>fn()),dispose:()=>hooks.unmounted.forEach(fn=>fn()),
  html:()=>renderToString(createSSRApp({render,setup:()=>({...toRefs(props),...state})}))}
}

test('a bundled PNG is visible before the animation decodes, with explicit native dimensions',async()=>{
 const c=character(),html=await c.html()
 assert.match(html,/nutrition-boy-v2-poster\.png/)
 assert.doesNotMatch(html,/poster-covered/)
 assert.deepEqual(c.state.frameStyle.value,{width:'128px',height:'128px'})
 assert.deepEqual(c.state.spriteStyle.value,{width:'256px',height:'256px'})
 assert.equal(c.state.posterCovered.value,false)
 c.dispose()
})

test('a decoded animation replaces the poster, while a failed animation restores the complete static boy',async()=>{
 const c=character();c.state.spriteLoaded()
 assert.match(await c.html(),/poster-covered/)
 c.state.spriteError()
 const html=await c.html();assert.match(html,/nutrition-boy-v2-poster\.png/)
 assert.doesNotMatch(html,/nutrition-boy-v2-sprite\.webp|poster-covered/)
 assert.equal(c.state.visualState.value,'idle')
 c.dispose()
})

test('leaving the page unloads the animation and returning waits for a new image load',async()=>{
 const c=character();c.state.spriteLoaded();c.hide();c.state.spriteLoaded()
 assert.equal(c.state.spriteReady.value,false)
 assert.doesNotMatch(await c.html(),/nutrition-boy-v2-sprite\.webp/)
 c.show();assert.equal(c.state.posterCovered.value,false)
 assert.match(await c.html(),/nutrition-boy-v2-poster\.png/)
 c.state.spriteLoaded();assert.equal(c.state.posterCovered.value,true)
 c.dispose()
})

test('reduced-motion changes keep a static boy and clean up the preference subscription',async()=>{
 let changed,removed=false
 const media={matches:true,addEventListener:(name,fn)=>{assert.equal(name,'change');changed=fn},removeEventListener:(name,fn)=>{removed=name==='change'&&fn===changed}}
 const c=character({},media);c.mount()
 assert.doesNotMatch(await c.html(),/nutrition-boy-v2-sprite\.webp/)
 changed({matches:false});c.state.spriteLoaded();assert.equal(c.state.posterCovered.value,true)
 changed({matches:true});assert.equal(c.state.posterCovered.value,false)
 changed({matches:false});assert.equal(c.state.spriteReady.value,false)
 c.dispose();assert.equal(removed,true)
})

test('avatars and explicitly static heroes never load animation frames',async()=>{
 const avatar=character({variant:'avatar',size:48,unit:'rpx'}),still=character({animated:false})
 for(const c of [avatar,still]){assert.match(await c.html(),/nutrition-boy-v2-poster\.png/);assert.doesNotMatch(await c.html(),/nutrition-boy-v2-sprite\.webp/);c.dispose()}
 assert.deepEqual(avatar.state.frameStyle.value,{width:'48rpx',height:'48rpx'})
})

test('even a poster decode failure retains a visible fallback and truthful activity label',async()=>{
 const c=character({state:'thinking'});c.state.posterFailed.value=true;c.state.spriteError()
 const html=await c.html();assert.match(html,/character-fallback/);assert.match(html,/正在认真思考/)
 assert.doesNotMatch(html,/status-check|poster-covered/)
 c.props.state='success';assert.match(await c.html(),/餐单准备好啦/)
 c.dispose()
})
