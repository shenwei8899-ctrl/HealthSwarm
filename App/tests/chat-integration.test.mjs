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
 const cards=elements.filter(n=>n.tag==='DailyMealPlanCard'&&n.props.some(p=>p.name==='detail-mode')&&directive(n,'bind','plan')?.includes('message.planDate'))
 assert.equal(cards.length,1)
 for(const card of cards){
  const date=directive(card,'bind','plan').includes('message.planDate')?'message.planDate':'todayPlan.date'
  assert.equal(directive(card,'on','detail'),`openDailyMeal($event,${date},message.menuView?verifiedMealView(message):dailyPlans[message.planDate])`)
 }
 const weekly=elements.find(n=>n.tag==='WeeklyMealPlanCard')
 assert.equal(directive(weekly,'bind','detail'),"weeklyOpenGroup===message.weeklyPlan.group_id?weeklyDetail:null")
 assert.equal(directive(weekly,'on','day'),'openWeeklyDay($event,message.weeklyPlan.group_id)')
 const menu=elements.find(n=>n.tag==='TodayMealPlanSheet')
 assert.ok(menu)
 assert.equal(directive(menu,'on','detail'),'showTodayMeal')
 assert.equal(directive(menu,'bind','state'),'todayMenu')
})

test('chat retains its all-meal handler while the today menu preserves the selected meal scope',()=>{
 const card=elements.find(n=>n.tag==='DailyMealPlanCard')
 const menu=elements.find(n=>n.tag==='TodayMealPlanSheet')
 assert.equal(directive(card,'on','all'),'buyAllMeals')
 assert.equal(directive(menu,'on','dish'),'openDailyDish($event,todayMenu.date,todayMenu.plan)')
 assert.equal(directive(card,'on','purchase'),undefined)
 assert.equal(directive(menu,'on','purchase'),undefined)
})

test('the today menu passes its actual pending task into the continuation handler',()=>{
 const menu=elements.find(n=>n.tag==='TodayMealPlanSheet')
 assert.equal(directive(menu,'on','action'),'actTodayMenu')
 assert.match(source,/resumePlanQuestion\(todayMenu.pending\)/)
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


test('the welcome excludes the menu while the conversation shares its state and actions with the sheet',()=>{
 const welcome=elements.find(n=>n.tag==='template'&&n.props.some(p=>p.type===7&&p.name==='slot'&&p.arg?.content==='welcome'))
 assert.ok(welcome)
 assert.equal(welcome.children.some(n=>n.tag==='TodayMealPlanContent'),false)
 assert.ok(welcome.children.some(n=>n.tag==='ChatWelcome'))
 const views=elements.filter(n=>n.tag==='TodayMealPlanContent')
 assert.equal(views.length,1)
 for(const view of views){
  assert.equal(directive(view,'bind','state'),'todayMenu')
  assert.equal(directive(view,'on','detail'),'showTodayMeal')
  assert.equal(directive(view,'on','dish'),'openDailyDish($event,todayMenu.date,todayMenu.plan)')
  assert.equal(directive(view,'on','action'),'actTodayMenu')
 }
 const sheet=readFileSync(new URL('../src/components/TodayMealPlanSheet.vue',import.meta.url),'utf8')
 assert.doesNotMatch(sheet,/createTodayMealPlan|todayMealPlanState/)
 assert.match(sheet,/<TodayMealPlanContent :state="state"/)
})

test('the inline menu appears after entering chat and stays hidden during welcome loading and transitions',()=>{
 const menu=elements.find(n=>n.tag==='TodayMealPlanContent')
 const show=new Function('welcomeMounted','entryView','presentation','props',`return Boolean(${directive(menu,'if')})`)
 const cases=[
  {name:'initial loading',mounted:false,engaged:false,welcome:true,expected:false},
  {name:'welcome page',mounted:true,engaged:false,welcome:true,expected:false},
  {name:'welcome leaving',mounted:true,engaged:true,welcome:true,expected:false},
  {name:'focused composer without a sent message',mounted:false,engaged:true,welcome:true,expected:true},
  {name:'existing conversation',mounted:false,engaged:false,welcome:false,expected:true},
  {name:'empty composer restored to welcome',mounted:true,engaged:false,welcome:true,expected:false},
  {name:'explicit task entry',mounted:false,engaged:false,welcome:true,taskType:'consultation',expected:true},
 ]
 for(const item of cases){
  assert.equal(show(item.mounted,{engaged:item.engaged},{welcome:item.welcome},{route:{taskType:item.taskType}}),item.expected,item.name)
 }
})

test('selected menu replies use the dish grid and its verified plan for rendering and navigation',()=>{
 const card=elements.find(node=>node.tag==='DailyMealPlanCard')
 assert.equal(directive(card,'bind','dish-grid'),'!!message.menuView')
 assert.equal(directive(card,'bind','plan'),'message.menuView?verifiedMealView(message):dailyPlans[message.planDate]')
 assert.match(directive(card,'on','detail'),/verifiedMealView\(message\)/)
 assert.match(directive(card,'on','dish'),/verifiedMealView\(message\)/)
})
