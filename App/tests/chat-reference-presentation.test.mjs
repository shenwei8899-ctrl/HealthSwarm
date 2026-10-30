import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,watch,nextTick,reactive} from 'vue'
import {chatPresentation} from '../src/services/chat-presentation.js'

test('saved onboarding content is shown inside chat without the generic welcome',()=>{
 const state=chatPresentation({route:{preparation:'saved'},hasSavedArrangement:true,preparedThreadId:'first',currentThreadId:'first'})
 assert.deepEqual(state,{initialResults:true,welcome:false})
 assert.equal(chatPresentation({route:{from:'onboarding'},hasSavedArrangement:true}).welcome,false)
})
test('a new empty conversation has welcome content even when today has a saved arrangement',()=>{
 assert.deepEqual(chatPresentation({hasSavedArrangement:true}),{initialResults:false,welcome:true})
 assert.deepEqual(chatPresentation({route:{preparation:'saved'},hasSavedArrangement:true,newConversation:true}),{initialResults:false,welcome:true})
})
test('restoring a different empty thread does not repeat the first onboarding analysis',()=>{
 assert.deepEqual(chatPresentation({route:{preparation:'saved'},hasSavedArrangement:true,preparedThreadId:'first',currentThreadId:'second'}),{initialResults:false,welcome:true})
})
test('welcome is visible during first initialization and hidden while restoring an existing thread',()=>{
 assert.equal(chatPresentation({hasMessages:true}).welcome,false)
 assert.equal(chatPresentation({loading:true}).welcome,true)
 assert.equal(chatPresentation({loading:true,currentThreadId:'existing'}).welcome,false)
 assert.equal(chatPresentation({route:{preparation:'saved'},hasMessages:true,hasSavedArrangement:true}).initialResults,true)
})
function layout(){
 const emitted=[],props=reactive({followBottom:true});let dispose=()=>{}
 const source=readFileSync(new URL('../src/components/NutritionistLayout.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const deps={getCurrentInstance:()=>({proxy:{}}),onMounted(){},onUnmounted:f=>dispose=f,ref,watch,nextTick,defineProps:()=>props,defineEmits:()=>(...args)=>emitted.push(args)}
 const value=new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {shortcuts,choose,openProfile,beginRead}`)(deps)
 return {...value,emitted,props,dispose:()=>dispose()}
}
test('the bottom shortcuts preserve all five existing actions and the profile event',()=>{
 const p=layout()
 assert.deepEqual(p.shortcuts.map(s=>[s.key,s.name]),[['plans','AI专属计划'],['family','家庭档案'],['camera','拍照记餐'],['today','今日餐单'],['community','加入社群']])
 for(const key of ['plans','family','camera','today','community']){p.choose(key);assert.deepEqual(p.emitted.at(-1),['shortcut',key])}
 p.openProfile();assert.deepEqual(p.emitted.at(-1),['profile'])
})
test('the five actions remain outside the scrolling conversation and above the composer',()=>{
 const source=readFileSync(new URL('../src/components/NutritionistLayout.vue',import.meta.url),'utf8')
 const conversationEnd=source.indexOf('</scroll-view>'),bar=source.indexOf('class="bottom-shortcuts"'),input=source.indexOf('<slot name="composer"/>')
 assert.ok(conversationEnd<bar&&bar<input)
 assert.match(source,/:disabled="voiceBusy" @click="choose\(item.key\)"/)
 assert.doesNotMatch(source,/chat-menu-sheet|more-button/)
})

test('welcome preserves shuffle and the latest today entry alongside bottom shortcuts',()=>{
 const source=readFileSync(new URL('../src/components/ChatWelcome.vue',import.meta.url),'utf8')
 assert.match(source,/prompt-grid/);assert.match(source,/\$emit\('ask',prompt\)/)
 const chat=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8')
 assert.match(chat,/@ask="askPrompt" @shuffle="shufflePrompts"/)
 assert.match(chat,/inlineTodayOpen.value=!inlineTodayOpen.value/)
 assert.match(chat,/function camera\(\)[\s\S]*?url:'\/pages\/chat\/camera'/)
 assert.match(chat,/key==='camera'\)uni\.navigateTo\(\{url:'\/pages\/scan\/index'/)
})

async function renderLayout(showShortcuts) {
 const {compile,createSSRApp,h}=await import('vue')
 const {renderToString}=await import('vue/server-renderer')
 const source=readFileSync(new URL('../src/components/NutritionistLayout.vue',import.meta.url),'utf8')
 const template=source.match(/<template>([\s\S]*?)<\/template>/)[1]
 const render=compile(template,{isCustomElement:tag=>['view','text','scroll-view'].includes(tag)})
 const state=layout(),props={entryTransition:true,shortcutsCollapsed:!showShortcuts,keyboardOpen:false,welcomeMounted:false,welcomeLeaving:false,viewportStyle:{},transitionTicket:0,scrollLocked:false,restoreTop:0,rememberScroll(){},voiceBusy:false,historyOpen:false,scrollTarget:''}
 return renderToString(createSSRApp({render,components:{AppNavBar:{setup:(_props,{slots})=>()=>h('nav',slots.default?.())},AppIcon:{render:()=>h('span',{class:'app-icon'})}},setup:()=>({...state,...props,props})}))
}

test('shortcut actions remain available outside welcome and while the keyboard is focused',async()=>{
 const shown=await renderLayout(true),hidden=await renderLayout(false)
 assert.match(shown,/aria-label="常用功能"/)
 assert.doesNotMatch(hidden,/is-collapsed/);assert.match(hidden,/aria-label="常用功能"/)
 for(const label of ['AI专属计划','家庭档案','拍照记餐','今日餐单','加入社群'])assert.ok(shown.includes(label))
})

test('the shell retains the history artwork, compact shortcuts and welcome density',()=>{
 const shell=readFileSync(new URL('../src/components/NutritionistLayout.vue',import.meta.url),'utf8')
 const welcome=readFileSync(new URL('../src/components/ChatWelcome.vue',import.meta.url),'utf8')
 assert.match(shell,/static\/chat\/history\.png/)
 assert.match(shell,/shortcut-reveal/);assert.match(shell,/entry-transition/)
 assert.match(welcome,/prompt-grid/);assert.match(welcome,/density-small/)
 assert.match(welcome,/\$emit\('ask',prompt\)/)
})

test('the conversation drawer retains its narrow panel and one-row new-conversation header',()=>{
 const source=readFileSync(new URL('../src/components/ChatConversationDrawer.vue',import.meta.url),'utf8')
 const heading=source.match(/<view class="drawer-heading">([\s\S]*?)<\/AppNavBar>/)?.[1]||''
 assert.match(heading,/class="drawer-new"/)
 assert.doesNotMatch(source,/class="drawer-close"/)
 assert.match(source,/width:76vw/)
 assert.match(source,/class="drawer-settings-icon"/)
})


test('a delayed automatic scroll target does not re-enable follow after an upward gesture',async()=>{
 const p=layout();p.beginRead({deltaY:-400});p.props.followBottom=false;p.props.scrollTarget='chat-bottom-anchor';await nextTick()
 const changes=p.emitted.filter(e=>e[0]==='readingChange');assert.ok(changes.length);assert.equal(changes.at(-1)[1].following,false);p.dispose()
})
