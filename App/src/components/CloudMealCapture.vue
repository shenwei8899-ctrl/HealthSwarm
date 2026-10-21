<script setup>
import { computed,reactive,ref,watch,onMounted } from 'vue'
import { onShow,onHide,onUnload } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import { request } from '../services/request.js'
import { scopedStorage,storageContext } from '../services/storage.js'
import { createMealPhotoClient,photoState } from '../services/meal-photo-client.js'
import { createCloudMealSaver,personalMeal,mealLabels,mealDay,feedbackUrl } from '../services/cloud-meals.js'
import { commerce } from '../services/commerce.js'
import { getSession } from '../services/session.js'
const props=defineProps({route:{type:Object,default:()=>({})}})
const members=ref([]),people=ref([]),dishes=ref([]),captureScope=ref('单人餐盘'),mealType=ref('dinner'),date=ref(mealDay(new Date().toISOString())),time=ref('18:00'),oil=ref('不确定'),photo=ref(''),error=ref(''),notice=ref(''),busy=ref(false),consent=ref(false),accept=ref(false),editing=ref(false),source=ref('手动填写'),saved=ref(null),pendingGroup=ref(null)
const vision=reactive(photoState()),photoClient=createMealPhotoClient({state:vision}),saver=createCloudMealSaver()
const origin=ref(null)
const portionDraft=ref([]),portionError=ref('');
const mealKeys=Object.keys(mealLabels),portions=['少量','一般','较多','不确定'],oils=['少油','一般','偏多','不确定']
const locked=computed(()=>busy.value||vision.busy||!!vision.pending||(!!pendingGroup.value&&!pendingGroup.value.editable)),selected=computed(()=>people.value.filter(p=>p.selected)),hasDishes=computed(()=>dishes.value.length>0)
const canSave=computed(()=>selected.value.length&&selected.value.every(p=>p.noneConfirmed||p.dishes.length)&&selected.value.some(p=>!p.noneConfirmed&&p.dishes.length))
let epoch=0,opening=false,scope='',loading=false
function store(){if(scope!==storageContext()||!members.value.length)return;scopedStorage.setStorageSync('cloud-capture-ui',{people:people.value,dishes:dishes.value,captureScope:captureScope.value,mealType:mealType.value,date:date.value,time:time.value,oil:oil.value,photo:photo.value,source:source.value,saved:saved.value,origin:origin.value})}
watch([people,dishes,captureScope,mealType,date,time,oil,photo,source,saved],store,{deep:true})
async function load(){if(loading)return;if(scope===storageContext()&&members.value.length)return;const mine=++epoch;scope=storageContext();const context=scope;loading=true;busy.value=true;error.value='';try{const {data}=await request({path:'/api/health/v1/members'});if(mine!==epoch||context!==storageContext())return;members.value=data.filter(m=>m.scopes?.includes('diet_edit'));people.value=members.value.map((m,i)=>({memberId:m.id,name:m.display_name||m.name||m.relationship_label,selected:i===0,dishes:[],portion:'不确定',grams:'',noneConfirmed:false}));const ui=scopedStorage.getStorageSync('cloud-capture-ui');if(ui){people.value=people.value.map(p=>({...p,...ui.people?.find(x=>x.memberId===p.memberId)}));dishes.value=ui.dishes||[];captureScope.value=ui.captureScope;mealType.value=ui.mealType;date.value=ui.date;time.value=ui.time;oil.value=ui.oil;photo.value=ui.photo||'';source.value=ui.source;saved.value=ui.saved;origin.value=ui.origin||null}
 pendingGroup.value=saver.read();
 if(!ui&&mealKeys.includes(props.route.meal))mealType.value=props.route.meal
 if(props.route.commerce==='1'&&props.route.id&&!saver.read()&&!ui){const order=await commerce.cooking(props.route.id);if(mine!==epoch||context!==storageContext())return;dishes.value=order.meal_snapshot.dishes.map(d=>({name:d.recipe_name}));source.value='订单菜谱选菜';notice.value='订单菜谱仅供选菜，请逐人确认实际吃过的菜，未自动记为已吃。'}
 const first=people.value.find(p=>p.selected)||people.value[0];if(first)await photoClient.open(first.memberId)
 if(mine!==epoch||context!==storageContext())return;store()
 }catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch){busy.value=false;loading=false}}}
function hide(){if(opening)return;epoch++;loading=false;store();saver.hide();photoClient.discard();scope='';members.value=[];people.value=[];dishes.value=[];photo.value='';saved.value=null;pendingGroup.value=null;captureScope.value='单人餐盘';mealType.value='dinner';date.value=mealDay(new Date().toISOString());time.value='18:00';oil.value='不确定';source.value='手动填写';origin.value=null;notice.value='';error.value='';busy.value=false;consent.value=false;accept.value=false;editing.value=false;portionDraft.value=[];portionError.value=''}
onMounted(load);onShow(()=>{void load()});onHide(hide);onUnload(()=>{opening=false;hide()})
function togglePerson(p){if(locked.value)return;if(captureScope.value==='单人餐盘')people.value.forEach(x=>x.selected=x===p);else p.selected=!p.selected;consent.value=false;const first=people.value.find(p=>p.selected);if(first&&first.memberId!==vision.memberId)void photoClient.open(first.memberId)}
function setScope(value){if(locked.value)return;captureScope.value=value;if(value==='单人餐盘'){const first=selected.value[0]||people.value[0];people.value.forEach(p=>p.selected=p===first)}}
function toggleDish(p,name){p.dishes=p.dishes.includes(name)?p.dishes.filter(n=>n!==name):[...p.dishes,name];p.noneConfirmed=false}
function openPortions(){if(pendingGroup.value&&!pendingGroup.value.editable)return;portionDraft.value=JSON.parse(JSON.stringify(selected.value));portionError.value='';editing.value=true}
function applyPortions(){if(portionDraft.value.some(p=>!p.noneConfirmed&&!p.dishes.length)){portionError.value='请为每位成员选择实际吃过的菜，或确认本餐未吃';return}for(const row of portionDraft.value){const target=people.value.find(p=>p.memberId===row.memberId);if(target)Object.assign(target,row)}editing.value=false}
function manual(){if(locked.value)return;uni.showModal({title:'手动填写菜品',editable:true,content:dishes.value.map(d=>d.name).join('、'),placeholderText:'例如：杂粮饭、西兰花',success:r=>{if(!r.confirm||!r.content?.trim())return;dishes.value=[...new Set(r.content.split(/[、，,]/).map(n=>n.trim()).filter(Boolean))].map(name=>({name}));source.value=origin.value&&source.value==='照片识别后核对'?'照片识别后核对':'手动填写';saved.value=null;people.value.forEach(p=>p.dishes=p.dishes.filter(n=>dishes.value.some(d=>d.name===n)));openPortions()}})}
async function fromMenu(){if(locked.value)return;const mine=epoch,context=storageContext();busy.value=true;error.value='';try{const {data}=await request({path:'/api/family/'+encodeURIComponent(getSession()?.householdId)+'/daily-arrangements/'+date.value});if(mine!==epoch||context!==storageContext())return;const arrangement=data.arrangement||data;const m=arrangement.meals?.find(m=>(m.type||m.meal_type)===mealType.value);if(!m?.dishes?.length)throw new Error('这一天的本餐尚无已保存食谱，请手动填写实际吃过的菜');dishes.value=m.dishes.map(d=>({name:d.name}));source.value='当天食谱选菜';openPortions()}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch)busy.value=false}}
function chooseImage(which){if(locked.value||!vision.memberId)return;opening=true;const context=storageContext();uni.chooseImage({count:1,sizeType:['compressed'],sourceType:[which],success:async r=>{if(context!==storageContext())return;photo.value=r.tempFilePaths[0];origin.value=null;dishes.value=[];saved.value=null;source.value='照片待识别';notice.value='已更换照片，请重新识别，或手动核对这张照片中的菜品。';vision.draft=null;vision.meal=null;vision.job=null;vision.calculation=null;vision.saved=null;vision.dirty=false;people.value.forEach(p=>{p.dishes=[];p.grams='';p.noneConfirmed=false;p.portion='不确定'});for(const old of [...vision.uploads])photoClient.removePhoto(old.upload_id);await photoClient.addPhoto(photo.value)},fail:e=>{if(!/cancel/i.test(e.errMsg||''))error.value='照片选择失败，请检查权限后重试'},complete:()=>opening=false})}
async function analyze(){if(locked.value)return;await photoClient.start(mealType.value,`${date.value}T${time.value}:00+08:00`,consent.value);useCandidates()}
function useCandidates(){if(!vision.meal||!vision.draft)return;origin.value={memberId:vision.memberId,draft:JSON.parse(JSON.stringify(vision.draft)),meal:JSON.parse(JSON.stringify(vision.meal))};dishes.value=vision.meal.items.filter(i=>!i.excluded).map(i=>({name:i.name,food_id:i.food_id,recipe_version_id:i.recipe_version_id}));source.value='照片识别后核对';openPortions();notice.value='照片只提供候选菜品，请逐人核对；粗略份量不会自动换成克数。'}
async function job(id){await photoClient.job(id);useCandidates()}
function savedMeal(person){
 const meal=personalMeal(dishes.value,person,{mealType:mealType.value,eatenAt:`${date.value}T${time.value}:00+08:00`,captureScope:captureScope.value,oil:oil.value})
 if(source.value==='照片识别后核对'&&origin.value?.draft?.id&&origin.value.memberId===person.memberId){
   const original=JSON.parse(JSON.stringify(origin.value.meal));original.meal_type=meal.meal_type;original.eaten_at=meal.eaten_at
   const used=new Set()
   original.items=original.items.map(item=>{const chosen=meal.items.find(i=>i.name===item.name);if(!chosen)return {...item,excluded:true};used.add(chosen.name);return {...item,...chosen,item_id:item.item_id,locations:item.locations||[],excluded:false}})
   original.items.push(...meal.items.filter(item=>!used.has(item.name)))
   return {memberId:person.memberId,meal:original,draftId:origin.value.draft.id,draftVersion:origin.value.draft.version}
 }
 if(source.value==='照片识别后核对'&&origin.value?.draft?.id)meal.items.forEach(item=>item.uncertainties.push('家庭桌菜候选经本人逐项核对；本成员未关联照片原图'))
 return {memberId:person.memberId,meal}
}
async function save(chat=false){if(scope!==storageContext()){hide();void load();return}if(busy.value||((!saver.read()||saver.read().editable)&&(!canSave.value||!accept.value)))return;const mine=epoch,context=storageContext();busy.value=true;error.value='';try{let meals=[];if(!saver.read()||saver.read().editable)meals=selected.value.filter(p=>!p.noneConfirmed&&p.dishes.length).map(savedMeal);const group=await saver.save(meals,accept.value);if(mine!==epoch||context!==storageContext()||!group)return;saved.value=group;notice.value=`已保存${group.rows.length}位成员的实际记录。`;if(chat)chatWithSaved()}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch){pendingGroup.value=saver.read();busy.value=false}}}
async function recheckRejected(){
 const mine=epoch,context=storageContext(),group=saver.releaseRejected();if(!group)return
 pendingGroup.value=group;error.value='';notice.value='请重新核对未保存成员；已保存成员不会重复记录。'
 if(origin.value){const owner=origin.value.memberId,id=origin.value.draft.id;await photoClient.open(owner);if(mine!==epoch||context!==storageContext())return;await photoClient.draft(id);if(mine!==epoch||context!==storageContext())return;if(vision.draft?.id===id&&vision.draft.review_status==='pending_confirmation')useCandidates();else{origin.value=null;source.value='手动填写';notice.value='原照片候选已不可继续，请核对当前菜品后人工保存未保存成员。'}}
 openPortions()
}
function chatWithSaved(){const rows=saved.value?.rows||[];if(!rows.length)return;const go=row=>uni.navigateTo({url:feedbackUrl(row.memberId,row.record)});if(rows.length===1)go(rows[0]);else uni.showActionSheet({itemList:rows.map(r=>(people.value.find(p=>p.memberId===r.memberId)?.name||'成员')+'的这一餐'),success:r=>go(rows[r.tapIndex])})}
function newMeal(){if(!saved.value||busy.value)return;saver.finish();photoClient.discard();const first=people.value.find(p=>p.selected);if(first)void photoClient.open(first.memberId);pendingGroup.value=null;saved.value=null;origin.value=null;source.value='手动填写';dishes.value=[];photo.value='';accept.value=false;people.value.forEach(p=>{p.dishes=[];p.portion='不确定';p.grams='';p.noneConfirmed=false});store()}
</script>
<template><view class="screen scan-screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack()">‹</button><text class="nav-title">拍照记一餐</text></view></AppNavBar><view class="scan-status"><view class="status-dot"/><text>{{notice||'拍照或从相册选择，开始记录这一餐'}}</text></view><view class="photo-preview"><image v-if="photo" :src="photo" mode="aspectFill"/><view v-else class="photo-placeholder"><text class="photo-symbol">＋</text><text class="photo-title">拍下这一餐</text><text class="small">先核对菜品，再确认每个人的份量</text></view></view><view class="photo-actions"><button class="primary-button" :disabled="locked" @click="chooseImage('camera')">{{photo?'重新拍照':'拍照'}}</button><button class="secondary-button" :disabled="locked" @click="chooseImage('album')">从相册选择</button></view><text v-if="busy||vision.busy" class="safe-note">正在处理，请稍候…</text><text v-if="error||vision.error" class="inline-error">{{error||vision.error}}</text><button v-if="!members.length" class="secondary-button" :disabled="busy" @click="load">重新读取授权成员</button><view class="card capture-setup"><text class="field-title">记录哪一餐</text><view class="scope-grid"><button v-for="s in ['单人餐盘','家庭共享桌菜']" :key="s" :class="{active:captureScope===s}" :disabled="locked" @click="setScope(s)">{{s}}</button></view><view class="member-picks"><button v-for="p in people" :key="p.memberId" :class="{active:p.selected}" :disabled="locked" @click="togglePerson(p)">{{p.name}} · {{p.selected?'已选':'加入'}}</button></view><picker :range="mealKeys.map(k=>mealLabels[k])" :disabled="locked" @change="mealType=mealKeys[$event.detail.value]"><view class="setup-row">餐次 <text>{{mealLabels[mealType]}} ›</text></view></picker><view class="setup-row"><picker mode="date" :value="date" :disabled="locked" @change="date=$event.detail.value">{{date}} ›</picker><picker mode="time" :value="time" :disabled="locked" @change="time=$event.detail.value">{{time}} ›</picker></view></view><template v-if="photo&&vision.uploads.length"><view v-if="vision.config?.meal?.available" class="card capture-setup"><text class="small">照片识别处理方：{{vision.config.meal.processor}} · 政策{{vision.config.policy_version}}</text><label><switch :checked="consent" :disabled="locked" @change="consent=$event.detail.value"/>同意本次照片识别</label><button class="primary-button" :disabled="locked||!consent" @click="analyze">上拉分析这张照片</button></view><text v-else class="safe-note">照片识别服务当前不可用，可手动核对菜品后记餐。</text></template><view v-if="vision.job" class="card capture-setup"><text>照片识别：{{vision.job.execution_status}}</text><button :disabled="vision.busy" @click="job(vision.job.task_id)">读取识别结果</button></view><button v-if="vision.pending" class="secondary-button" :disabled="vision.busy" @click="photoClient.retryPending()">恢复原照片任务</button><view v-if="vision.drafts.length&&!hasDishes" class="card capture-setup"><text>继续核对之前的照片</text><button v-for="d in vision.drafts.filter(d=>d.review_status!=='confirmed')" :key="d.id" @click="photoClient.draft(d.id).then(useCandidates)">{{d.payload?.items?.map(i=>i.name).join('、')||'未核对候选'}} ›</button></view><view class="other-methods"><button :disabled="locked" @click="fromMenu">从今日食谱选菜</button><button :disabled="locked" @click="manual">手动填写</button></view><view v-if="hasDishes" class="card foods-card"><view class="foods-heading"><text class="field-title">{{source==='照片识别后核对'?'识别出的菜品':'本餐菜品'}}</text><button class="adjust-button" :disabled="locked" @click="openPortions">调整份量</button></view><text v-for="d in dishes" :key="d.name" class="food-row">{{d.name}}</text><button class="correction" :disabled="locked" @click="manual">修改本餐菜品</button></view><view v-if="hasDishes" class="card nutrition-card"><text class="field-title">{{captureScope==='家庭共享桌菜'?'家庭记餐':'本餐摄入'}} · 逐人确认</text><view v-for="p in selected" :key="p.memberId" class="intake-summary"><text>{{p.name}}</text><text>{{p.noneConfirmed?'未吃这些菜':p.dishes.join('、')||'尚未确认菜品'}} · {{p.portion}}</text></view><text class="small">每人只记录本人确认吃过的菜和份量，不分摊整桌热量。多道菜的合计克数只作为补充记录。</text><text class="adjust-label">烹饪用油（选填）</text><view class="portion-choices"><button v-for="o in oils" :key="o" :class="{active:oil===o}" :disabled="locked" @click="oil=o">{{o}}</button></view><text class="nutrition-empty">未称重或未匹配营养资料时，营养值保持未知。</text></view><template v-if="hasDishes&&!saved"><label class="safe-note"><switch :checked="accept" :disabled="locked" @change="accept=$event.detail.value"/>接受缺失营养保持未知，保存真实摄入</label><view class="save-actions"><button class="secondary-button" :disabled="busy||((!saver.read()||saver.read().editable)&&(!canSave||!accept))" @click="save()">{{saver.read()&&!saver.read().editable?'恢复原保存请求':'仅保存'}}</button><button class="primary-button" :disabled="busy||((!saver.read()||saver.read().editable)&&(!canSave||!accept))" @click="save(true)">保存并聊聊这一餐</button></view></template><view v-if="pendingGroup&&!saved" class="card capture-setup"><text v-for="r in pendingGroup.rows.filter(r=>r.phase==='saved')" :key="r.memberId">{{people.find(p=>p.memberId===r.memberId)?.name}}已保存，将保留原收据。</text><button v-if="pendingGroup.rows.some(r=>r.phase==='rejected')&&!pendingGroup.editable" :disabled="busy" @click="recheckRejected">重新核对未保存成员</button></view><view v-if="saved" class="card capture-setup"><text class="section-title">这一餐已保存</text><text v-for="r in saved.rows" :key="r.memberId">{{people.find(p=>p.memberId===r.memberId)?.name}} · v{{r.record.source_version}}</text><button class="primary-button" @click="chatWithSaved">继续聊聊这一餐</button><button class="secondary-button" @click="uni.navigateTo({url:'/pages/records/index'})">查看饮食记录</button><button class="secondary-button" @click="newMeal">记录新的一餐</button></view><view v-if="editing" class="portion-mask" @click.self="editing=false"><view class="portion-dialog"><view class="dialog-header"><view><text class="section-title">调整份量</text><text class="small">{{mealLabels[mealType]}} · {{captureScope}}</text></view><button class="dialog-close" aria-label="关闭份量调整" @click="editing=false">×</button></view><scroll-view class="dialog-body" scroll-y><view v-for="p in portionDraft" :key="p.memberId" class="person-adjustment"><view class="person-heading"><text>{{p.name}}吃了什么</text><button class="not-eaten" :class="{active:p.noneConfirmed}" :disabled="busy" @click="p.noneConfirmed=true;p.dishes=[]">未吃这些菜</button></view><view class="dish-picks"><button v-for="d in dishes" :key="d.name" :class="{active:p.dishes.includes(d.name)}" :disabled="busy" @click="toggleDish(p,d.name)">{{d.name}}</button></view><template v-if="!p.noneConfirmed"><text class="adjust-label">大致吃了多少</text><view class="portion-choices"><button v-for="n in portions" :key="n" :class="{active:p.portion===n}" :disabled="busy" @click="p.portion=n">{{n}}</button></view><input v-model="p.grams" type="digit" class="field-input" :disabled="busy" placeholder="实际克数（选填，可留空）"/></template></view><text class="dialog-note">每位成员只记录自己吃过的菜。粗略份量不会自动换算成重量，不要求称重。</text></scroll-view><view class="dialog-footer"><text v-if="portionError" class="inline-error">{{portionError}}</text><view class="dialog-actions"><button class="secondary-button" @click="editing=false">取消</button><button class="primary-button" @click="applyPortions">确认份量</button></view></view></view></view></view></template>
<style scoped>
.scan-flow{margin-top:20rpx}
.scan-status{display:flex;align-items:center;gap:12rpx;margin:24rpx 0 18rpx;padding:18rpx 22rpx;border:1rpx solid #ebebef;border-radius:20rpx;background:#fff;color:#63636b;font-size:23rpx;line-height:1.5}
.status-dot{width:12rpx;height:12rpx;flex-shrink:0;border-radius:50%;background:#246b50}
.processing .status-dot{animation:pulse 1s infinite alternate}
.photo-preview{position:relative;height:400rpx;overflow:hidden;border:1rpx solid #ebebef;border-radius:28rpx;background:#e9ecea}
.photo-preview image{width:100%;height:100%}
.photo-placeholder{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16rpx}
.photo-symbol{color:#246b50;font-size:76rpx;line-height:1}
.photo-title{font-size:30rpx;font-weight:600}
.photo-placeholder .small{font-size:23rpx;text-align:center}
.demo-plate{display:flex;align-items:center;justify-content:center;gap:18rpx;width:290rpx;height:210rpx;border:16rpx solid #fff;border-radius:50%;background:#f0f3f1;font-size:58rpx}
.confidence{position:absolute;left:20rpx;bottom:20rpx;max-width:calc(100% - 40rpx);padding:12rpx 18rpx;border-radius:16rpx;background:rgba(29,29,31,.78);color:#fff;font-size:21rpx}
.scan-line{position:absolute;left:6%;right:6%;top:20%;height:3rpx;background:#fff;box-shadow:0 0 20rpx #fff;animation:scan 1.2s infinite alternate}
@keyframes scan{to{top:78%}}@keyframes pulse{to{opacity:.3}}
.photo-actions{display:grid;grid-template-columns:1fr 1fr;gap:14rpx;margin-top:16rpx}
.photo-actions button{min-height:80rpx;font-size:26rpx}
.photo-actions .photo-capture-label{color:#fff;font-size:26rpx;font-weight:600}
.capture-setup{margin-top:24rpx;padding:24rpx}
.field-title{display:block;font-size:28rpx;font-weight:600;line-height:1.4}
.scope-grid{display:grid;grid-template-columns:1fr 1fr;gap:12rpx;margin-top:20rpx}
.scope-grid button,.member-picks button{min-height:64rpx;padding:14rpx;border:1rpx solid #dedee3;border-radius:16rpx;color:#63636b;font-size:23rpx}
.scope-grid button.active,.member-picks button.active{border-color:#246b50;background:#eaf2ed;color:#246b50;font-weight:600}
.setup-row{width:100%;display:flex;justify-content:space-between;gap:16rpx;padding:22rpx 0;border-bottom:1rpx solid #ebebef;font-size:25rpx}
.setup-row:last-child{border:0;padding-bottom:0}
.setup-row text:last-child{color:#246b50}
.member-picks{display:flex;flex-wrap:wrap;gap:10rpx;margin-top:20rpx}
.demo-entry{width:100%;margin-top:22rpx;padding:18rpx;color:#246b50;font-size:25rpx}
.other-methods{display:grid;grid-template-columns:1fr 1fr;gap:12rpx;margin-top:8rpx}
.other-methods button{padding:18rpx;border:1rpx solid #dedee3;border-radius:18rpx;background:#fff;font-size:23rpx;color:#63636b}
.analyzing-card{display:flex;flex-direction:column;gap:14rpx;margin-top:24rpx;padding:28rpx;font-size:25rpx;color:#63636b}
.result-state{display:flex;flex-direction:column;gap:20rpx;margin-top:24rpx}
.foods-card,.nutrition-card,.confirm-card,.risk-card{padding:26rpx}
.foods-heading,.nutrition-heading,.risk-heading{display:flex;align-items:center;justify-content:space-between;gap:16rpx}
.foods-heading>view{display:flex;flex-direction:column;gap:8rpx}
.foods-heading .small{font-size:22rpx}
.adjust-button{flex-shrink:0;min-height:68rpx;padding:16rpx 22rpx;border-radius:18rpx;background:#246b50;color:#fff;font-size:25rpx;font-weight:600}
.food-row{display:flex;align-items:center;gap:14rpx;min-height:88rpx;border-top:1rpx solid #ebebef;font-size:28rpx}
.food-row:first-of-type{margin-top:20rpx}
.food-row>text:first-of-type{flex:1;min-width:0}
.food-row .small{font-size:22rpx;flex-shrink:0}
.food-dot{width:10rpx;height:10rpx;border-radius:50%;background:#246b50;flex-shrink:0}
.nutrition-heading .status-chip{flex-shrink:0;font-size:21rpx}
.calorie-line{display:flex;align-items:baseline;gap:10rpx;margin-top:24rpx;color:#63636b;font-size:25rpx}
.calorie-value{color:#1d1d1f;font-size:52rpx;font-weight:600}
.nutrition-range{display:block;margin-top:10rpx;font-size:23rpx;color:#63636b}
.macro-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10rpx;margin-top:22rpx}
.macro-grid>view{display:flex;flex-direction:column;gap:8rpx;padding:16rpx 6rpx;border-radius:16rpx;background:#f5f5f7;text-align:center;font-size:25rpx;font-weight:600}
.macro-grid .small{font-size:21rpx;font-weight:400}
.nutrition-empty{display:block;margin-top:20rpx;font-size:25rpx;color:#63636b;line-height:1.65}
.intake-summary{display:flex;flex-direction:column;gap:14rpx;margin-top:20rpx}
.intake-summary>view{display:flex;justify-content:space-between;gap:20rpx;font-size:24rpx}
.intake-summary text:last-child{color:#63636b;text-align:right}
.estimate-note{display:block;margin-top:20rpx;font-size:22rpx;color:#767680;line-height:1.65}
.confirm-row{width:100%;display:flex;align-items:center;justify-content:space-between;gap:20rpx;min-height:80rpx;border-bottom:1rpx solid #ebebef;text-align:left;font-size:26rpx}
.confirm-row:last-child{border:0}
.confirm-row>text:last-child{max-width:65%;color:#63636b;text-align:right;font-size:24rpx}
.inline-link{flex-shrink:0;padding:10rpx 0;color:#246b50;font-size:23rpx}
.risk-card{display:flex;flex-direction:column;gap:14rpx;font-size:25rpx;line-height:1.65}
.risk-card .small,.risk-details{font-size:23rpx}
.risk-heading .field-title{font-size:27rpx}
.risk-warning{color:#c73632;font-weight:600}
.risk-details,.member-caution{display:flex;flex-direction:column;gap:12rpx;border-top:1rpx solid #ebebef;padding-top:16rpx}
.correction{width:100%;min-height:76rpx;border:1rpx solid #dedee3;border-radius:20rpx;background:#fff;color:#246b50;font-size:25rpx;font-weight:500}
.save-actions{display:grid;grid-template-columns:.8fr 1.4fr;gap:12rpx}
.save-actions button{min-width:0;padding:16rpx 10rpx;font-size:25rpx}
.portion-mask{position:fixed;inset:0;z-index:100;display:flex;align-items:center;justify-content:center;padding:32rpx;background:rgba(0,0,0,.4)}
.portion-dialog{width:100%;max-width:690rpx;max-height:86vh;display:flex;flex-direction:column;overflow:hidden;border-radius:32rpx;background:#fff}
.dialog-header{display:flex;align-items:center;justify-content:space-between;gap:16rpx;padding:26rpx 28rpx 22rpx;border-bottom:1rpx solid #ebebef}
.dialog-header>view{display:flex;flex-direction:column;gap:8rpx}
.dialog-header .section-title{font-size:32rpx}
.dialog-header .small{font-size:22rpx}
.dialog-close{width:64rpx;height:64rpx;flex-shrink:0;border-radius:50%;background:#f5f5f7;font-size:38rpx;color:#63636b}
.dialog-body{height:52vh;min-height:0}
.person-adjustment,.oil-adjustment{margin:0 26rpx;padding:24rpx 0;border-bottom:1rpx solid #ebebef}
.person-heading{display:flex;align-items:center;justify-content:space-between;gap:12rpx}
.person-heading .field-title{font-size:27rpx}
.not-eaten{flex-shrink:0;padding:10rpx 12rpx;border:1rpx solid #dedee3;border-radius:12rpx;color:#63636b;font-size:21rpx}
.not-eaten.active{border-color:#246b50;color:#246b50;background:#eaf2ed}
.dish-picks{display:flex;flex-wrap:wrap;gap:10rpx;margin-top:18rpx}
.dish-picks button{min-height:60rpx;padding:14rpx 18rpx;border:1rpx solid #dedee3;border-radius:16rpx;color:#63636b;font-size:23rpx}
.dish-picks button.active,.portion-choices button.active{border-color:#246b50;background:#eaf2ed;color:#246b50;font-weight:600}
.adjust-label{display:block;margin-top:22rpx;font-size:24rpx}
.portion-choices{display:grid;grid-template-columns:repeat(4,1fr);gap:8rpx;margin-top:14rpx}
.portion-choices button{min-height:62rpx;padding:14rpx 4rpx;border:1rpx solid #dedee3;border-radius:14rpx;color:#63636b;font-size:23rpx}
.grams-row{display:flex;align-items:center;gap:10rpx;margin-top:22rpx;font-size:24rpx}
.grams-row>view{display:flex;flex:1;min-width:0;flex-direction:column;gap:8rpx}
.grams-row .small{font-size:20rpx}
.grams-row input{width:132rpx;height:64rpx;padding:0 14rpx;border:1rpx solid #dedee3;border-radius:14rpx;background:#f5f5f7;font-size:24rpx;text-align:right}
.dialog-note{display:block;margin:22rpx 26rpx 26rpx;font-size:21rpx;color:#767680;line-height:1.65}
.draft-nutrition{display:flex;flex-direction:column;gap:10rpx;margin:22rpx 26rpx;padding:22rpx;border-radius:20rpx;background:#f5f5f7}.draft-calories{font-size:34rpx;font-weight:600}.draft-nutrition .small{font-size:22rpx;line-height:1.6}
.dialog-footer{flex-shrink:0;padding:20rpx 26rpx 26rpx;border-top:1rpx solid #ebebef}
.dialog-footer .inline-error{padding:0 0 16rpx;font-size:23rpx}
.dialog-actions{display:grid;grid-template-columns:1fr 1fr;gap:14rpx}
.dialog-actions button{min-height:80rpx;padding:16rpx 8rpx;font-size:26rpx}
.scan-screen{padding-bottom:60rpx}.capture-setup{margin-top:24rpx;display:flex;flex-direction:column;gap:16rpx}.setup-row{justify-content:space-between}.person-heading{font-size:28rpx}.safe-note{text-align:left}.scan-screen button[disabled]{opacity:.5}.small{font-size:24rpx}</style>