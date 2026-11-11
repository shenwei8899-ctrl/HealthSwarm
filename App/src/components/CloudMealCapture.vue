<script setup>
import { computed,reactive,ref,watch,onMounted } from 'vue'
import { onShow,onHide,onUnload } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'
import { createMealNutritionClient,mealNutritionState,recognizedMealDish,bindMealSource,exactMealSource } from '../services/meal-nutrition.js'
import { supplementCandidates,appendMealCandidates,preserveMealEvidence,createMealSupplementSaver,mealDishKey } from '../services/meal-supplement.js'
import { request } from '../services/request.js'
import { scopedStorage,storageContext } from '../services/storage.js'
import { createMealPhotoClient,photoState,mealPhotoFailure,mealPhotoUploadMessage } from '../services/meal-photo-client.js'
import { createCloudMealSaver,personalMeal,mealLabels,mealDay,feedbackUrl,readDietRecord } from '../services/cloud-meals.js'
import { commerce } from '../services/commerce.js'
import { getSession } from '../services/session.js'
const props=defineProps({route:{type:Object,default:()=>({})}})
function currentMealContext(){const local=new Date(Date.now()+8*3600000).toISOString(),hour=Number(local.slice(11,13));return {date:local.slice(0,10),time:local.slice(11,16),meal:hour<10?'breakfast':hour<15?'lunch':hour<21?'dinner':'snack'}}
const initialContext=currentMealContext()
const members=ref([]),people=ref([]),dishes=ref([]),captureScope=ref('单人餐盘'),mealType=ref(Object.hasOwn(mealLabels,props.route.meal)?props.route.meal:initialContext.meal),date=ref(initialContext.date),time=ref(initialContext.time),oil=ref('不确定'),photo=ref(''),error=ref(''),notice=ref(''),busy=ref(false),editing=ref(false),source=ref('手动填写'),saved=ref(null),pendingGroup=ref(null)
const membersLoading=ref(false),photoPreparing=ref(false),localPhotoPending=ref(false)
const supplement=ref(null),editingRecord=ref(null),extraPhotos=ref([]),supplementSaver=createMealSupplementSaver()
const vision=reactive(photoState()),photoClient=createMealPhotoClient({state:vision}),saver=createCloudMealSaver()
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
const locked=computed(()=>busy.value||(vision.busy&&!photoPreparing.value)||localPhotoPending.value||!!vision.pending||!!supplementSaver.read()||(!!pendingGroup.value&&!pendingGroup.value.editable&&!saved.value)),selected=computed(()=>people.value.filter(p=>p.selected)),hasDishes=computed(()=>dishes.value.length>0)
const captureLocked=computed(()=>locked.value||!!saved.value||manualOpen.value||!!supplement.value)
const canSave=computed(()=>!manualOpen.value&&!supplement.value&&selected.value.length&&selected.value.every(p=>p.noneConfirmed||p.dishes.length)&&selected.value.some(p=>!p.noneConfirmed&&p.dishes.length))
let epoch=0,opening=false,scope='',loading=false,preparation=null,photoPreparation=null,entryDay=initialContext.date,photoVersion=0,pollTimer=null,nutritionTimer=null
function queueNutrition(){clearTimeout(nutritionTimer);nutritionClient.invalidate();acceptMissing.value=false;if(!hasDishes.value||manualOpen.value||saved.value)return;const mine=epoch;nutritionTimer=setTimeout(()=>{if(mine===epoch)void refreshNutrition()},350)}
async function refreshNutrition(){if(saved.value||manualOpen.value)return;const meals=selected.value.filter(p=>!p.noneConfirmed&&p.dishes.length).map(savedMeal);if(meals.length)await nutritionClient.preview(meals)}
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
function store(){if(loading||scope!==storageContext()||!members.value.length)return;scopedStorage.setStorageSync('cloud-capture-ui',{entryDay,people:people.value,dishes:dishes.value,captureScope:captureScope.value,mealType:mealType.value,date:date.value,time:time.value,oil:oil.value,photo:photo.value,source:source.value,saved:saved.value,origin:origin.value,manualDraft:manualOpen.value?manualText.value:null,supplement:supplement.value,editingRecord:editingRecord.value,extraPhotos:extraPhotos.value})}
watch([people,dishes,captureScope,mealType,date,time,oil,photo,source,saved,manualOpen,manualText,supplement,editingRecord,extraPhotos],store,{deep:true})
async function openPhotoClient(memberId,restore=false){
 const mine=epoch;photoPreparing.value=true
 try{photoPreparation=photoClient.open(memberId,members.value,{restore,history:false,day:entryDay});await photoPreparation}
 finally{if(mine===epoch)photoPreparing.value=false}
}
function load(){
 const today=currentMealContext().date
 if(scope&&(scope!==storageContext()||entryDay!==today))hide()
 if(loading)return preparation
 if(scope===storageContext()&&members.value.length&&vision.memberId)return Promise.resolve()
 const mine=++epoch,selection=photoVersion;scope=storageContext();const context=scope;entryDay=today
 loading=true;membersLoading.value=true;error.value=''
 preparation=(async()=>{try{
  const previous=saver.read()
  if(previous?.rows?.length&&previous.rows.every(row=>row.phase==='saved'))saver.finish()
  pendingGroup.value=saver.read()
  const cached=scopedStorage.getStorageSync('cloud-capture-ui')
  // An uncertain save must be resolved with its original meal and request.
  let ui=cached&&((cached.entryDay||cached.date)===today||pendingGroup.value||supplementSaver.read())?cached:null
  if(ui){busy.value=!!ui.saved;people.value=ui.people||[];dishes.value=ui.dishes||[];captureScope.value=ui.captureScope;mealType.value=ui.mealType;date.value=ui.date;time.value=ui.time;oil.value=ui.oil;photo.value=ui.photo||'';source.value=ui.source;origin.value=ui.origin||null;supplement.value=ui.supplement||null;editingRecord.value=ui.editingRecord||null;extraPhotos.value=ui.extraPhotos||[]
   if(typeof ui.manualDraft==='string'&&!ui.saved&&(!pendingGroup.value||pendingGroup.value.editable)){manualText.value=ui.manualDraft;manualOpen.value=true}
   if((ui.entryDay||ui.date)!==today)notice.value='正在核对之前一餐的保存结果。'
  }
  const {data}=await request({path:'/api/health/v1/members'})
  if(mine!==epoch||context!==storageContext())return
  members.value=data.filter(m=>m.scopes?.includes('diet_edit'));membersLoading.value=false
  const allowed=new Set(members.value.map(m=>m.id))
  if(ui&&((ui.people||[]).some(p=>p.selected&&!allowed.has(p.memberId))||(ui.origin&&!allowed.has(ui.origin.memberId))||(ui.editingRecord&&!allowed.has(ui.editingRecord.row.memberId))||(ui.saved?.rows||[]).some(r=>!allowed.has(r.memberId)))){
   scopedStorage.setStorageSync('cloud-capture-ui',null);hide();notice.value='部分成员授权已变化，请重新核对。';return
  }
  people.value=members.value.map((m,i)=>({selected:i===0,dishes:[],portion:'不确定',grams:'',noneConfirmed:false,...people.value.find(p=>p.memberId===m.id),memberId:m.id,name:m.display_name||m.name||m.relationship_label}))
  if(!members.value.length){error.value='暂无可记餐成员，请检查成员授权。';return}
  if(ui?.saved){busy.value=true;const rows=await Promise.all(ui.saved.rows.map(async row=>({...row,record:await readDietRecord(row.memberId,row.recordId||row.record?.id,request)})));if(mine!==epoch||context!==storageContext())return;saved.value={...ui.saved,rows};busy.value=false}
  if(props.route.commerce==='1'&&props.route.id&&!pendingGroup.value&&!ui){const order=await commerce.cooking(props.route.id);if(mine!==epoch||context!==storageContext())return;if(selection===photoVersion&&!manualOpen.value&&!hasDishes.value){dishes.value=order.meal_snapshot.dishes.map(d=>({name:d.recipe_name}));source.value='订单菜谱选菜';notice.value='订单菜谱仅供选菜，请逐人确认实际吃过的菜，未自动记为已吃。'}}
  const first=selected.value[0]||people.value[0]
  const resumePhotos=!!(ui?.origin||ui?.photo||ui?.supplement?.phase==='upload')
  await openPhotoClient(first.memberId,resumePhotos&&selection===photoVersion)
  if(mine!==epoch||context!==storageContext())return
  const pendingMeal=vision.pending&&(vision.meal||vision.pending.request?.data)
  if(pendingMeal?.eaten_at){date.value=mealDay(pendingMeal.eaten_at);time.value=new Date(Date.parse(pendingMeal.eaten_at)+8*3600000).toISOString().slice(11,16);mealType.value=pendingMeal.meal_type;notice.value='之前的照片请求尚待确认，请先核对原任务。'}
  if(selection===photoVersion&&vision.meal&&(!hasDishes.value||supplement.value?.phase==='upload'))useCandidates()
  if(hasDishes.value&&captureScope.value==='单人餐盘'&&!saved.value&&(!pendingGroup.value||pendingGroup.value.editable))selected.value.forEach(p=>{p.dishes=dishes.value.map(d=>d.name);p.noneConfirmed=false})
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
onMounted(()=>{void load()});onShow(()=>{void load()});onHide(hide);onUnload(()=>{opening=false;hide()})
function togglePerson(p){if(captureLocked.value||photoPreparing.value||editingRecord.value)return;if(captureScope.value==='单人餐盘')people.value.forEach(x=>x.selected=x===p);else p.selected=!p.selected;const first=people.value.find(p=>p.selected);if(first&&first.memberId!==vision.memberId){if(captureScope.value==='单人餐盘'){photo.value='';dishes.value=[];origin.value=null}void openPhotoClient(first.memberId)}}
function setScope(value){if(captureLocked.value||editingRecord.value)return;captureScope.value=value;if(value==='单人餐盘'){const first=selected.value[0]||people.value[0];people.value.forEach(p=>p.selected=p===first)}}
function toggleDish(p,name){p.dishes=p.dishes.includes(name)?p.dishes.filter(n=>n!==name):[...p.dishes,name];p.noneConfirmed=false}
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
async function fromMenu(){if(captureLocked.value)return;const mine=epoch,context=storageContext();busy.value=true;error.value='';menuNotice.value='';try{const {data}=await request({path:'/api/family/'+encodeURIComponent(getSession()?.householdId)+'/daily-arrangements/'+date.value});if(mine!==epoch||context!==storageContext())return;const arrangement=data.arrangement||data;const m=arrangement.meals?.find(m=>(m.type||m.meal_type)===mealType.value);if(!m?.dishes?.length){menuNotice.value='还没有本餐食谱，可以直接填写吃过的菜。';return}dishes.value=m.dishes.map(d=>({name:d.name}));source.value='当天食谱选菜';if(captureScope.value==='单人餐盘')selected.value.forEach(p=>{p.dishes=dishes.value.map(d=>d.name);p.noneConfirmed=false});else openPortions()}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch)busy.value=false}}
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
async function beginSupplement(row=null){
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
function joinSupplement(){
 if(!supplement.value||supplement.value.phase!=='review'||locked.value)return
 try{
  const merged=appendMealCandidates(dishes.value,supplement.value.candidates)
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
 const meal=personalMeal(dishes.value,person,{mealType:mealType.value,eatenAt:`${date.value}T${time.value}:00+08:00`,captureScope:captureScope.value,oil:oil.value})
 if(editingRecord.value){const original=editingRecord.value.row.record.snapshot.meal;return {memberId:person.memberId,meal:preserveMealEvidence({...meal,meal_type:original.meal_type,eaten_at:original.eaten_at},original)}}
 if(source.value==='照片识别后核对'&&origin.value?.draft?.id&&origin.value.memberId===person.memberId){
   return {memberId:person.memberId,meal:preserveMealEvidence(meal,origin.value.meal),draftId:origin.value.draft.id,draftVersion:origin.value.draft.version}
 }
 if(source.value==='照片识别后核对'&&origin.value?.draft?.id)meal.items.forEach(item=>item.uncertainties.push('家庭桌菜候选经本人逐项核对；本成员未关联照片原图'))
 return {memberId:person.memberId,meal}
}
async function save(chat=false){if(editingRecord.value){await saveSupplementedMeal();return}if(scope!==storageContext()){hide();void load();return}if(manualOpen.value||busy.value||((!saver.read()||saver.read().editable)&&!canSave.value))return;if(incomplete.value&&!acceptMissing.value){error.value='部分营养或份量尚未补齐，请先补充，或明确选择仅保存已知内容';return}const mine=epoch,context=storageContext();busy.value=true;error.value='';try{let meals=[];if(!saver.read()||saver.read().editable)meals=selected.value.filter(p=>!p.noneConfirmed&&p.dishes.length).map(savedMeal);const group=await saver.save(meals,acceptMissing.value);if(mine!==epoch||context!==storageContext()||!group)return;saved.value=group;notice.value=`已保存${group.rows.length}位成员的实际记录。`;if(chat)chatWithSaved()}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch){pendingGroup.value=saver.read();busy.value=false}}}
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
 supplement.value=null;editingRecord.value=null;extraPhotos.value=[];nutritionClient.invalidate()
 adjusting.value='';mapping.value='';acceptMissing.value=false;photoOpen.value=false;cancelManual();menuNotice.value=''
 saver.finish();photoClient.discard();photoVersion++
 const current=currentMealContext();entryDay=current.date;date.value=current.date;time.value=current.time
 mealType.value=mealKeys.includes(props.route.meal)?props.route.meal:current.meal
 pendingGroup.value=null;saved.value=null;origin.value=null;source.value='手动填写';dishes.value=[];photo.value=''
 people.value.forEach(p=>{p.dishes=[];p.portion='不确定';p.grams='';p.noneConfirmed=false})
 const first=selected.value[0];if(first)void openPhotoClient(first.memberId)
 store()
}
</script>
<template>
 <view class="screen scan-screen">
  <view class="capture-fixed-header"><AppNavBar title="拍照记餐"><template #left><button class="icon-button" aria-label="返回" @click="uni.navigateBack()">‹</button></template></AppNavBar></view>
  <view class="capture-page-wash" aria-hidden="true"/>
  <view class="meal-context"><text>{{selected.map(p=>p.name).join('、')||'选择记录成员'}}</text><view class="context-time"><picker :range="mealKeys.map(k=>mealLabels[k])" :disabled="captureLocked||!!editingRecord" @change="mealType=mealKeys[$event.detail.value]"><view>{{mealLabels[mealType]}}⌄</view></picker><picker mode="date" :value="date" :disabled="captureLocked||!!editingRecord" @change="date=$event.detail.value"><view>{{date.slice(5).replace('-','月')}}日</view></picker><picker mode="time" :value="time" :disabled="captureLocked||!!editingRecord" @change="time=$event.detail.value"><view>{{time}}⌄</view></picker></view></view>
  <view v-if="people.length>1" class="member-picks"><button v-for="p in people" :key="p.memberId" :class="{active:p.selected}" :disabled="captureLocked" @click="togglePerson(p)">{{p.name}}</button></view>
  <text v-if="membersLoading||photoPreparing||localPhotoPending" class="capture-loading" role="status">{{localPhotoPending?'照片已选择，正在准备识别…':membersLoading?'正在准备成员信息…':'正在准备照片识别…'}}</text>
  <text v-if="error||vision.error" class="inline-error" role="alert">{{error||vision.error}}</text><text v-if="notice" class="capture-notice" role="status">{{notice}}</text><button v-if="!members.length&&!membersLoading&&error" class="secondary-button" :disabled="busy" @click="load">重新读取成员</button>
  <view v-if="saved" class="saved-receipt"><text class="saved-check">✓</text><view><text class="saved-title">这一餐已记录</text><text class="saved-caption">{{selected.map(p=>p.name).join('、')}} · {{mealLabels[mealType]}}，已保存到饮食记录</text></view></view>
  <view v-if="hasDishes&&!manualOpen" class="nutrition-card">
   <view class="section-heading"><text class="summary-label">本餐热量</text><text class="recognition-badge">{{source==='照片识别后核对'?'已识别':'已填写'}} {{dishes.length}} 道食物</text></view>
   <template v-if="nutritionRows.length<=1"><view class="energy-line"><text class="energy-value" :class="{unavailable:!previewReady||preview?.totals?.energy_kcal==null}">{{nutrition.busy?'计算中':previewReady&&preview.totals.energy_kcal!=null?amount('energy_kcal'):'待补齐'}}</text><text v-if="previewReady&&preview.totals.energy_kcal!=null" class="energy-unit">千卡</text><text v-if="previewReady&&preview.estimated" class="estimate-tag">估算</text></view><text class="nutrition-caption">{{previewReady&&preview.totals.energy_kcal!=null?'按当前份量计算，请核对实际吃下的分量。':'请匹配营养数据并核对份量，缺失项目不按 0 计算。'}}</text><view class="macro-grid"><view v-for="n in nutrients" :key="n[0]"><text class="macro-label">{{n[1]}}</text><view><text class="macro-number">{{amount(n[0])}}</text><text class="macro-unit">克</text></view></view></view></template>
   <view v-else class="member-nutrition"><view v-for="row in nutritionRows" :key="row.member_id"><text>{{people.find(p=>p.memberId===row.member_id)?.name}}</text><text>{{row.estimated&&row.totals.energy_kcal!=null?'约 ':''}}{{row.totals.energy_kcal??'待补齐'}} {{row.totals.energy_kcal!=null?'千卡':''}}</text></view><text class="nutrition-caption">家庭成员分别计算，不将整桌菜算作每人的摄入。</text></view>
  </view>
  <view v-if="!hasDishes&&!manualOpen" class="capture-card upload-card">
   <template v-if="vision.job&&['pending','running'].includes(vision.job.execution_status)"><view class="recognition-spinner"/><text class="upload-title">正在看这餐吃了什么</text><text class="capture-card-caption">识别完成后，结果会直接显示在这里。</text><button class="text-link" :disabled="vision.busy" @click="photoClient.cancel()">取消识别</button></template>
   <template v-else><view v-if="photo" class="photo-preview"><image :src="photo" mode="aspectFill"/></view><view v-else class="photo-placeholder"><view class="capture-camera-tile" aria-hidden="true"><AppIcon name="camera" :size="52"/></view><text class="upload-title">这一餐，拍照记下来</text><text class="capture-photo-caption">拍清楚食物，识别后核对实际份量</text></view><view class="photo-actions"><button class="capture-primary" :disabled="captureLocked" @click="chooseImage('camera')"><AppIcon name="camera" :size="36"/>{{photo?'重新拍照':'拍照'}}</button><button class="capture-secondary" :disabled="captureLocked" @click="chooseImage('album')">从相册选择</button></view><view class="other-methods"><button :disabled="captureLocked" @click="fromMenu">从今日食谱选择 ›</button><text>｜</text><button :disabled="captureLocked" @click="manual">手动填写 ›</button></view></template>
  </view>
  <view v-if="!supplement&&vision.uploads.length&&(!hasDishes||source==='照片识别后核对')" class="consent-card">
   <template v-if="vision.config?.meal?.available"><template v-if="!consent"><text class="consent-kicker">首次使用 · 云识别授权</text><text class="consent-title">用照片，帮你记下这一餐</text><text class="consent-copy">同意后，你之后提交用于记餐的照片将交由{{vision.config.meal.processor?.startsWith('alibaba-cn:')?'阿里云百炼':'当前已审核的云识别服务'}}处理，以识别食物并辅助记餐。</text><text class="consent-copy muted">授权持续有效，无需每餐重复确认。你可在本页撤回授权；处理方或政策变化时会重新征求同意。</text><button class="primary-button" :disabled="captureLocked" @click="authorizeAndAnalyze">授权并开始识别</button><button class="text-link" :disabled="captureLocked" @click="manual">暂不授权，手动记餐</button></template><template v-else><text class="consent-copy">已授权云识别，无需重复确认。</text><button class="primary-button" :disabled="captureLocked" @click="analyze">开始识别</button></template></template><text v-else class="safe-note">{{vision.config?.meal?.reason||'照片识别暂不可用，可手动填写菜品。'}}</text>
  </view>
  <view v-if="!supplement&&vision.job&&['failed','cancelled'].includes(vision.job.execution_status)" class="card recognition-card"><text>{{mealPhotoFailure(vision.job.error_code)}}</text><button :disabled="captureLocked" @click="photoClient.retryJob().then(pollResult)">重新尝试识别</button></view>
  <button v-if="vision.pending" class="secondary-button" :disabled="vision.busy" @click="photoClient.retryPending().then(()=>{useCandidates();pollResult()})">恢复原照片任务</button>
  <view v-if="vision.drafts.length&&!hasDishes&&!photo" class="card recognition-card"><text>继续核对之前的照片</text><button v-for="d in vision.drafts.filter(d=>d.review_status!=='confirmed')" :key="d.id" :disabled="captureLocked" @click="photoClient.draft(d.id).then(useCandidates)">{{d.payload?.items?.map(i=>i.name).join('、')||'未核对菜品'}} ›</button></view>
  <text v-if="menuNotice" class="menu-notice" role="status">{{menuNotice}}</text>
  <view v-if="manualOpen" class="manual-card"><view class="section-heading"><text>这一餐吃了什么</text><text class="manual-caption">手动填写</text></view><text class="manual-help">多道菜可换行或用顿号分隔。</text><textarea v-model="manualText" class="manual-input" aria-label="本餐菜品" placeholder="例如：杂粮饭、清蒸鱼、炒西兰花" :maxlength="4000" auto-height :focus="manualOpen" :cursor-spacing="100" :adjust-position="true" :disabled="locked" @input="manualError=''"/><text v-if="manualError" class="manual-error" role="alert">{{manualError}}</text><view class="manual-actions"><button class="manual-cancel" :disabled="locked" @click="cancelManual">取消</button><button class="manual-confirm" :disabled="locked||!manualText.trim()" @click="applyManual">确认菜品</button></view></view>
  <view v-else-if="hasDishes" class="dish-list-card"><view class="section-heading"><text class="dish-list-title">这一餐吃了什么</text><button v-if="!saved" :disabled="captureLocked" @click="manual">修改菜品 ›</button></view>
   <view v-for="d in dishes" :key="d.item_id||d.name" class="nutrition-dish">
    <view class="dish-overview">
     <view class="dish-identity">
      <text class="dish-name">{{d.name}}</text>
      <button v-if="!saved" class="source-link" :disabled="captureLocked" @click="openMapping(d)"><text>{{d.food_id||d.recipe_version_id||d.nutrition_source?'已匹配 · '+(d.source_name||d.name):d.photo_estimate?'营养参考 · 可调整':'匹配营养数据'}}</text><text class="dish-chevron" aria-hidden="true">›</text></button>
      <text v-else class="source-link source-receipt">{{d.food_id||d.recipe_version_id||d.nutrition_source?'已匹配营养来源':d.photo_estimate?'营养参考':'营养数据待补齐'}}</text>
     </view>
     <view v-if="captureScope==='单人餐盘'" class="dish-metrics">
      <view class="dish-energy"><text class="dish-kcal">{{dishEnergy(d)}}</text><text class="dish-unit">千卡</text></view>
      <button v-if="!saved" class="portion-button" :disabled="captureLocked" :aria-label="d.name+'，'+(d.portion_confirmed?portionLabel(d):'核对份量')" @click="openAdjustment(d)"><text>{{d.portion_confirmed?portionLabel(d):'核对份量'}}</text><view class="portion-chevron" aria-hidden="true"/></button>
      <text v-else class="portion-receipt">{{d.portion_confirmed?portionLabel(d):'份量待补齐'}}</text>
     </view>
    </view>
    <view v-if="mapping===mealDishKey(d)" class="dish-editor"><view class="source-search"><input v-model="sourceQuery" class="field-input" aria-label="搜索营养数据" maxlength="120" placeholder="搜索食品或菜谱"/><button :disabled="nutrition.sourceBusy" @click="searchSources">搜索</button></view><text v-if="nutrition.sourceBusy" class="small">正在检索…</text><button v-for="row in nutrition.sources" :key="row.type+row.id" class="source-choice" :disabled="nutrition.sourceBusy" @click="chooseSource(row)"><text>{{row.name}} · {{row.cooking_state}}</text><text>{{row.type==='food'?'食品':row.type==='recipe'?'菜谱':'现有资料'}} · {{row.basis_label||'每100克'}}</text></button><text v-if="!nutrition.sourceBusy&&!nutrition.sourceError&&!nutrition.sources.length" class="editor-note">暂无计量基准明确的匹配营养资料。可以先保留菜品记录，数据补齐后再计算。</text><text v-if="nutrition.sourceError" class="inline-error">{{nutrition.sourceError}}</text><button class="text-link" @click="mapping=''">收起</button></view>
    <view v-if="adjusting===mealDishKey(d)" class="dish-editor"><template v-if="d.source_basis==='per_serving'"><text class="editor-note">原文每份：{{d.basis_label||'按所选资料'}}。请按这个基准填写本人吃下的份数。</text><view class="weight-input"><input v-model="portionCount" type="digit" aria-label="原文份数" placeholder="实际份数"/><text>份</text><button :disabled="captureLocked" @click="applyServings(d)">更新份量</button></view></template><template v-else><text class="editor-note">填写本人实际吃下的可食重量。</text><view class="weight-input"><input v-model="gramInput" type="digit" aria-label="实际可食重量" placeholder="实际克数"/><text>克</text><button :disabled="captureLocked" @click="applyWeight(d)">更新份量</button></view><text v-if="nutrition.portionError" class="inline-error">{{nutrition.portionError}}</text><template v-if="nutrition.portions.length"><text class="editor-note">也可采用已发布参考份量，结果标为估算。</text><input v-model="portionCount" type="digit" class="field-input" aria-label="参考份数" placeholder="份数"/><button v-for="row in nutrition.portions" :key="row.id" class="source-choice" @click="applyReference(d,row)">{{row.unit_label}} · 每份 {{row.grams_per_unit}} 克</button></template></template><button class="text-link" @click="adjusting=''">收起</button></view>
   </view>
   <button v-if="!supplement" class="supplement-entry" :disabled="locked||manualOpen" @click="beginSupplement()"><text class="supplement-plus">＋</text>补充本餐</button>
  </view>
  <view v-if="supplement" class="manual-card supplement-card">
   <view class="section-heading"><text class="field-title">补充本餐</text><button class="text-link" :disabled="busy||vision.busy||!!vision.pending" @click="cancelSupplement">取消</button></view>
   <text class="manual-help">原有食物会保留，新食物核对后再加入。</text>
   <template v-if="supplement.phase==='choose'"><view class="photo-actions"><button class="capture-primary" :disabled="locked" @click="chooseImage('camera')"><AppIcon name="camera" :size="32"/>拍照</button><button class="capture-secondary" :disabled="locked" @click="chooseImage('album')">从相册选择</button></view><button class="text-link supplement-manual" :disabled="locked" @click="supplement.phase='manual'">手动填写 ›</button></template>
   <template v-else-if="supplement.phase==='manual'"><textarea v-model="supplement.text" class="manual-input" placeholder="例如：米饭、炒西兰花" aria-label="补充的食物" :maxlength="4000" auto-height/><button class="primary-button supplement-confirm" :disabled="locked||!supplement.text.trim()" @click="prepareManualSupplement">核对食物</button></template>
   <template v-else-if="supplement.phase==='upload'"><image v-if="supplement.photo" class="supplement-photo" :src="supplement.photo" mode="aspectFill"/><text class="manual-help" :class="{'inline-error':!!vision.error}" role="status">{{mealPhotoUploadMessage(vision)}}</text><text v-if="!vision.consent&&!vision.job" class="consent-copy">同意后，提交用于记餐的照片将交由当前已审核的云识别服务处理。授权持续有效，可在本页撤回。</text><button v-if="!vision.job&&!vision.busy" class="primary-button supplement-confirm" :disabled="!!vision.pending||!vision.uploads.length" @click="vision.consent?analyze():authorizeAndAnalyze()">{{vision.consent?(vision.error?'重试识别':'识别这张照片'):'同意照片识别并继续'}}</button><button v-if="vision.error||vision.job&&['failed','cancelled'].includes(vision.job.execution_status)" class="text-link" :disabled="locked" @click="chooseImage('album')">重新选择照片</button><button v-if="vision.error||vision.job&&['failed','cancelled'].includes(vision.job.execution_status)" class="text-link" :disabled="locked" @click="switchSupplementToManual">改为手动补充</button><button v-if="vision.job&&!['pending','running','failed','cancelled'].includes(vision.job.execution_status)" class="text-link" :disabled="locked" @click="job(vision.job.task_id)">读取本次识别结果</button></template>
   <template v-else-if="supplement.phase==='review'">
    <text class="supplement-review-note">本次识别的食物 · 尚未计入本餐</text>
    <view v-for="(candidate,index) in supplement.candidates" :key="candidate.dish.item_id||index" class="supplement-item">
     <view class="dish-topline"><text class="dish-name">{{candidate.dish.name}}</text><button v-if="!candidate.duplicate" class="text-link" @click="candidate.choice=candidate.choice==='skip'?'add':'skip'">{{candidate.choice==='skip'?'加入':'不添加'}}</button></view>
     <template v-if="candidate.duplicate"><text class="duplicate-note">这一餐已有同名食物，这次是？</text><view class="duplicate-choices"><button :class="{active:candidate.choice==='same'}" @click="candidate.choice='same'">同一份，不再添加</button><button :class="{active:candidate.choice==='extra'}" @click="candidate.choice='extra'">又吃了一份</button></view></template>
     <view v-if="candidate.choice!=='same'&&candidate.choice!=='skip'" class="supplement-weight"><text>本人吃下</text><input v-model="candidate.amount" type="digit" :aria-label="candidate.dish.name+'补充份量'" placeholder="待核对"/><text>{{candidate.dish.source_basis==='per_serving'?'份':'克'}}</text></view>
    </view>
    <text v-if="!supplement.candidates.length" class="manual-help">这张照片没有可加入的食物，可取消后手动填写。</text>
    <button class="primary-button supplement-confirm" :disabled="locked||!supplement.candidates.length" @click="joinSupplement">加入这一餐</button>
   </template>
  </view>
  <button v-if="editingRecord&&!supplement" class="text-link cancel-meal-edit" :disabled="locked" @click="cancelMealEdit">取消本次修改</button>
  <text v-if="nutrition.error" class="inline-error" role="alert">{{nutrition.error}}</text><button v-if="nutrition.error&&canSave&&!saved" class="text-link" @click="refreshNutrition">重新计算营养</button>
  <text v-if="hasDishes&&!manualOpen" class="nutrition-footnote">{{incomplete?'部分营养或份量待补齐，缺失项保持未知。':'营养按所选来源与核对份量计算，实际烹饪仍可能存在差异。'}}</text>
  <view v-if="hasDishes&&!saved&&!manualOpen" class="secondary-actions"><button v-if="photo||extraPhotos.length" @click="photoOpen=!photoOpen">{{photoOpen?'收起原图':'核对原图'}}</button><button :disabled="captureLocked" @click="familyOpen=!familyOpen">多人一起吃？ 分别记录 ›</button></view><view v-if="photoOpen&&(photo||extraPhotos.length)" class="original-photo"><image v-if="photo" :src="photo" mode="widthFix"/><image v-for="(path,index) in extraPhotos" :key="index" :src="path" mode="widthFix"/></view>
  <view v-if="familyOpen&&!saved" class="family-settings"><text class="field-title">就餐方式</text><view class="scope-grid"><button v-for="s in ['单人餐盘','家庭共享桌菜']" :key="s" :class="{active:captureScope===s}" :disabled="captureLocked" @click="setScope(s)">{{s}}</button></view></view>
  <view v-if="hasDishes&&captureScope==='家庭共享桌菜'&&!saved" class="people-card"><text class="field-title">分别核对每位成员的摄入</text><view v-for="p in selected" :key="p.memberId" class="person-row"><view class="person-heading"><text class="person-name">{{p.name}}</text><view class="portion-choices"><button v-for="n in portions" :key="n" :class="{active:p.portion===n&&!p.noneConfirmed}" :disabled="captureLocked||p.noneConfirmed||!p.dishes.length" @click="p.portion=n">{{n}}</button></view></view><button class="person-dishes" :disabled="captureLocked" @click="openPortions"><text>{{p.noneConfirmed?'未吃这些菜':p.dishes.join(' · ')||'选择实际吃过的菜'}}</text><text>核对 ›</text></button></view></view>
  <button v-if="!saved&&origin?.meal?.photos?.length&&dishes.some(d=>!d.food_id&&!d.recipe_version_id&&!d.nutrition_source&&!d.photo_estimate)" class="text-link" :disabled="captureLocked" @click="reestimate">重新识别并补充营养</button>
  <view v-if="hasDishes&&!saved&&!manualOpen&&incomplete" class="incomplete-consent"><button class="incomplete-toggle" role="checkbox" :aria-checked="acceptMissing" :disabled="busy||nutrition.busy" @click="acceptMissing=!acceptMissing"><view class="missing-check" :class="{checked:acceptMissing}" aria-hidden="true">{{acceptMissing?'✓':''}}</view><text>仅保存已知内容，缺失营养保持未知</text></button></view>
  <view v-if="pendingGroup&&!saved" class="card recognition-card"><text v-for="r in pendingGroup.rows.filter(r=>r.phase==='saved')" :key="r.memberId">{{people.find(p=>p.memberId===r.memberId)?.name}}已保存</text><button v-if="pendingGroup.rows.some(r=>r.phase==='rejected')&&!pendingGroup.editable" :disabled="busy" @click="recheckRejected">重新核对未保存成员</button></view>
  <view v-if="saved" class="secondary-actions"><button @click="uni.navigateTo({url:'/pages/records/index'})">查看饮食记录 ›</button><button :disabled="busy" @click="newMeal">记录新的一餐</button></view>
  <view v-if="hasDishes&&!manualOpen" class="save-actions"><text class="save-hint">{{supplement?'还有食物待核对，加入后再保存':saved?'已保存，咨询由你主动发起':incomplete?'缺失营养不计入热量合计':'请按实际吃下的份量核对'}}</text><button v-if="!saved" class="save-primary" :disabled="!!supplement||busy||(vision.busy&&!photoPreparing)||nutrition.busy||(!supplementSaver.read()&&((!saver.read()||saver.read().editable)&&!canSave||incomplete&&!acceptMissing))" @click="save()">{{busy?'正在保存…':editingRecord?(supplementSaver.read()?'恢复原保存请求':'保存本餐修改'):saver.read()&&!saver.read().editable?'恢复原保存请求':incomplete?'保存已知内容':'确认并记录这一餐'}}</button><button v-else class="save-primary" @click="chatWithSaved">问问营养师</button></view>
  <view class="privacy-actions"><button v-if="consent&&!vision.pending" :disabled="captureLocked" @click="photoClient.revokeConsent()">撤回照片云识别授权</button><button v-if="!hasDishes" :disabled="captureLocked" @click="photoClient.refreshConfiguration()">检查识别服务</button></view>
  <view v-if="editing" class="portion-mask" @touchmove.stop.prevent @click="editing=false"><view class="portion-dialog" @click.stop><view class="dialog-header"><text>核对本人吃过的菜和份量</text><button aria-label="关闭份量调整" @click="editing=false">×</button></view><scroll-view class="dialog-body" scroll-y :style="{height:Math.min(680,180+portionDraft.length*360)+'rpx'}" @touchmove.stop><view v-for="p in portionDraft" :key="p.memberId" class="person-adjustment"><view class="adjustment-heading"><text>{{p.name}}</text><button class="not-eaten" :class="{active:p.noneConfirmed}" :disabled="busy" @click="p.noneConfirmed=true;p.dishes=[]">本餐未吃</button></view><view class="dish-picks"><button v-for="d in dishes" :key="d.item_id||d.name" :class="{active:p.dishes.includes(d.name)}" :disabled="busy" @click="toggleDish(p,d.name)">{{d.name}}</button></view><template v-if="!p.noneConfirmed"><view class="portion-choices dialog-portions"><button v-for="n in portions" :key="n" :class="{active:p.portion===n}" :disabled="busy" @click="p.portion=n">{{n}}</button></view><input v-model="p.grams" type="digit" class="field-input" :disabled="busy" placeholder="本人所选菜品合计克数（选填）"/></template></view></scroll-view><view class="dialog-footer"><text v-if="portionError" class="inline-error">{{portionError}}</text><view class="dialog-actions"><button class="secondary-button" @click="editing=false">取消</button><button class="primary-button" @click="applyPortions">确认</button></view></view></view></view>
 </view>
</template>


<style scoped>
.supplement-entry{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;min-height:46px;margin:16px 0 2px;padding:10px 16px;border:0;border-radius:16px;background:var(--ui-soft);color:var(--ui-text);font-size:13px;font-weight:500}.supplement-plus{font-size:19px;font-weight:400;line-height:20px;color:var(--ui-muted)}.supplement-card{margin-top:0}.supplement-manual{display:block;margin:8px auto 0}.supplement-photo{width:100%;height:145px;border-radius:12px}.supplement-review-note{display:block;font-size:11px;color:#95869f;margin:8px 0}.supplement-item{padding:12px 0;border-bottom:1px solid #eae4ef}.supplement-weight{display:flex;align-items:center;gap:10px;margin-top:8px;font-size:12px;color:#8d8198}.supplement-weight input{width:80px;height:36px;background:white;border:1px solid #e2dce9;border-radius:8px;padding:0 8px;text-align:right;color:#383340}.duplicate-note{display:block;font-size:12px;color:#9b7959;margin:10px 0}.duplicate-choices{display:flex;gap:7px}.duplicate-choices button{flex:1;padding:9px 4px;border:1px solid #ded5e6;border-radius:9px;font-size:11px;background:white;color:#8e7e9c}.duplicate-choices button.active{background:#eee6f5;border-color:#c6b4d8;color:#75558d}.supplement-confirm{margin-top:15px;font-size:14px}.cancel-meal-edit{margin:0 auto 12px}

.nav-spacer{width:80rpx}.scan-screen{position:relative;z-index:0;padding-left:18px;padding-right:18px;background:var(--ui-canvas);color:var(--ui-text)}
.capture-page-wash{position:fixed;z-index:-1;top:0;left:0;right:0;height:360px;pointer-events:none;background-image:radial-gradient(ellipse at 0% 0%,rgba(125,174,255,.65),rgba(125,174,255,0) 72%),radial-gradient(ellipse at 100% 0%,rgba(206,178,245,.55),rgba(206,178,245,0) 75%)}
.capture-card{min-width:0;border:1px solid rgba(255,255,255,.94);border-radius:28px;background:linear-gradient(165deg,rgba(255,255,255,.92),#fff 48%);box-shadow:inset 0 1px 0 #fff,0 8px 28px rgba(75,69,107,.035)}
.section-heading,.person-heading,.adjustment-heading,.dialog-header{display:flex;align-items:center;justify-content:space-between;gap:8px}.field-title{display:block;font-size:15px;font-weight:600}.section-heading button{min-height:40px}.small,.text-link{font-size:12px;color:var(--ui-muted)}
.manual-card{margin:4px 0 20px;padding:16px;border:1px solid #e5dfed;border-radius:18px;background:#f9f8fc}.manual-caption{flex:none;font-size:11px;color:var(--ui-muted)}.manual-help{display:block;margin:8px 0 12px;font-size:12px;line-height:1.7;color:var(--ui-muted)}.manual-input{display:block;width:100%;min-height:136px;padding:12px;border:1px solid #e6e1ec;border-radius:12px;background:#fff;color:var(--ui-text);font-size:14px;line-height:28px}.manual-input:focus{border-color:#9784ad}.manual-error{display:block;margin-top:10px;color:#a33b35;font-size:12px;line-height:1.6}.manual-actions{display:flex;gap:10px;margin-top:14px}.manual-actions button{flex:1;min-width:0;min-height:44px;padding:8px;border-radius:12px;font-size:13px;line-height:1.5}.manual-cancel{border:1px solid #e2dce9;background:#fff;color:var(--ui-muted)}.manual-confirm{background:var(--ui-accent);color:#fff}.menu-notice{display:block;margin:0 0 14px;font-size:12px;line-height:1.7;color:var(--ui-muted)}
.photo-preview{overflow:hidden;border-radius:18px}.photo-placeholder{display:flex;flex-direction:column;align-items:center;justify-content:center}.photo-actions{display:flex;gap:9px}.photo-actions button{flex:1;display:flex;align-items:center;justify-content:center;gap:7px;min-height:48px;padding:8px;border-radius:999px}.capture-primary{background:#333440;color:#fff}.capture-secondary{background:#fff;border:1px solid #e5e0ed;color:#756a82}.other-methods{display:flex;align-items:center;justify-content:center;gap:8px;margin-top:14px;font-size:11px;color:#a69aaf}.other-methods button{min-height:40px;padding:6px 0;color:#8f7d9e;font-size:11px}.capture-card-caption,.capture-photo-caption{color:#9c90a8}.capture-camera-tile{display:flex;align-items:center;justify-content:center}
.scope-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.scope-grid button,.member-picks button{min-height:40px;padding:8px 12px;border:1px solid #e8e3ee;background:#fff;border-radius:12px;font-size:12px;color:#8e7e9c}.scope-grid button.active,.member-picks button.active{border-color:#c9bada;background:#f0eaf7;color:#806492}.member-picks{display:flex;flex-wrap:wrap;gap:7px}
.person-row,.person-adjustment{padding:10px 0;border-bottom:1px solid #eeedf4}.person-heading{justify-content:flex-start;flex-wrap:wrap}.person-name{font-size:13px;max-width:90px;overflow-wrap:anywhere}.portion-choices{display:flex;flex:1;gap:4px;margin-left:auto;min-width:220px}.portion-choices button,.dish-picks button,.not-eaten{min-height:44px;padding:6px 8px;border:1px solid #e9e7ef;border-radius:8px;background:#f8f8fb;color:var(--ui-muted);font-size:12px;line-height:1.5}.portion-choices button{flex:1;white-space:nowrap}.portion-choices button.active,.dish-picks button.active,.not-eaten.active{background:#eee6f5;border-color:#cebedc;color:#806393}.person-dishes{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;min-height:44px;text-align:left;font-size:12px;line-height:1.6;color:var(--ui-muted)}.person-dishes>text:first-child{flex:1;min-width:0;overflow-wrap:anywhere}.person-dishes>text:last-child{flex:none}
.recognition-card{display:flex;flex-direction:column;gap:10px;padding:16px;margin:14px 0;line-height:1.65}.text-link{min-height:40px}.save-actions{position:fixed;z-index:20;left:0;right:0;bottom:0;display:flex;box-sizing:border-box;border-top:1px solid #eeedf4}.save-actions button{display:flex;align-items:center;justify-content:center;min-width:0;padding:8px 6px;line-height:1.4}
.portion-mask{position:fixed;inset:0;display:flex;align-items:flex-end;background:var(--ui-overlay)}.portion-dialog{display:flex;flex-direction:column;width:100%;max-height:90vh;overflow:hidden;border-radius:24px 24px 0 0;background:#fff}.dialog-header{flex:none;font-size:16px}.dialog-header button{min-width:44px;min-height:44px;font-size:22px;color:var(--ui-muted)}.dialog-body{max-height:58vh;min-height:0}.person-adjustment{margin:0 18px}.dish-picks{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.dialog-portions{margin:10px 0 6px}.dialog-footer{flex:none;padding:8px 18px calc(env(safe-area-inset-bottom) + 12px);border-top:1px solid #eeedf4}.dialog-actions{display:flex;gap:8px}.dialog-actions button{flex:1;min-width:0;font-size:14px}
@media(max-width:390px){.portion-choices{flex-basis:100%;margin-left:0;min-width:0}}
/* #ifdef H5 */
.save-actions,.portion-dialog{max-width:480px;margin-left:auto;margin-right:auto}
/* #endif */

/* The capture page owns its safe header; other AppNavBar consumers are unchanged. */
.scan-screen{min-height:100vh;overflow:visible;padding-top:0;padding-bottom:calc(env(safe-area-inset-bottom) + 150px)}
.capture-fixed-header{position:sticky;z-index:30;top:0;margin:0 -18px 12px;padding:0 18px;background:linear-gradient(110deg,#d5e5fc,#e7dcf5)}
.capture-loading{display:block;margin:0 3px 12px;font-size:11px;line-height:1.7;color:var(--ui-muted)}
.meal-context,.context-time{display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:12px;color:#77788e}.meal-context{margin:0 3px 18px}.context-time picker{min-height:36px;display:flex;align-items:center}.member-picks{margin-bottom:14px}
.meal-context>text{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.context-time{flex-shrink:0}
.nutrition-card,.dish-list-card,.consent-card,.family-settings{padding:21px 20px;border:1px solid rgba(255,255,255,.95);border-radius:24px;background:#fff;margin-bottom:14px;box-shadow:0 5px 22px rgba(70,62,95,.025)}
.summary-label{font-size:13px;font-weight:600}.recognition-badge{font-size:10px;color:#50816f;background:#f0f8f3;border-radius:20px;padding:4px 8px;font-weight:400}.energy-line{display:flex;align-items:baseline;gap:7px;margin:16px 0 5px}.energy-value{font-size:60px;line-height:1.1;font-weight:700;letter-spacing:-2px;color:#30313e}.energy-value.unavailable{font-size:33px;letter-spacing:0;line-height:1.5}.energy-unit{font-size:12px;color:#9192a0}.estimate-tag{align-self:center;margin-left:4px;padding:3px 5px;border-radius:5px;background:#f3eff9;color:#9987af;font-size:10px}.nutrition-caption{display:block;font-size:11px;line-height:1.8;color:#9694a4;margin:8px 0 17px}.macro-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;border-top:1px solid #efedf5;padding-top:16px}.macro-label{display:block;font-size:11px;color:#9290a0;margin-bottom:8px}.macro-label:before{content:'';display:inline-block;width:5px;height:5px;border-radius:50%;background:#ac92cc;margin-right:5px}.macro-grid>view:nth-child(2) .macro-label:before{background:#83a4c3}.macro-grid>view:nth-child(3) .macro-label:before{background:#caa47a}.macro-number{font-size:21px;font-weight:600;color:#353440}.macro-unit{font-size:10px;color:#9894a6;margin-left:4px}.member-nutrition>view{display:flex;justify-content:space-between;padding:14px 0;font-size:13px}
.dish-list-card{padding:12px 20px 18px;border-radius:20px;box-shadow:none}
.dish-list-card .section-heading{min-height:44px;margin-bottom:2px}.dish-list-title{font-size:16px;font-weight:600;line-height:1.5;color:var(--ui-text)}.dish-list-card .section-heading button{min-height:44px;padding:8px 0 8px 12px;color:var(--ui-muted);font-size:12px}
.nutrition-dish{padding:18px 0 14px;border-bottom:1px solid var(--ui-line)}
.dish-overview{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.dish-identity{flex:1;min-width:0}.dish-list-card .dish-name{display:block;min-width:0;overflow-wrap:anywhere;font-size:15px;font-weight:500;line-height:28px;color:var(--ui-text)}
.dish-topline{display:flex;align-items:center;justify-content:space-between;gap:9px}.dish-metrics{display:flex;flex-direction:column;align-items:flex-end;gap:6px;flex-shrink:0;max-width:50%}.dish-energy{display:flex;align-items:baseline;justify-content:flex-end;gap:4px;min-height:28px}.dish-kcal{font-size:20px;font-weight:500;line-height:28px;font-variant-numeric:tabular-nums;color:var(--ui-text)}.dish-unit{font-size:11px;color:var(--ui-muted)}
.dish-list-card .source-link{display:flex;align-items:center;justify-content:flex-start;gap:5px;width:100%;min-width:0;min-height:44px;margin:6px 0 0;padding:6px 0;text-align:left;font-size:12px;line-height:1.7;color:var(--ui-muted);overflow-wrap:anywhere}.source-link>text:first-child{min-width:0}.dish-chevron{flex-shrink:0;font-size:16px;color:#aaa6b4}.dish-list-card .source-receipt{padding-top:10px}
.portion-button{display:flex;align-items:center;justify-content:center;gap:9px;min-height:44px;max-width:100%;padding:8px 12px;border:0;border-radius:14px;background:var(--ui-soft);font-size:12px;line-height:1.6;color:var(--ui-text)}.portion-button>text{min-width:0;overflow-wrap:anywhere}.portion-chevron{flex-shrink:0;width:6px;height:6px;margin-top:-3px;border-right:1px solid #8e899b;border-bottom:1px solid #8e899b;transform:rotate(45deg)}.portion-receipt{display:block;min-height:44px;padding:10px 0;font-size:12px;line-height:1.7;color:var(--ui-muted)}
.dish-editor{margin-top:12px;background:#f8f6fc;border-radius:13px;padding:14px}.editor-note{display:block;font-size:11px;line-height:1.8;color:#92889f;margin-bottom:10px}.weight-input,.source-search{display:flex;align-items:center;gap:8px;font-size:12px}.weight-input input,.source-search input{min-width:0;flex:1;border:1px solid #e8e2ef;background:#fff;border-radius:9px;padding:10px;height:40px;box-sizing:border-box;font-size:12px}.weight-input button,.source-search button{flex:none;background:#7b698f;color:#fff;border-radius:10px;padding:10px 11px;font-size:11px;line-height:1.7}.source-choice{display:flex;flex-direction:column;gap:5px;width:100%;text-align:left;background:white;border:1px solid #e6e0ef;border-radius:10px;padding:12px;margin-top:9px;font-size:12px;line-height:1.7}.source-choice>text:last-child{font-size:10px;color:#9b93a6}.dish-editor .text-link{min-height:36px;padding:8px 0;font-size:11px;color:#92839e}.nutrition-footnote{display:block;margin:10px 4px;font-size:10px;line-height:1.9;color:#9993a5}.secondary-actions{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:6px 2px}.secondary-actions button{font-size:11px;min-height:42px;padding:8px 0;color:#8b7b9d;line-height:1.8}.original-photo{margin:10px 0 16px;overflow:hidden;border-radius:18px}.original-photo image{display:block;width:100%}
.upload-card{text-align:center;margin-top:0;padding:27px 20px 20px}.upload-title{display:block;font-size:20px;font-weight:600;line-height:1.7}.photo-placeholder{min-height:190px;gap:14px}.capture-photo-caption{font-size:12px}.capture-camera-tile{width:72px;height:72px;border-radius:24px;background:#f1ebfa;color:#9d83ba;margin-bottom:5px}.upload-card .photo-preview{height:190px;margin-bottom:15px}.upload-card .photo-preview image{height:100%;width:100%}.photo-actions{margin-top:14px;gap:9px}.photo-actions button{min-width:0;font-size:13px}.consent-kicker{display:block;font-size:10px;color:#aaa0b5;margin-bottom:10px}.consent-title{display:block;font-size:17px;font-weight:600;margin-bottom:13px}.consent-copy{display:block;font-size:12px;line-height:1.9;color:#8a8097;margin-bottom:14px}.consent-copy.muted{font-size:11px;color:#a095ab}.consent-card .primary-button{border-radius:24px;font-size:14px}.consent-card .text-link{font-size:11px;color:#9886a8;margin-top:6px}.recognition-spinner{width:46px;height:46px;margin:30px auto 25px;border:3px solid #ede4f5;border-top-color:#a68ac5;border-radius:50%;animation:capture-spin 1s linear infinite}.upload-card .capture-card-caption{display:block;line-height:1.9;margin:12px 0 23px}.recognition-card{font-size:12px}.saved-receipt{display:flex;align-items:center;gap:12px;padding:15px 16px;border-radius:18px;background:#ecf6ef;color:#4e7e65;margin-bottom:15px}.saved-check{display:flex;align-items:center;justify-content:center;width:29px;height:29px;border:1px solid #a8c5b3;border-radius:50%;font-size:15px}.saved-title{display:block;font-size:14px;font-weight:600}.saved-caption{display:block;font-size:10px;line-height:1.8;margin-top:5px}.incomplete-consent{margin:14px 2px}.incomplete-consent label{display:flex;align-items:center;gap:5px;font-size:11px;line-height:1.9;color:#9b8c79}.incomplete-consent checkbox{transform:scale(.72);flex:none}.save-actions{flex-direction:column;gap:8px;padding:10px 20px calc(env(safe-area-inset-bottom) + 16px);background:#fff}.save-actions .save-primary{width:100%;min-height:49px;flex:none;border-radius:30px;background:#333440;font-size:14px;font-weight:600;color:white;letter-spacing:.5px}.save-hint{text-align:center;font-size:10px;color:#9d94a9;line-height:1.6}.privacy-actions{display:flex;justify-content:center;gap:18px;margin:18px 0 0}.privacy-actions button{font-size:10px;color:#a69caf;min-height:38px;padding:5px}.portion-mask{z-index:60}.portion-dialog{box-shadow:0 -8px 40px rgba(44,34,61,.08)}.dialog-header{padding:15px 18px 10px;font-size:16px;font-weight:600}.person-adjustment{padding:14px 0}.family-settings{margin-top:10px}.family-settings .scope-grid{margin-top:12px}.people-card{background:#fff;border-radius:22px;padding:18px;margin-top:12px}.capture-notice{display:block;font-size:12px;line-height:1.8;margin:10px 0}.field-input{box-sizing:border-box}
@keyframes capture-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.recognition-spinner{animation:none}}
@media(max-width:350px){.scan-screen{padding-left:14px;padding-right:14px}.capture-fixed-header{margin-left:-14px;margin-right:-14px;padding-left:14px;padding-right:14px}.nutrition-card{padding-left:18px;padding-right:18px}.meal-context,.context-time{gap:7px;font-size:11px}.macro-number{font-size:19px}.dish-list-card{padding-left:16px;padding-right:16px}.dish-overview{gap:10px}.dish-list-card .source-link,.portion-button{font-size:11px}.portion-button{padding-left:10px;padding-right:10px}}
/* #ifdef H5 */
.capture-fixed-header{max-width:480px}
/* #endif */

.incomplete-toggle{display:flex;align-items:center;gap:8px;text-align:left;font-size:11px;line-height:1.9;color:#9b8c79;min-height:44px}.missing-check{flex:none;display:flex;align-items:center;justify-content:center;width:17px;height:17px;border:1px solid #cec3d8;border-radius:5px;font-size:12px;color:white}.missing-check.checked{background:#8b76a3;border-color:#8b76a3}
</style>
