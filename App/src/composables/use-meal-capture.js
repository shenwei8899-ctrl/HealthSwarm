import { computed,reactive,ref,watch,onMounted,onUnmounted } from 'vue'
import { onShow,onHide,onUnload } from '@dcloudio/uni-app'
import { createMealNutritionClient,mealNutritionState,recognizedMealDish,bindMealSource,exactMealSource } from '../services/meal-nutrition.js'
import { supplementCandidates,appendMealCandidates,preserveMealEvidence,createMealSupplementSaver,mealDishKey } from '../services/meal-supplement.js'
import { request } from '../services/request.js'
import { scopedStorage,storageContext } from '../services/storage.js'
import { createMealPhotoClient,photoState,mealPhotoFailure,mealPhotoUploadMessage } from '../services/meal-photo-client.js'
import { createCloudMealSaver,personalMeal,mealLabels,mealDay,feedbackUrl,readDietRecord } from '../services/cloud-meals.js'
import { commerce } from '../services/commerce.js'
import { getSession } from '../services/session.js'
import { readDailyMealPlan } from '../services/daily-meal-plan.js'
import { captureMenuDishes } from '../services/capture-menu.js'
import { mealPhotoNavigation } from '../services/meal-photo-navigation.js'
import { captureUiKey } from '../services/meal-record-entry.js'

/** Shared editor for the photo page and dish recording sheet. */
export function useMealCapture(props){

const photoEntry=props.route.captureNavigation?mealPhotoNavigation.read(props.route.captureNavigation):null
const sourcePhoto=!!photoEntry
const photoContext=sourcePhoto?storageContext():null
const expectedDishes=photoEntry?.dishes.map(d=>d.name).join('、')||''
const entryKey=ref(photoEntry?.key||props.entry?.key||''),entryBlocked=ref(!!props.route.captureNavigation&&!photoEntry)
let handedOff=false
const uiKey=()=>captureUiKey(entryKey.value)
function currentMealContext(){const local=new Date(Date.now()+8*3600000).toISOString(),hour=Number(local.slice(11,13));return {date:local.slice(0,10),time:local.slice(11,16),meal:hour<10?'breakfast':hour<15?'lunch':hour<21?'dinner':'snack'}}
const initialContext=currentMealContext()
const routeDate=props.route.date
if(typeof routeDate==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(routeDate)&&Number.isFinite(Date.parse(routeDate+'T00:00:00Z'))&&new Date(routeDate+'T00:00:00Z').toISOString().slice(0,10)===routeDate)initialContext.date=routeDate
const members=ref([]),people=ref([]),dishes=ref([]),captureScope=ref('单人餐盘'),mealType=ref(Object.hasOwn(mealLabels,props.route.meal)?props.route.meal:initialContext.meal),date=ref(initialContext.date),time=ref(initialContext.time),oil=ref('不确定'),photo=ref(''),error=ref(''),notice=ref(''),busy=ref(false),editing=ref(false),source=ref('手动填写'),saved=ref(null),pendingGroup=ref(null)
const membersLoading=ref(false),photoPreparing=ref(false),localPhotoPending=ref(false)
const supplement=ref(null),editingRecord=ref(null),extraPhotos=ref([]),supplementSaver=createMealSupplementSaver()
const vision=reactive(photoState()),photoClient=createMealPhotoClient({state:vision,namespace:()=>entryKey.value,sourceContext:()=>photoEntry?.sourceContext||null}),saver=createCloudMealSaver({entryKey:()=>entryKey.value})
const nutrition=reactive(mealNutritionState()),nutritionClient=createMealNutritionClient({state:nutrition})
const adjusting=ref(''),mapping=ref(''),sourceQuery=ref(''),gramInput=ref(''),portionCount=ref('1'),acceptMissing=ref(false),familyOpen=ref(false),photoOpen=ref(false)
const nutritionRows=computed(()=>saved.value?saved.value.rows.map(r=>({member_id:r.memberId,...r.record?.snapshot?.nutrition,meal:r.record?.snapshot?.meal})):nutrition.results)
const preview=computed(()=>nutritionRows.value.length===1?nutritionRows.value[0]:null)
const previewReady=computed(()=>!!preview.value&&!nutrition.busy&&!nutrition.error)
const incomplete=computed(()=>nutritionRows.value.length>1?nutrition.busy||!!nutrition.error||nutritionRows.value.some(r=>!r.complete):!previewReady.value||!preview.value.complete)
const nutrients=[['protein_g','蛋白质'],['carbohydrate_g','碳水'],['fat_g','脂肪']]
const consent=computed({get:()=>!!vision.consent,set:value=>photoClient.setConsent(value)})
const origin=ref(null)
const portionDraft=ref([]),portionError=ref('');
const manualOpen=ref(false),manualText=ref(''),manualError=ref(''),menuNotice=ref('')
const mealKeys=Object.keys(mealLabels),portions=['少量','一般','较多','不确定'],oils=['少油','一般','偏多','不确定']
const locked=computed(()=>entryBlocked.value||busy.value||(vision.busy&&!photoPreparing.value)||localPhotoPending.value||!!vision.pending||!!supplementSaver.read()||(!!pendingGroup.value&&!pendingGroup.value.editable&&!saved.value)),selected=computed(()=>people.value.filter(p=>p.selected)),hasDishes=computed(()=>dishes.value.length>0)
const captureLocked=computed(()=>locked.value||!!saved.value||manualOpen.value||!!supplement.value)
const canSave=computed(()=>!entryBlocked.value&&!editing.value&&!manualOpen.value&&!supplement.value&&selected.value.length>0&&selected.value.every(p=>p.noneConfirmed||p.dishes.length)&&selected.value.some(p=>!p.noneConfirmed&&p.dishes.length))
let epoch=0,opening=false,scope='',loading=false,preparation=null,photoPreparation=null,entryDay=initialContext.date,photoVersion=0,pollTimer=null,nutritionTimer=null
function queueNutrition(){clearTimeout(nutritionTimer);nutritionClient.invalidate();acceptMissing.value=false;if(!hasDishes.value||manualOpen.value||saved.value)return;const mine=epoch;nutritionTimer=setTimeout(()=>{if(mine===epoch)void refreshNutrition()},350)}
async function refreshNutrition(){if(saved.value||manualOpen.value)return;try{const meals=selected.value.filter(p=>!p.noneConfirmed&&p.dishes.length).map(savedMeal);if(meals.length)await nutritionClient.preview(meals)}catch(e){error.value=e.message}}
function amount(code){const value=previewReady.value?preview.value.totals?.[code]:null;return value==null?'—':String(code==='energy_kcal'?Math.round(Number(value)):Math.round(Number(value)*10)/10)}
function dishEnergy(dish){const row=nutritionRows.value[0],id=row?.meal?.items?.find(i=>i.item_id===dish.item_id||!dish.item_id&&i.name===dish.name)?.item_id;const value=row?.items?.find(i=>i.item_id===id)?.nutrients?.energy_kcal;return value==null?'—':String(Math.round(Number(value)))}
function pollResult(){clearTimeout(pollTimer);if(!vision.job||!['pending','running'].includes(vision.job.execution_status))return;const mine=epoch;pollTimer=setTimeout(async()=>{if(mine!==epoch)return;if(vision.busy){pollResult();return}await job(vision.job.task_id);if(mine===epoch)pollResult()},1500)}
async function authorizeAndAnalyze(){photoClient.setConsent(true);await analyze()}
async function openMapping(dish){mapping.value=mealDishKey(dish);adjusting.value='';sourceQuery.value=dish.name;await nutritionClient.search(sourceQuery.value,selected.value[0]?.memberId)}
async function searchSources(){await nutritionClient.search(sourceQuery.value,selected.value[0]?.memberId)}
function chooseSource(row){const dish=dishes.value.find(d=>mealDishKey(d)===mapping.value);if(!dish)return;bindMealSource(dish,row);mapping.value='';queueNutrition()}
async function matchCandidates(){const mine=epoch,list=[...dishes.value],member=selected.value[0]?.memberId;for(const dish of list){if(!member||mine!==epoch||!dishes.value.includes(dish))return;if(dish.food_id||dish.recipe_version_id||dish.nutrition_source)continue;try{const rows=await nutritionClient.match(dish.name,member);if(mine!==epoch||captureLocked.value||saved.value||member!==selected.value[0]?.memberId||!dishes.value.includes(dish))return;const row=exactMealSource(dish.name,rows);if(row&&!dish.food_id&&!dish.recipe_version_id&&!dish.nutrition_source)bindMealSource(dish,row)}catch{}}if(mine===epoch)queueNutrition()}
function applyServings(dish){const count=Number(portionCount.value);if(!Number.isFinite(count)||count<=0||count>1000){error.value='请填写大于 0 且不超过 1000 的份数';return}Object.assign(dish,{servings:count,grams:null,portion_reference_id:null,portion_count:null,portion_source:'manual',portion_confirmed:true});adjusting.value='';error.value='';queueNutrition()}
function portionLabel(d){return (d.portion_source==='estimated'?'约 ':'')+(d.source_basis==='per_serving'?d.servings+' 份':d.portion_reference_id?d.portion_count+' '+d.portion_label:d.grams+' 克')}

async function openAdjustment(dish){adjusting.value=adjusting.value===mealDishKey(dish)?'':mealDishKey(dish);mapping.value='';gramInput.value=dish.grams??'';portionCount.value=String(dish.servings||dish.portion_count||1);if(adjusting.value)await nutritionClient.portions(dish)}
function applyWeight(dish){const value=Number(gramInput.value);if(!Number.isFinite(value)||value<=0||value>10000){error.value='请填写大于 0 且不超过 10000 克的实际份量';return}Object.assign(dish,{grams:value,portion_reference_id:null,portion_count:null,portion_source:'manual',portion_confirmed:true});error.value='';adjusting.value='';queueNutrition()}
function applyReference(dish,row){const count=Number(portionCount.value);if(!Number.isFinite(count)||count<=0||count>1000||count*Number(row.grams_per_unit)>10000){error.value='请填写有效份数，换算后总重量不能超过 10000 克';return}Object.assign(dish,{grams:null,portion_reference_id:row.id,portion_count:count,portion_label:row.unit_label,portion_source:'estimated',portion_confirmed:true});adjusting.value='';error.value='';queueNutrition()}
watch([dishes,people,captureScope,mealType,date,time,manualOpen],queueNutrition,{deep:true})
function store(){if(!capturePageActive()||handedOff||loading||entryBlocked.value||scope!==storageContext()||!members.value.length)return;scopedStorage.setStorageSync(uiKey(),{entryDay,people:people.value,dishes:dishes.value,captureScope:captureScope.value,mealType:mealType.value,date:date.value,time:time.value,oil:oil.value,photo:photo.value,source:source.value,saved:saved.value,origin:origin.value,manualDraft:manualOpen.value?manualText.value:null,supplement:supplement.value,editingRecord:editingRecord.value,extraPhotos:extraPhotos.value})}
watch([people,dishes,captureScope,mealType,date,time,oil,photo,source,saved,manualOpen,manualText,supplement,editingRecord,extraPhotos],store,{deep:true})
async function openPhotoClient(memberId,restore=false){
 const mine=epoch;photoPreparing.value=true
 try{photoPreparation=photoClient.open(memberId,members.value,{restore,history:false,day:entryDay});await photoPreparation}
 finally{if(mine===epoch)photoPreparing.value=false}
}
function capturePageActive(){
 // 小程序和 H5 都可能延迟派发旧页面的生命周期，交接后只允许栈顶编辑器恢复。
 const pages=typeof getCurrentPages==='function'?getCurrentPages():[],top=pages.at(-1)
 let activeRoute=top?.route||'',activeNavigation=top?.options?.captureNavigation
 // #ifdef H5
 if(typeof window!=='undefined'&&window.location.hash.startsWith('#/')){
  const [path,query='']=window.location.hash.slice(2).split('?');activeRoute=path
  activeNavigation=new URLSearchParams(query).get('captureNavigation')
 }
 // #endif
 return !activeRoute||!(props.embedded&&activeRoute==='pages/scan/index'||sourcePhoto&&(activeRoute!=='pages/scan/index'||activeNavigation!==props.route.captureNavigation))
}
function load(){
 if(!capturePageActive())return Promise.resolve()
 if(sourcePhoto&&photoContext!==storageContext()){hide();entryBlocked.value=true}
 if(entryBlocked.value){error.value='这次拍照的来源已失效，请返回菜品详情重新进入。';return Promise.resolve()}
 const today=currentMealContext().date
 if(scope&&(scope!==storageContext()||entryDay!==today))hide()
 if(loading)return preparation
 if(scope===storageContext()&&members.value.length&&vision.memberId)return Promise.resolve()
 handedOff=false
 const mine=++epoch,selection=photoVersion;scope=storageContext();const context=scope;entryDay=today
 loading=true;membersLoading.value=true;error.value=''
 preparation=(async()=>{try{
  const previous=saver.read()
  if(previous?.rows?.length&&previous.rows.every(row=>row.phase==='saved'))saver.finish()
  pendingGroup.value=saver.read()
  if((props.embedded||sourcePhoto)&&pendingGroup.value&&(pendingGroup.value.entryKey||'')!==entryKey.value){pendingGroup.value=null;entryBlocked.value=true;throw new Error('上一餐的保存结果尚待确认，请先继续上次记餐。')}
  if(!props.embedded&&!sourcePhoto&&pendingGroup.value?.entryKey)entryKey.value=pendingGroup.value.entryKey
  const cached=scopedStorage.getStorageSync(uiKey())
  // An uncertain save must be resolved with its original meal and request.
  let ui=cached&&(sourcePhoto||(cached.entryDay||cached.date)===today||pendingGroup.value||supplementSaver.read())?cached:null
  if(props.embedded&&ui?.supplement?.phase==='choose')ui={...ui,supplement:null}
  const frozen=!!supplementSaver.read()||pendingGroup.value&&!pendingGroup.value.editable
  if(ui&&!frozen&&((props.route.date&&ui.date!==initialContext.date)||(props.route.meal&&ui.mealType!==props.route.meal)||(props.route.memberId&&!(ui.people||[]).some(p=>p.selected&&p.memberId===props.route.memberId))))ui=null
  if(!ui){const current=currentMealContext();date.value=routeDate&&initialContext.date===routeDate?routeDate:current.date;mealType.value=Object.hasOwn(mealLabels,props.route.meal)?props.route.meal:current.meal}
  if(ui){busy.value=!!ui.saved;people.value=ui.people||[];dishes.value=ui.dishes||[];captureScope.value=ui.captureScope;mealType.value=ui.mealType;date.value=ui.date;time.value=ui.time;oil.value=ui.oil;photo.value=ui.photo||'';source.value=ui.source;origin.value=ui.origin||null;supplement.value=ui.supplement||null;editingRecord.value=ui.editingRecord||null;extraPhotos.value=ui.extraPhotos||[]
   if(typeof ui.manualDraft==='string'&&!ui.saved&&(!pendingGroup.value||pendingGroup.value.editable)){manualText.value=ui.manualDraft;manualOpen.value=true}
   if((ui.entryDay||ui.date)!==today)notice.value='正在核对之前一餐的保存结果。'
  }
  const {data}=await request({path:'/api/health/v1/members'})
  if(mine!==epoch||context!==storageContext())return
  members.value=data.filter(m=>m.scopes?.includes('diet_edit'));membersLoading.value=false
  if(props.route.memberId&&!members.value.some(m=>m.id===props.route.memberId)){members.value=[];people.value=[];throw new Error('所选成员当前没有记餐权限，请返回重新选择。')}
  const allowed=new Set(members.value.map(m=>m.id))
  if(ui&&((ui.people||[]).some(p=>p.selected&&!allowed.has(p.memberId))||(ui.origin&&!allowed.has(ui.origin.memberId))||(ui.editingRecord&&!allowed.has(ui.editingRecord.row.memberId))||(ui.saved?.rows||[]).some(r=>!allowed.has(r.memberId)))){
   scopedStorage.setStorageSync(uiKey(),null);hide();notice.value='部分成员授权已变化，请重新核对。';return
  }
  people.value=members.value.map((m,i)=>({selected:props.route.memberId?m.id===props.route.memberId:i===0,dishes:[],portion:'不确定',grams:'',noneConfirmed:false,...(ui?people.value.find(p=>p.memberId===m.id):null),memberId:m.id,name:m.display_name||m.name||m.relationship_label}))
  if(!members.value.length){error.value='暂无可记餐成员，请检查成员授权。';return}
  if(ui?.saved){busy.value=true;const rows=await Promise.all(ui.saved.rows.map(async row=>({...row,record:await readDietRecord(row.memberId,row.recordId||row.record?.id,request)})));if(mine!==epoch||context!==storageContext())return;saved.value={...ui.saved,rows};busy.value=false}
  if(props.embedded&&!ui&&!pendingGroup.value){dishes.value=JSON.parse(JSON.stringify(props.entry?.dishes||[]));source.value='菜品详情';people.value.forEach(p=>{p.dishes=p.selected?dishes.value.map(d=>d.name):[]})}
  if(props.route.commerce==='1'&&props.route.id&&!pendingGroup.value&&!ui){const order=await commerce.cooking(props.route.id);if(mine!==epoch||context!==storageContext())return;if(selection===photoVersion&&!manualOpen.value&&!hasDishes.value){dishes.value=order.meal_snapshot.dishes.map(d=>({name:d.recipe_name}));source.value='订单菜谱选菜';notice.value='订单菜谱仅供选菜，请逐人确认实际吃过的菜，未自动记为已吃。'}}
  const first=selected.value[0]||people.value[0]
  const resumePhotos=!!(ui?.origin||ui?.photo||ui?.supplement?.phase==='upload')
  await openPhotoClient(first.memberId,resumePhotos&&selection===photoVersion)
  if(mine!==epoch||context!==storageContext())return
  const pendingMeal=vision.pending&&(vision.meal||vision.pending.request?.data)
  if(pendingMeal?.eaten_at){date.value=mealDay(pendingMeal.eaten_at);time.value=new Date(Date.parse(pendingMeal.eaten_at)+8*3600000).toISOString().slice(11,16);mealType.value=pendingMeal.meal_type;notice.value='之前的照片请求尚待确认，请先核对原任务。'}
  if(selection===photoVersion&&vision.meal&&(!hasDishes.value||supplement.value?.phase==='upload'))useCandidates()
  if(hasDishes.value&&source.value!=='当天食谱选菜'&&captureScope.value==='单人餐盘'&&!saved.value&&(!pendingGroup.value||pendingGroup.value.editable))selected.value.forEach(p=>{p.dishes=dishes.value.map(d=>d.name);p.noneConfirmed=false})
  pollResult();queueNutrition()
 }catch(e){if(mine===epoch){error.value=e.message;busy.value=false}}finally{if(mine===epoch){loading=false;membersLoading.value=false;photoPreparing.value=false;store()}}})()
 return preparation
}
function hide(){
 if(opening)return
 clearTimeout(pollTimer);clearTimeout(nutritionTimer);nutritionClient.invalidate()
 epoch++;loading=false;store();saver.hide();supplementSaver.hide();photoClient.discard()
 scope='';members.value=[];people.value=[];dishes.value=[];photo.value='';saved.value=null;pendingGroup.value=null
 supplement.value=null;editingRecord.value=null;extraPhotos.value=[];origin.value=null
 adjusting.value='';mapping.value='';familyOpen.value=false;photoOpen.value=false
 captureScope.value='单人餐盘';oil.value='不确定';source.value='手动填写';notice.value='';error.value=''
 busy.value=false;membersLoading.value=false;photoPreparing.value=false;localPhotoPending.value=false;photoVersion++
 const current=currentMealContext();entryDay=current.date;date.value=current.date;time.value=current.time
 mealType.value=mealKeys.includes(props.route.meal)?props.route.meal:current.meal
 vision.consent=null;editing.value=false;portionDraft.value=[];portionError.value='';cancelManual();menuNotice.value=''
}
onMounted(()=>{void load()});onShow(()=>{void load()});onHide(hide);onUnload(()=>{opening=false;hide()});onUnmounted(()=>{opening=false;hide()})
function togglePerson(p){if(props.embedded||sourcePhoto){toggleRecordPerson(p);return}if(captureLocked.value||photoPreparing.value||editingRecord.value)return;if(captureScope.value==='单人餐盘')people.value.forEach(x=>x.selected=x===p);else p.selected=!p.selected;const first=people.value.find(p=>p.selected);if(first&&first.memberId!==vision.memberId){if(captureScope.value==='单人餐盘'){photo.value='';dishes.value=[];origin.value=null}void openPhotoClient(first.memberId)}}
function toggleRecordPerson(person){
 if(captureLocked.value||photoPreparing.value||editingRecord.value)return
 const previous=selected.value[0]?.memberId
 person.selected=!person.selected
 if(person.selected&&!person.dishes.length){person.dishes=dishes.value.map(d=>d.name);person.noneConfirmed=false}
 captureScope.value=selected.value.length>1?'家庭共享桌菜':'单人餐盘'
 const first=selected.value[0]
 if(first&&first.memberId!==previous){dishes.value.forEach(d=>d.portion_confirmed=false);void openPhotoClient(first.memberId)}
}
function viewRecords(){uni.navigateTo({url:'/pages/records/index?date='+encodeURIComponent(date.value)})}
const isBusy=computed(()=>busy.value||vision.busy||localPhotoPending.value||membersLoading.value)
function handleBack(){
 if(isBusy.value)return true
 if(supplement.value){void cancelSupplement();return true}
 if(editing.value){editing.value=false;return true}
 if(manualOpen.value){cancelManual();return true}
 if(adjusting.value||mapping.value){adjusting.value='';mapping.value='';return true}
 return false
}
function setScope(value){if(captureLocked.value||editingRecord.value)return;captureScope.value=value;if(value==='单人餐盘'){const first=selected.value[0]||people.value[0];people.value.forEach(p=>p.selected=p===first)}}
function toggleDish(p,name){if(sourcePhoto)p.grams='';p.dishes=p.dishes.includes(name)?p.dishes.filter(n=>n!==name):[...p.dishes,name];p.noneConfirmed=false}
function openPortions(){if(manualOpen.value||saved.value||(pendingGroup.value&&!pendingGroup.value.editable))return;portionDraft.value=JSON.parse(JSON.stringify(selected.value));portionError.value='';editing.value=true}
function applyPortions(){if(portionDraft.value.some(p=>!p.noneConfirmed&&!p.dishes.length)){portionError.value='请为每位成员选择实际吃过的菜，或确认本餐未吃';return}for(const row of portionDraft.value){const target=people.value.find(p=>p.memberId===row.memberId);if(target)Object.assign(target,row)}editing.value=false}
function manual(){
 if(captureLocked.value)return
 manualText.value=dishes.value.map(d=>d.name).join('\n');manualError.value='';manualOpen.value=true
}
function cancelManual(){manualOpen.value=false;manualText.value='';manualError.value=''}
function applyManual(){
 if(scope!==storageContext()){hide();void load();return}
 if(!manualOpen.value||locked.value||saved.value)return
 const names=[...new Set(manualText.value.split(/[、，,\r\n]+/).map(name=>name.trim()).filter(Boolean))]
 if(!names.length){manualError.value='请至少填写一道菜';return}
 if(names.length>30){manualError.value='一餐最多填写30道菜，请合并或删减后重试';return}
 if(names.some(name=>[...name].length>120)){manualError.value='单个菜名最多120字，可用换行或顿号分隔多道菜';return}
 const previous=[...dishes.value]
 dishes.value=names.flatMap(name=>previous.some(d=>d.name===name)?previous.filter(d=>d.name===name):[{name}])
 people.value.forEach(person=>{
   const retained=person.dishes.filter(name=>names.includes(name))
   // A weight confirmed for several dishes must not migrate to the remaining dish.
   if(retained.length!==person.dishes.length){person.grams='';person.portion='不确定'}
   person.dishes=retained
 })
 source.value=origin.value&&source.value==='照片识别后核对'?'照片识别后核对':'手动填写'
 menuNotice.value='';uni.hideKeyboard?.();cancelManual();if(captureScope.value==='单人餐盘'){selected.value.forEach(p=>{p.dishes=names;p.noneConfirmed=false})}else openPortions()
}
async function fromMenu(){
 if(captureLocked.value)return
 const mine=epoch,context=storageContext(),family=getSession()?.householdId,day=date.value,type=mealType.value
 const current=()=>mine===epoch&&context===storageContext()&&family===getSession()?.householdId&&day===date.value&&type===mealType.value
 busy.value=true;error.value='';menuNotice.value=''
 try{
  if(type==='snack'){menuNotice.value='今日餐单暂不包含加餐，请手动填写实际吃过的食物。';return}
  if(!family)throw new Error('请先选择当前家庭。')
  await preparation
  if(!current()||!members.value.length||saved.value||manualOpen.value||hasDishes.value||vision.pending||supplement.value||pendingGroup.value&&!pendingGroup.value.editable)return
  const plan=await readDailyMealPlan(family,day,request,{fresh:true})
  if(!current())return
  const result=captureMenuDishes(plan,type);menuNotice.value=result.notice
  if(!result.dishes.length)return
  dishes.value=result.dishes;source.value='当天食谱选菜';origin.value=null;photo.value=''
  people.value.forEach(p=>{p.dishes=[];p.grams='';p.portion='不确定';p.noneConfirmed=false})
  openPortions()
 }catch(e){if(current())error.value=e.message}
 finally{if(mine===epoch)busy.value=false}
}
function chooseImage(which){
 if(locked.value||saved.value||manualOpen.value)return
 if(!loading&&(!members.value.length||!vision.memberId))void load()
 opening=true;const context=storageContext(),mine=epoch,adding=!!supplement.value
 uni.chooseImage({count:1,sizeType:['compressed'],sourceType:[which],success:async r=>{
  if(mine!==epoch||context!==storageContext()||!r.tempFilePaths?.[0])return
  const version=++photoVersion
  localPhotoPending.value=true
  menuNotice.value=''
  if(adding){supplement.value={phase:'upload',photo:r.tempFilePaths[0],candidates:[],text:''}}
  else {photo.value=r.tempFilePaths[0];origin.value=null;dishes.value=[];saved.value=null;source.value='照片待识别';notice.value='';people.value.forEach(p=>{p.dishes=[];p.grams='';p.noneConfirmed=false;p.portion='不确定'})}
  try{
   await preparation;await photoPreparation
   if(mine!==epoch||context!==storageContext()||version!==photoVersion)return
   if(!vision.memberId){error.value=error.value||'成员信息尚未就绪，照片已保留，可稍后重试。';return}
   if(!photoClient.resetSelection()){error.value='上一张照片任务尚未完成，请先处理当前任务。';return}
   await photoClient.addPhoto(r.tempFilePaths[0])
   if(mine!==epoch||context!==storageContext()||version!==photoVersion)return
   localPhotoPending.value=false
   if(vision.consent&&!vision.error)await analyze()
  }finally{if(mine===epoch&&version===photoVersion)localPhotoPending.value=false}
 },fail:e=>{if(!/cancel/i.test(e.errMsg||''))error.value='照片选择失败，请检查权限后重试'},complete:()=>opening=false})
}
function openPhotoPage(){
 if(isBusy.value||saved.value||manualOpen.value||editing.value||entryBlocked.value)return
 store()
 const ui=scopedStorage.getStorageSync(uiKey())
 if(!ui){error.value='记餐内容尚未准备好，请稍后重试。';return}
 // 写入交接草稿后冻结原页，navigateTo 的隐藏钩子不能再次覆盖。
 handedOff=true
 mealPhotoNavigation.open(props.entry,{...ui,supplement:ui.supplement||{phase:'choose',photo:'',candidates:[],text:''}},options=>uni.navigateTo({...options,fail:()=>{handedOff=false;error.value='拍照页未能打开，请重试。'}}))
}
async function beginSupplement(row=null){
 if(props.embedded&&!saved.value){openPhotoPage();return}
 if(locked.value||manualOpen.value||supplement.value)return
 if(saved.value){
  if(!row&&saved.value.rows.length>1){uni.showActionSheet({itemList:saved.value.rows.map(r=>(people.value.find(p=>p.memberId===r.memberId)?.name||'成员')+'的这一餐'),success:r=>void beginSupplement(saved.value.rows[r.tapIndex])});return}
  row ||= saved.value.rows[0]
  const mine=epoch,context=storageContext();busy.value=true;error.value=''
  try{
   const record=await readDietRecord(row.memberId,row.recordId||row.record.id)
   if(mine!==epoch||context!==storageContext())return
   editingRecord.value={row:{...row,record,recordId:record.id},group:JSON.parse(JSON.stringify(saved.value))}
   saver.finish();pendingGroup.value=null;saved.value=null;origin.value=null
   captureScope.value='单人餐盘';people.value.forEach(p=>{p.selected=p.memberId===row.memberId;p.dishes=[]})
   const original=record.snapshot.meal;mealType.value=original.meal_type;date.value=mealDay(original.eaten_at);time.value=new Date(Date.parse(original.eaten_at)+8*3600000).toISOString().slice(11,16)
   dishes.value=original.items.filter(i=>!i.excluded).map(recognizedMealDish)
   selected.value.forEach(p=>{p.dishes=dishes.value.map(d=>d.name);p.noneConfirmed=false})
   await openPhotoClient(row.memberId)
   if(mine!==epoch||context!==storageContext())return
  }catch(e){if(mine===epoch)error.value=e.message;return}finally{if(mine===epoch)busy.value=false}
 }
 if(vision.pending)return
 supplement.value={phase:'choose',photo:'',candidates:[],text:''};error.value='';notice.value=''
}
async function cancelSupplement(){
 if(busy.value||vision.busy||vision.pending)return
 const mine=epoch
 if(vision.job&&['pending','running'].includes(vision.job.execution_status)){await photoClient.cancel();if(mine!==epoch||vision.error)return}
 photoClient.resetSelection();supplement.value=null;error.value='';store()
}
function switchSupplementToManual(){
 if(locked.value||!supplement.value||!photoClient.resetSelection())return
 supplement.value={phase:'manual',photo:'',candidates:[],text:''};error.value='';store()
}
function prepareManualSupplement(){
 const names=[...new Set((supplement.value?.text||'').split(/[、，,\r\n]+/).map(n=>n.trim()).filter(Boolean))]
 if(!names.length||names.some(n=>[...n].length>120)||names.length>30){error.value='请填写菜名，多道食物可换行，每个菜名不超过120字';return}
 supplement.value.candidates=supplementCandidates(dishes.value,names.map(name=>({name,portion_source:'unknown'})));supplement.value.phase='review';error.value=''
}
function matchCarriedDish(candidate){
 if(locked.value||!sourcePhoto||!dishes.value.length)return
 const target=dishes.value.find(d=>photoEntry.dishes.some(original=>original.name===d.name))
 if(!target)return
 for(const row of supplement.value.candidates)if(row!==candidate&&row.matchKey===mealDishKey(target)){row.matchKey=null;row.choice=row.duplicate?'':'add'}
 candidate.matchKey=mealDishKey(target);candidate.choice='same'
}
function removeCarriedDish(){
 if(locked.value||!sourcePhoto)return
 const names=photoEntry.dishes.map(d=>d.name)
 dishes.value=dishes.value.filter(d=>!names.includes(d.name))
 people.value.forEach(p=>{if(p.dishes.some(n=>names.includes(n))){p.dishes=p.dishes.filter(n=>!names.includes(n));p.grams='';p.portion='不确定'}})
 for(const row of supplement.value.candidates){row.matchKey=null;row.choice='add';row.duplicate=false}
}
function joinSupplement(){
 if(!supplement.value||supplement.value.phase!=='review'||locked.value)return
 try{
  let existing=dishes.value
  if(sourcePhoto&&supplement.value.photo&&vision.draft&&vision.meal){
   existing=dishes.value.map(old=>{
    const match=supplement.value.candidates.find(row=>row.choice==='same'&&(row.matchKey===mealDishKey(old)||row.dish.name.trim().replace(/\s/g,'')===old.name.trim().replace(/\s/g,'')))
    if(!match)return old
    return {...old,name:match.dish.name,item_id:match.dish.item_id,photo_estimate:match.dish.photo_estimate,visible_ingredients:match.dish.visible_ingredients,uncertainties:match.dish.uncertainties,locations:match.dish.locations}
   })
  }
  const merged=appendMealCandidates(existing,supplement.value.candidates)
  // 原来单道菜的本人克数不能变成新增多道菜后的合计重量。
  if(sourcePhoto&&captureScope.value==='单人餐盘'&&merged.length>1){
   const person=selected.value[0]
   if(person?.dishes.length===1&&Number(person.grams)>0){
    const index=dishes.value.findIndex(d=>d.name===person.dishes[0]),dish=merged[index]
    if(dish&&dish.source_basis!=='per_serving')Object.assign(dish,{grams:Number(person.grams),portion_source:'manual',portion_confirmed:true})
    person.grams=''
   }
  }
  if(sourcePhoto&&supplement.value.photo&&vision.draft&&vision.meal){
   people.value.forEach(p=>{p.dishes=p.dishes.map(name=>{const index=dishes.value.findIndex(d=>d.name===name);return index<0?name:existing[index].name})})
   origin.value={memberId:vision.memberId,draft:JSON.parse(JSON.stringify(vision.draft)),meal:JSON.parse(JSON.stringify(vision.meal))};source.value='照片识别后核对'
   photo.value=supplement.value.photo
  }
  if(supplement.value.photo&&merged.length>dishes.value.length)extraPhotos.value.push(supplement.value.photo)
  dishes.value=merged
  if(captureScope.value==='单人餐盘')selected.value.forEach(p=>{p.dishes=dishes.value.map(d=>d.name);p.noneConfirmed=false})
  supplement.value=null;error.value='';notice.value='已加入这一餐，请核对后统一保存。';photoClient.resetSelection();store();queueNutrition();void matchCandidates()
  if(captureScope.value==='家庭共享桌菜')openPortions()
 }catch(e){error.value=e.message}
}
async function cancelMealEdit(){
 if(locked.value||supplement.value||!editingRecord.value)return
 const mine=epoch,edit=editingRecord.value;busy.value=true
 try{
  const record=await readDietRecord(edit.row.memberId,edit.row.record.id)
  if(mine!==epoch)return
  saved.value={...edit.group,rows:edit.group.rows.map(r=>r.memberId===edit.row.memberId?{...edit.row,record}:r)}
  dishes.value=record.snapshot.meal.items.filter(i=>!i.excluded).map(recognizedMealDish);editingRecord.value=null;error.value='';store()
 }catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch)busy.value=false}
}
async function reestimate(){
 if(captureLocked.value||!origin.value?.meal?.photos?.length)return
 if(vision.job&&(!['success','failed','cancelled'].includes(vision.job.execution_status)||vision.job.execution_status==='success'&&vision.job.result_id!==origin.value.draft.id)){const mine=epoch,context=storageContext();await job(vision.job.task_id);if(mine===epoch&&context===storageContext())pollResult();return}
 vision.uploads=origin.value.meal.photos.map(p=>({upload_id:p.upload_id}));await analyze()
}
async function analyze(){if(locked.value||saved.value||manualOpen.value)return;const mine=epoch,context=storageContext();await photoClient.start(mealType.value,`${date.value}T${time.value}:00+08:00`);if(mine!==epoch||context!==storageContext())return;if(!supplement.value&&vision.job&&['pending','running'].includes(vision.job.execution_status)){dishes.value=[];origin.value=null;notice.value=''}useCandidates();pollResult()}
function useCandidates(){if(manualOpen.value||saved.value||!vision.meal||!vision.draft)return;if(supplement.value){if(supplement.value.phase==='upload'){supplement.value.candidates=supplementCandidates(dishes.value,vision.meal.items.filter(i=>!i.excluded).map(recognizedMealDish));supplement.value.phase='review';store()}return;}if(origin.value?.draft?.id===vision.draft.id&&origin.value?.draft?.version===vision.draft.version&&hasDishes.value)return;origin.value={memberId:vision.memberId,draft:JSON.parse(JSON.stringify(vision.draft)),meal:JSON.parse(JSON.stringify(vision.meal))};dishes.value=vision.meal.items.filter(i=>!i.excluded).map(recognizedMealDish);source.value='照片识别后核对';if(captureScope.value==='单人餐盘')selected.value.forEach(p=>{p.dishes=dishes.value.map(d=>d.name);p.noneConfirmed=false});else people.value.forEach(p=>{p.dishes=[];p.grams='';p.noneConfirmed=false;p.portion='不确定'});notice.value=captureScope.value==='家庭共享桌菜'?'已更新菜品，请重新核对每个人吃过的菜和份量。':'';queueNutrition();void matchCandidates()}
async function job(id){if(locked.value||saved.value||manualOpen.value)return;const mine=epoch,context=storageContext();await photoClient.job(id);if(mine===epoch&&context===storageContext())useCandidates()}
function savedMeal(person){
 if((props.embedded||sourcePhoto)&&String(person.grams??'').trim()&&(!Number.isFinite(Number(person.grams))||Number(person.grams)<=0||Number(person.grams)>10000))throw new Error('请填写大于 0 且不超过 10000 克的实际份量，或留空。')
 const candidates=(props.embedded||sourcePhoto)&&person.dishes.length===1&&Number(person.grams)>0?dishes.value.map(d=>({...d,portion_confirmed:false})):dishes.value
 const meal=personalMeal(candidates,person,{mealType:mealType.value,eatenAt:`${date.value}T${time.value}:00+08:00`,captureScope:captureScope.value,oil:oil.value})
 if(editingRecord.value){const original=editingRecord.value.row.record.snapshot.meal;return {memberId:person.memberId,meal:preserveMealEvidence({...meal,meal_type:original.meal_type,eaten_at:original.eaten_at},original)}}
 if(source.value==='照片识别后核对'&&origin.value?.draft?.id&&origin.value.memberId===person.memberId){
   return {memberId:person.memberId,meal:preserveMealEvidence(meal,origin.value.meal),draftId:origin.value.draft.id,draftVersion:origin.value.draft.version}
 }
 if(source.value==='照片识别后核对'&&origin.value?.draft?.id)meal.items.forEach(item=>item.uncertainties.push('家庭桌菜候选经本人逐项核对；本成员未关联照片原图'))
 return {
  memberId:person.memberId,meal,
 }
}
async function save(chat=false){if(editingRecord.value){await saveSupplementedMeal();return}if(scope!==storageContext()){hide();void load();return}if(manualOpen.value||busy.value||((!saver.read()||saver.read().editable)&&!canSave.value))return;if((!saver.read()||saver.read().editable)&&incomplete.value&&!acceptMissing.value){error.value='部分营养或份量尚未补齐，请先补充，或明确选择仅保存已知内容';return}const mine=epoch,context=storageContext();busy.value=true;error.value='';try{let meals=[];if(!saver.read()||saver.read().editable)meals=selected.value.filter(p=>!p.noneConfirmed&&p.dishes.length).map(savedMeal);const group=await saver.save(meals,acceptMissing.value);if(mine!==epoch||context!==storageContext()||!group)return;saved.value=group;notice.value=`已保存${group.rows.length}位成员的实际记录。`;if(chat)chatWithSaved()}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch){pendingGroup.value=saver.read();busy.value=false}}}
async function saveSupplementedMeal(){
 if(scope!==storageContext()||busy.value||vision.busy||supplement.value||manualOpen.value)return
 if(!supplementSaver.read()&&(!canSave.value||incomplete.value&&!acceptMissing.value))return
 const mine=epoch,edit=editingRecord.value;busy.value=true;error.value=''
 try{
  const row=await supplementSaver.save(edit.row,savedMeal(selected.value[0]).meal,acceptMissing.value)
  if(mine!==epoch||!row)return
  saved.value={...edit.group,rows:edit.group.rows.map(old=>old.memberId===row.memberId?row:old)}
  editingRecord.value=null;notice.value='已补充到原来的这一餐。';store()
 }catch(e){if(mine===epoch)error.value=Number(e.code)===409?'本餐已在别处修改，当前补充尚未保存。可取消本次修改，读取最新记录后再补充。':e.message}
 finally{if(mine===epoch)busy.value=false}
}
async function recheckRejected(){
 const mine=epoch,context=storageContext(),group=saver.releaseRejected();if(!group)return
 pendingGroup.value=group;error.value='';notice.value='请重新核对未保存成员；已保存成员不会重复记录。'
 if(origin.value){const owner=origin.value.memberId,id=origin.value.draft.id;await openPhotoClient(owner);if(mine!==epoch||context!==storageContext())return;await photoClient.draft(id);if(mine!==epoch||context!==storageContext())return;if(vision.draft?.id===id&&vision.draft.review_status==='pending_confirmation')useCandidates();else{origin.value=null;source.value='手动填写';notice.value='原照片候选已不可继续，请核对当前菜品后人工保存未保存成员。'}}
 openPortions()
}
function chatWithSaved(){const rows=saved.value?.rows||[];if(!rows.length)return;const go=row=>uni.navigateTo({url:feedbackUrl(row.memberId,row.record)});if(rows.length===1)go(rows[0]);else uni.showActionSheet({itemList:rows.map(r=>(people.value.find(p=>p.memberId===r.memberId)?.name||'成员')+'的这一餐'),success:r=>go(rows[r.tapIndex])})}
function newMeal(){
 if(!saved.value||busy.value)return
 entryKey.value=props.entry?.key||''
 supplement.value=null;editingRecord.value=null;extraPhotos.value=[];nutritionClient.invalidate()
 adjusting.value='';mapping.value='';acceptMissing.value=false;photoOpen.value=false;cancelManual();menuNotice.value=''
 saver.finish();photoClient.discard();photoVersion++
 const current=currentMealContext();entryDay=current.date;date.value=current.date;time.value=current.time
 mealType.value=mealKeys.includes(props.route.meal)?props.route.meal:current.meal
 pendingGroup.value=null;saved.value=null;origin.value=null;source.value='手动填写';dishes.value=[];photo.value=''
 if(props.embedded){dishes.value=JSON.parse(JSON.stringify(props.entry?.dishes||[]));source.value='菜品详情'}
 people.value.forEach(p=>{p.dishes=props.embedded&&p.selected?dishes.value.map(d=>d.name):[];p.portion='不确定';p.grams='';p.noneConfirmed=false})
 const first=selected.value[0];if(first)void openPhotoClient(first.memberId)
 store()
}

 return {matchCarriedDish,removeCarriedDish,sourcePhoto,expectedDishes,entryKey,entryBlocked,uiKey,currentMealContext,initialContext,routeDate,members,people,dishes,captureScope,mealType,date,time,oil,photo,error,notice,busy,editing,source,saved,pendingGroup,membersLoading,photoPreparing,localPhotoPending,supplement,editingRecord,extraPhotos,supplementSaver,vision,photoClient,saver,nutrition,nutritionClient,adjusting,mapping,sourceQuery,gramInput,portionCount,acceptMissing,familyOpen,photoOpen,nutritionRows,preview,previewReady,incomplete,nutrients,consent,origin,portionDraft,portionError,manualOpen,manualText,manualError,menuNotice,mealKeys,portions,oils,locked,selected,hasDishes,captureLocked,canSave,epoch,opening,scope,loading,preparation,photoPreparation,entryDay,photoVersion,pollTimer,nutritionTimer,queueNutrition,refreshNutrition,amount,dishEnergy,pollResult,authorizeAndAnalyze,openMapping,searchSources,chooseSource,matchCandidates,applyServings,portionLabel,openAdjustment,applyWeight,applyReference,store,openPhotoClient,load,hide,togglePerson,toggleRecordPerson,viewRecords,isBusy,handleBack,setScope,toggleDish,openPortions,applyPortions,manual,cancelManual,applyManual,fromMenu,chooseImage,beginSupplement,cancelSupplement,switchSupplementToManual,prepareManualSupplement,joinSupplement,cancelMealEdit,reestimate,analyze,useCandidates,job,savedMeal,save,saveSupplementedMeal,recheckRejected,chatWithSaved,newMeal}
}
