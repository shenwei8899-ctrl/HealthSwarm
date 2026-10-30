import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createRequire} from 'node:module'
const require=createRequire(import.meta.url),vueRequire=createRequire(require.resolve('vue'))
const {baseParse}=vueRequire('@vue/compiler-dom')
const source=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8')
const template=source.slice(source.indexOf('<template>')+10,source.lastIndexOf('</template>'))
const elements=[]
function walk(node){if(node.type===1)elements.push(node);for(const child of node.children||[])walk(child)}
walk(baseParse(template))
const directive=(node,name,arg)=>node.props.find(p=>p.type===7&&p.name===name&&(!arg||p.arg?.content===arg))?.exp?.content
const attribute=(node,name)=>node.props.find(p=>p.type===6&&p.name===name)?.value?.content

test('rendered reference cards wire their detail event to the corresponding selected business date',()=>{
 const cards=elements.filter(n=>n.tag==='DailyMealPlanCard'&&n.props.some(p=>p.name==='detail-mode'))
 assert.equal(cards.length,2)
 for(const card of cards){
  const date=directive(card,'bind','plan').includes('message.planDate')?'message.planDate':'todayPlan.date'
  assert.equal(directive(card,'on','detail'),`openDailyMeal($event,${date})`)
 }
})
test('the generating composer exposes an explicit stop control connected to task cancellation',()=>{
 const stop=elements.find(n=>n.tag==='button'&&attribute(n,'aria-label')==='停止生成')
 assert.ok(stop);assert.equal(directive(stop,'else-if'),"primaryMode==='stop'");assert.equal(attribute(stop,'key'),'stop')
 assert.equal(directive(stop,'on','click'),'flow.cancelRequest()')
})
test('failed and interrupted messages keep only the message marker without a recovery card',()=>{
 const marker=elements.find(n=>attribute(n,'class')==='message-issue')
 assert.ok(marker);assert.equal(directive(marker,'if'),'hasMessageIssue(message)')
 assert.equal(elements.some(n=>attribute(n,'class')==='recovery-card'),false)
 assert.equal(elements.some(n=>n.tag==='button'&&['editFailedQuestion','restartChat'].includes(directive(n,'on','click'))),false)
 assert.equal(directive(marker,'on','click'),'messageStatus(message)')
 assert.match(source,/\.message-issue\{[^}]*background:#d83a3a/)
})


test('a cancellation reconciled to a running task makes the wired stop button reachable again',()=>{
 const expression=source.match(/const primaryMode=computed\(\(\)=>?([^\n]+)\)/)[1]
 const mode=new Function('task','canCancel','voiceMode','hasDraftContent',`return ${expression}`)
 assert.equal(mode({value:{status:'running',cancelPhase:'error'}},{value:true},{value:false},{value:false}),'stop')
 assert.equal(mode({value:{status:'running',cancelPhase:'unknown'}},{value:true},{value:false},{value:false}),'check')
 const stop=elements.find(n=>n.tag==='button'&&attribute(n,'aria-label')==='停止生成')
 assert.equal(directive(stop,'on','click'),'flow.cancelRequest()')
})
