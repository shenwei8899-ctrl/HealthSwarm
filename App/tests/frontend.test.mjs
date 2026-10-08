import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeProfile,saveProfile,getProfile,saveRecord,getRecords } from '../src/utils/profile.js'
import { mockService } from '../src/services/mock.js'
import { createDemoOrder,getOrder,updateOrder,orderStatus } from '../src/utils/orders.js'
import { remember,forget } from '../src/utils/memory.js'
import { confirmedFor,vegetableTrend } from '../src/utils/feedback.js'
import { localDate } from '../src/utils/meal-state.js'
import { readFileSync } from 'node:fs'
import { ref, computed } from 'vue'
import { photoEstimate } from '../src/utils/demo.js'
import { DIABETES_CASE_ID, getActiveHealthCaseId } from '../src/utils/health-cases.js'
import { todayPlan, mealProfile } from '../src/utils/meal-state.js'
import { ingredientConflicts, memberNotes } from '../src/utils/health.js'
import { mealFromRoute } from '../src/utils/meal-flow.js'
import { portionOptions, oilOptions, createPortionDraft, confirmPortionDraft, intakeSummary } from '../src/utils/scan-portions.js'
test('record day is Beijing time across UTC midnight boundaries',()=>{assert.equal(localDate(new Date('2026-10-05T16:01:00Z')),'2026-10-06');assert.equal(localDate(new Date('2026-10-05T15:59:00Z')),'2026-10-05')})
function setup(){const storage=new Map();globalThis.uni={getStorageSync:k=>storage.get(k),setStorageSync:(k,v)=>storage.set(k,JSON.parse(JSON.stringify(v)))};saveProfile(normalizeProfile({viewerAccount:'creator',members:[{id:1,name:'我',relation:'本人',age:30,claimedBy:'creator',healthStatus:'none'},{id:2,name:'妈妈',relation:'母亲',age:55,claimedBy:'mom-account',healthStatus:'set',conditions:['高血压']}],memories:[]}))}
test('default creator memory provenance never treats an unclaimed member as the speaker',()=>{setup();const p=getProfile();delete p.viewerAccount;delete p.members[1].claimedBy;saveProfile(p);const entry=remember('我以后不吃花生').entry;assert.equal(entry.providerId,1);assert.equal(entry.sourceKind,'本人提供')})
test('address validation and order snapshots survive address edits',async()=>{setup();await assert.rejects(mockService.saveAddress({name:'测试'}),/完整填写/);const a=await mockService.saveAddress({name:'测试',phone:'13800000000',region:'上海市',detail:'虚构路88号'});const order=createDemoOrder({items:[],totalCents:100,meal:'午餐',addressSnapshot:a});await mockService.saveAddress({...a,detail:'虚构路99号'});assert.equal(mockService.selectedAddress().detail,'虚构路99号');assert.equal(getOrder(order.id).addressSnapshot.detail,'虚构路88号')})
test('reports belong to one member and require owner to share',async()=>{setup();const report=await mockService.addReport(2,'拍照');assert.equal(getProfile().members[0].reports,undefined);await assert.rejects(mockService.confirmReport(2,report.id,true),/本人/);await mockService.confirmReport(2,report.id,false);assert.equal(getProfile().members[1].reports[0].shared,false);const p=getProfile();p.viewerAccount='mom-account';saveProfile(p);await mockService.confirmReport(2,report.id,true);assert.equal(getProfile().members[1].reports[0].shared,true)})
test('family dialogue updates claimed member with provenance and reversible state',()=>{setup();const entry=remember('妈妈有糖尿病').entry;assert.equal(entry.memberId,2);assert.equal(entry.sourceKind,'家人提供');assert.equal(entry.providerId,1);assert.equal(getProfile().members[1].claimedBy,'mom-account');assert.ok(getProfile().members[1].conditions.includes('糖尿病'));forget(entry.id);assert.deepEqual(getProfile().members[1].conditions,['高血压']);assert.ok(remember('妈妈没有糖尿病').question)})
test('record correction keeps its ID and advances version without creating a second record',async()=>{setup();saveRecord({id:'record-1',version:1,meal:'晚餐',dishes:['鱼']});await mockService.correctRecord('record-1',{id:'different',dishes:['豆腐']});assert.equal(getRecords().length,1);assert.equal(getRecords()[0].id,'record-1');assert.equal(getRecords()[0].version,2);assert.deepEqual(getRecords()[0].dishes,['豆腐'])})
test('member feedback excludes unconfirmed shared food and gaps are not zeros',()=>{const records=[{id:1,createdAt:'2026-10-06T04:00:00Z',meal:'午餐',dishes:['番茄','鱼'],captureScope:'家庭共享桌菜',memberIntake:[{memberId:1,dishes:['鱼'],portion:'一般'},{memberId:2,dishes:['番茄'],portion:'少量'}]}];const own=confirmedFor(records,1),mom=confirmedFor(records,2);assert.deepEqual(own[0].dishes,['鱼']);assert.equal(confirmedFor(records,3).length,0);const end=new Date('2026-10-06T12:00:00+08:00');assert.equal(vegetableTrend(own,7,end).at(-1).ratio,0);assert.equal(vegetableTrend(mom,7,end).at(-1).ratio,1);assert.equal(vegetableTrend(own,7,end)[0].ratio,null)})

function receiptPage({ batches = false, modalFailure = false } = {}) {
  setup()
  const created = createDemoOrder({ items: [], totalCents: 7420, meal: '午餐',
    sourcePlanId: batches ? 'test-plan' : '',
    deliveryBatches: batches ? [{index:1}, {index:2}] : [] })
  const calls = { modal: null, toast: null }
  Object.assign(globalThis.uni, {
    showModal(options) {
      // Model the native WeChat constraint that H5 preview does not enforce.
      assert.ok([...options.confirmText].length <= 4, '微信确认按钮文字最多 4 个字符')
      calls.modal = options
      if (modalFailure) options.fail({ errMsg: 'showModal:fail' })
    },
    showToast(options) { calls.toast = options },
  })
  let show
  const deps = { ref, computed, getOrder, updateOrder, orderStatus,
    onLoad(callback) { callback({id:created.id}) },
    onShow(callback) { show = callback },
  }
  const script = readFileSync(new URL('../src/pages/orders/detail.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const page = new Function('deps', `const {${Object.keys(deps).join(',')}} = deps;\n${script}\nreturn { order, delivered, confirmReceived, selectBatch }`)(deps)
  show()
  return { ...page, calls, show, id:created.id }
}

test('receipt opens a WeChat-compatible modal and only confirmation persists delivery',()=>{
  const page = receiptPage()
  page.confirmReceived()
  page.calls.modal.success({confirm:false})
  assert.equal(getOrder(page.id).status,'paid')
  assert.equal(page.delivered.value,false)
  page.confirmReceived()
  page.calls.modal.success({confirm:true})
  assert.equal(getOrder(page.id).status,'delivered')
  assert.ok(getOrder(page.id).deliveredAt)
  page.show()
  assert.equal(page.delivered.value,true)
})

test('batch receipt affects only the selected batch and completes after all batches arrive',()=>{
  const page = receiptPage({batches:true})
  page.selectBatch(2)
  page.confirmReceived()
  page.calls.modal.success({confirm:true})
  assert.deepEqual(getOrder(page.id).receivedBatchIndices,[2])
  assert.equal(getOrder(page.id).status,'partial')
  assert.equal(page.delivered.value,true)
  page.selectBatch(1)
  assert.equal(page.delivered.value,false)
  page.confirmReceived()
  page.calls.modal.success({confirm:false})
  assert.deepEqual(getOrder(page.id).receivedBatchIndices,[2])
  page.confirmReceived()
  page.calls.modal.success({confirm:true})
  assert.deepEqual(getOrder(page.id).receivedBatchIndices,[1,2])
  assert.equal(getOrder(page.id).status,'delivered')
})

test('receipt modal failure gives feedback and leaves the order unreceived',()=>{
  const page = receiptPage({modalFailure:true})
  page.confirmReceived()
  assert.equal(page.calls.toast.title,'收货确认窗口未能打开，请重试')
  assert.equal(page.calls.toast.icon,'none')
  assert.equal(getOrder(page.id).status,'paid')
  assert.equal(page.delivered.value,false)
})

function scanPage(members = '1') {
  setup()
  const calls = { redirects: [], back: null }
  Object.assign(globalThis.uni, {
    showToast() {},
    showActionSheet(options) { calls.actionSheet = options },
    showModal(options) { calls.modal = options },
    chooseImage(options) { calls.image = options; options.success({tempFilePaths:['/tmp/selected-meal.jpg']}) },
    redirectTo(options) { calls.redirects.push(options); options.fail() },
  })
  const deps = {
    ref, computed, getProfile, saveRecord, backHome() {}, photoEstimate,
    DIABETES_CASE_ID, getActiveHealthCaseId, todayPlan, mealProfile,
    ingredientConflicts, memberNotes, mealFromRoute,
    portionOptions, oilOptions, createPortionDraft, confirmPortionDraft, intakeSummary,
    onLoad(callback) { callback({meal:'晚餐', members}) },
    onBackPress(callback) { calls.back = callback },
    setTimeout(callback) { callback() },
  }
  // Exercise the actual page handlers with the native APIs stubbed, rather than
  // reproducing the popup/save logic in a separate test implementation.
  const script = readFileSync(new URL('../src/pages/scan/index.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const exposed = 'portion, grams, oil, imagePath, status, portionDraft, portionDialogOpen, portionsConfirmed, estimate, draftEstimate, confirmedIntake, recognizedDishes, openPortions, closePortions, applyPortions, chooseImage, confirmRecord, correction, markNotEaten, toggleDraftDish, select, goBack'
  return { ...new Function('deps',`const {${Object.keys(deps).join(',')}} = deps;\n${script}\nreturn {${exposed}}`)(deps), calls }
}

test('cancel and page back discard portion popup edits and keep the confirmed meal',()=>{
  const page=scanPage()
  page.openPortions()
  page.portionDraft.value.people[0].portion='一般'
  page.portionDraft.value.people[0].grams='120'
  page.applyPortions()
  page.openPortions()
  page.portionDraft.value.people[0].dishes.pop()
  page.portionDraft.value.people[0].portion='少量'
  page.portionDraft.value.oil='偏多'
  assert.equal(page.calls.back(),true)
  assert.equal(page.portion.value,'一般')
  assert.equal(page.grams.value,120)
  assert.equal(page.oil.value,'不确定')
  assert.equal(page.confirmedIntake.value[0].dishes.length,3)
  page.openPortions()
  assert.equal(page.portionDraft.value.people[0].portion,'一般')
  assert.equal(page.portionDraft.value.people[0].dishes.length,3)
  page.goBack()
  assert.equal(page.portionDialogOpen.value,false)
  assert.equal(page.calls.back(),false)
})

test('family popup starts without assumed consumption and saves each member independently',()=>{
  const page=scanPage('1,2')
  page.openPortions()
  assert.ok(page.portionDraft.value.people.every(p=>p.dishes.length===0))
  assert.throws(()=>confirmPortionDraft(page.portionDraft.value,page.recognizedDishes.value),/吃过的菜/)
  const [own,mom]=page.portionDraft.value.people
  page.toggleDraftDish(own,'西兰花')
  own.portion='少量'
  own.grams='75.5'
  page.markNotEaten(mom)
  page.applyPortions()
  page.confirmRecord('records')
  const record=getRecords()[0]
  assert.deepEqual(record.memberIntake[0].dishes,['西兰花'])
  assert.equal(record.memberIntake[0].grams,75.5)
  assert.deepEqual(record.memberIntake[1].dishes,[])
  assert.equal(record.memberIntake[1].noneConfirmed,true)
  assert.equal(intakeSummary(record.memberIntake[1]),'未吃这些菜')
  assert.equal(record.kcal,null)
  assert.deepEqual(confirmedFor([record],1)[0].dishes,['西兰花'])
})

test('optional grams are validated without percentage requirements and unknown portions stay unknown',()=>{
  const page=scanPage()
  page.openPortions()
  const person=page.portionDraft.value.people[0]
  for(const invalid of ['0','-1','NaN','Infinity']) {
    person.grams=invalid
    assert.throws(()=>confirmPortionDraft(page.portionDraft.value,page.recognizedDishes.value),/大于 0/)
  }
  person.grams=''
  assert.equal(confirmPortionDraft(page.portionDraft.value,page.recognizedDishes.value).people[0].grams,null)
  person.grams='120'
  page.applyPortions()
  assert.equal(page.estimate.value,null)
  assert.equal(page.confirmedIntake.value[0].grams,120)
  page.openPortions()
  page.portionDraft.value.people[0].portion='一般'
  const before=page.draftEstimate.value.kcal
  page.portionDraft.value.oil='偏多'
  assert.ok(page.draftEstimate.value.kcal>before)
  page.closePortions()
  assert.equal(page.estimate.value,null)
})

test('photo selection keeps the original photo and both save destinations retry one record',()=>{
  const page=scanPage()
  page.chooseImage('album')
  assert.deepEqual(page.calls.image.sourceType,['album'])
  assert.equal(page.status.value,'result')
  assert.equal(page.imagePath.value,'/tmp/selected-meal.jpg')
  page.confirmRecord('chat')
  assert.equal(getRecords().length,0)
  assert.equal(page.portionDialogOpen.value,true)
  page.portionDraft.value.people[0].portion='一般'
  page.applyPortions()
  page.confirmRecord('chat')
  page.confirmRecord('records')
  assert.equal(getRecords().length,1)
  const record=getRecords()[0]
  assert.equal(record.photoPath,'/tmp/selected-meal.jpg')
  assert.ok(page.calls.redirects[0].url.includes('recordId='+record.id))
  assert.equal(page.calls.redirects[1].url,'/pages/records/index')
})

test('dish correction keeps the original photo and requires confirmation of the changed food list',()=>{
  const page=scanPage()
  page.chooseImage('camera')
  page.openPortions()
  page.portionDraft.value.people[0].portion='一般'
  page.applyPortions()
  page.correction()
  page.calls.modal.success({confirm:true,content:'西兰花、番茄炒蛋'})
  assert.equal(page.imagePath.value,'/tmp/selected-meal.jpg')
  assert.equal(page.portionsConfirmed.value,false)
  page.openPortions()
  assert.deepEqual([...page.portionDraft.value.people[0].dishes],['西兰花'])
  assert.equal(page.portionDraft.value.people[0].portion,'一般')
})

test('switching the personal diner never assigns the previous members quantity to the new member',()=>{
  const page=scanPage()
  page.openPortions()
  page.portionDraft.value.people[0].portion='较多'
  page.portionDraft.value.people[0].grams='200'
  page.applyPortions()
  page.select('member')
  page.calls.actionSheet.success({tapIndex:1})
  assert.equal(page.confirmedIntake.value[0].memberName,'妈妈')
  assert.equal(page.grams.value,null)
  assert.equal(page.portion.value,'不确定')
  assert.equal(page.estimate.value,null)
  assert.equal(page.portionsConfirmed.value,false)
})
