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

test('the rendered reply bubble follows real reply activity and excludes silent return errors',()=>{
 const reply=elements.find(n=>attribute(n,'id')==='stream-answer')
 assert.equal(directive(reply,'if'),'liveAnswer||entryReady&&!profileLoading&&replyPending')
 assert.equal(elements.some(n=>attribute(n,'aria-label')==='咨询未完成'),false)
 assert.doesNotMatch(template,/查看该成员档案|showMemberArchive|重试连接/)
})

test('rendered reference cards wire their detail event to the corresponding selected business date',()=>{
 const cards=elements.filter(n=>n.tag==='DailyMealPlanCard'&&n.props.some(p=>p.name==='detail-mode'))
 assert.equal(cards.length,1)
 for(const card of cards){
  const date=directive(card,'bind','plan').includes('message.planDate')?'message.planDate':'todayPlan.date'
  assert.equal(directive(card,'on','detail'),`openDailyMeal($event,${date})`)
 }
 const menu=elements.find(n=>n.tag==='TodayMealPlanSheet')
 assert.ok(menu)
 assert.equal(directive(menu,'on','detail'),'openDailyMeal($event,todayPlan.date)')
 assert.equal(directive(menu,'on','plan'),'acceptTodayPlan')
 assert.equal(directive(menu,'bind','read-only'),undefined)
})

test('chat and today menu send their own plan to the shared all-meal purchase handler',()=>{
 const card=elements.find(n=>n.tag==='DailyMealPlanCard')
 const menu=elements.find(n=>n.tag==='TodayMealPlanSheet')
 assert.equal(directive(card,'on','all'),'buyAllMeals')
 assert.equal(directive(menu,'on','all'),'buyAllMeals')
 assert.equal(directive(card,'on','purchase'),undefined)
 assert.equal(directive(menu,'on','purchase'),undefined)
})

test('the today menu passes its actual pending task into the continuation handler',()=>{
 const menu=elements.find(n=>n.tag==='TodayMealPlanSheet')
 assert.equal(directive(menu,'on','continue'),'resumePlanQuestion($event)')
})
test('the generating composer exposes an explicit stop control connected to task cancellation',()=>{
 const stop=elements.find(n=>n.tag==='button'&&attribute(n,'aria-label')==='停止生成')
 assert.ok(stop);assert.equal(directive(stop,'else-if'),"primaryMode==='stop'");assert.equal(attribute(stop,'key'),'stop')
 assert.equal(directive(stop,'on','click'),'stopQuestion')
 assert.equal(directive(stop,'bind','disabled'),'!preparingSend&&task.busy')
})
test('failed and interrupted messages keep only the message marker without a recovery card',()=>{
 const marker=elements.find(n=>attribute(n,'class')==='message-issue')
 assert.ok(marker);assert.equal(directive(marker,'if'),"hasMessageIssue(message)||message.role==='user'&&message.status==='unknown'")
 assert.equal(elements.some(n=>attribute(n,'class')==='recovery-card'),false)
 assert.equal(elements.some(n=>n.tag==='button'&&['editFailedQuestion','restartChat'].includes(directive(n,'on','click'))),false)
 assert.equal(directive(marker,'on','click'),'messageStatus(message)')
 assert.equal(attribute(marker,'role'),'button')
 assert.equal(attribute(marker,'tabindex'),'0')
 assert.match(source,/\.message-issue\{[^}]*background:#d83a3a/)
})

test('submission and reconciliation always render a visible non-error control',()=>{
 const submitting=elements.find(n=>attribute(n,'key')==='submitting')
 assert.equal(submitting.tag,'button');assert.equal(directive(submitting,'if'),"primaryMode==='submitting'")
 assert.equal(attribute(submitting,'aria-label'),'正在发送问题')
 assert.ok(submitting.children.some(n=>n.type===1&&attribute(n,'class')==='primary-spinner'))
 const check=elements.find(n=>attribute(n,'key')==='check')
 assert.equal(check.tag,'button');assert.equal(directive(check,'on','click'),'checkTaskStatus')
 assert.equal(directive(check,'bind','disabled'),'!canCheckTask')
 assert.ok(check.children.some(n=>n.type===1&&attribute(n,'class')==='check-task-icon'))
 assert.equal(check.children.some(n=>n.type===1&&attribute(n,'class')==='message-issue'),false)
 assert.match(source,/\.send-button\[disabled\]\{[^}]*background:var\(--ui-accent,#303739\);color:#fff;opacity:1/)
 assert.match(source,/\.message-issue\.is-unconfirmed\{[^}]*background:#eef0f2/)
 const stopped=elements.find(n=>attribute(n,'class')==='message-status-note')
 assert.equal(directive(stopped,'if'),"message.role==='user'&&message.status==='cancelled'")
})
