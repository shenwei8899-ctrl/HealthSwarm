<script setup>
import { computed,reactive,ref,watch,onMounted } from 'vue'
import { onShow,onHide,onUnload } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'
import FoodImageSlot from './FoodImageSlot.vue'
import { request } from '../services/request.js'
import { scopedStorage,storageContext } from '../services/storage.js'
import { createMealPhotoClient,photoState } from '../services/meal-photo-client.js'
import { createCloudMealSaver,personalMeal,mealLabels,mealDay,feedbackUrl } from '../services/cloud-meals.js'
import { commerce } from '../services/commerce.js'
import { getSession } from '../services/session.js'
const props=defineProps({route:{type:Object,default:()=>({})}})
const members=ref([]),people=ref([]),dishes=ref([]),captureScope=ref('单人餐盘'),mealType=ref('dinner'),date=ref(mealDay(new Date().toISOString())),time=ref('18:00'),oil=ref('不确定'),photo=ref(''),error=ref(''),notice=ref(''),busy=ref(false),consent=ref(false),editing=ref(false),source=ref('手动填写'),saved=ref(null),pendingGroup=ref(null)
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
 const first=people.value.find(p=>p.selected)||people.value[0];if(first)await photoClient.open(first.memberId,data)
 if(mine!==epoch||context!==storageContext())return;store()
 }catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch){busy.value=false;loading=false}}}
function hide(){if(opening)return;epoch++;loading=false;store();saver.hide();photoClient.discard();scope='';members.value=[];people.value=[];dishes.value=[];photo.value='';saved.value=null;pendingGroup.value=null;captureScope.value='单人餐盘';mealType.value='dinner';date.value=mealDay(new Date().toISOString());time.value='18:00';oil.value='不确定';source.value='手动填写';origin.value=null;notice.value='';error.value='';busy.value=false;consent.value=false;editing.value=false;portionDraft.value=[];portionError.value=''}
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
async function save(chat=false){if(scope!==storageContext()){hide();void load();return}if(busy.value||((!saver.read()||saver.read().editable)&&!canSave.value))return;const mine=epoch,context=storageContext();busy.value=true;error.value='';try{let meals=[];if(!saver.read()||saver.read().editable)meals=selected.value.filter(p=>!p.noneConfirmed&&p.dishes.length).map(savedMeal);const group=await saver.save(meals,true);if(mine!==epoch||context!==storageContext()||!group)return;saved.value=group;notice.value=`已保存${group.rows.length}位成员的实际记录。`;if(chat)chatWithSaved()}catch(e){if(mine===epoch)error.value=e.message}finally{if(mine===epoch){pendingGroup.value=saver.read();busy.value=false}}}
async function recheckRejected(){
 const mine=epoch,context=storageContext(),group=saver.releaseRejected();if(!group)return
 pendingGroup.value=group;error.value='';notice.value='请重新核对未保存成员；已保存成员不会重复记录。'
 if(origin.value){const owner=origin.value.memberId,id=origin.value.draft.id;await photoClient.open(owner);if(mine!==epoch||context!==storageContext())return;await photoClient.draft(id);if(mine!==epoch||context!==storageContext())return;if(vision.draft?.id===id&&vision.draft.review_status==='pending_confirmation')useCandidates();else{origin.value=null;source.value='手动填写';notice.value='原照片候选已不可继续，请核对当前菜品后人工保存未保存成员。'}}
 openPortions()
}
function chatWithSaved(){const rows=saved.value?.rows||[];if(!rows.length)return;const go=row=>uni.navigateTo({url:feedbackUrl(row.memberId,row.record)});if(rows.length===1)go(rows[0]);else uni.showActionSheet({itemList:rows.map(r=>(people.value.find(p=>p.memberId===r.memberId)?.name||'成员')+'的这一餐'),success:r=>go(rows[r.tapIndex])})}
function newMeal(){if(!saved.value||busy.value)return;saver.finish();photoClient.discard();const first=people.value.find(p=>p.selected);if(first)void photoClient.open(first.memberId);pendingGroup.value=null;saved.value=null;origin.value=null;source.value='手动填写';dishes.value=[];photo.value='';people.value.forEach(p=>{p.dishes=[];p.portion='不确定';p.grams='';p.noneConfirmed=false});store()}
</script>
<template>
 <view class="screen scan-screen"><AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="uni.navigateBack()">‹</button><text class="nav-title">拍照记餐</text><view class="nav-spacer"/></view></AppNavBar>
  <view class="capture-page-wash" aria-hidden="true"/>
  <view class="capture-card">
  <view class="capture-card-heading"><view><text class="capture-card-title">记录这一餐</text><text class="capture-card-caption">拍照、选照片，或直接填写。</text></view><view class="capture-leaf" aria-hidden="true"><view class="capture-leaf-glyph"/></view></view>
  <text v-if="notice" class="capture-notice">{{notice}}</text>
  <view class="photo-preview"><image v-if="photo" :src="photo" mode="aspectFill"/><view v-else class="photo-placeholder"><view class="capture-camera-tile" aria-hidden="true"><AppIcon name="camera" :size="52"/></view><text>拍下这一餐</text><text class="capture-photo-caption">清晰拍下食物，方便核对菜品</text></view></view>
  <view class="photo-actions"><button class="capture-primary" :hover-class="locked||saved?'none':'capture-pressed'" :hover-start-time="0" :hover-stay-time="50" :disabled="locked||!!saved" @click="chooseImage('camera')"><AppIcon name="camera" :size="36"/>{{photo?'重新拍照':'拍照'}}</button><button class="capture-secondary" :hover-class="locked||saved?'none':'capture-pressed'" :hover-start-time="0" :hover-stay-time="50" :disabled="locked||!!saved" @click="chooseImage('album')"><view class="capture-album-glyph" aria-hidden="true"/>从相册选择</button></view>
  <view class="other-methods"><button :disabled="locked||!!saved" @click="fromMenu">从今日食谱选择 ›</button><text>｜</text><button :disabled="locked||!!saved" @click="manual">手动填写 ›</button></view>
  <text v-if="busy||vision.busy" class="safe-note">正在处理，请稍候…</text><text v-if="error||vision.error" class="inline-error" role="alert">{{error||vision.error}}</text><button v-if="!members.length" class="secondary-button" :disabled="busy" @click="load">重新读取成员</button>
  <template v-if="photo&&vision.uploads.length"><view v-if="vision.config?.meal?.available" class="card recognition-card"><text class="small">照片识别处理方：{{vision.config.meal.processor}} · 政策{{vision.config.policy_version}}</text><label><switch :checked="consent" :disabled="locked" @change="consent=$event.detail.value"/>同意本次照片识别</label><button class="primary-button" :disabled="locked||!consent" @click="analyze">识别照片</button></view><text v-else class="safe-note">照片识别暂不可用，可手动填写菜品。</text></template>
  <view v-if="vision.job" class="card recognition-card"><text>照片识别：{{vision.job.execution_status}}</text><button :disabled="vision.busy" @click="job(vision.job.task_id)">读取识别结果</button></view><button v-if="vision.pending" class="secondary-button" :disabled="vision.busy" @click="photoClient.retryPending()">恢复原照片任务</button><view v-if="vision.drafts.length&&!hasDishes" class="card recognition-card"><text>继续核对之前的照片</text><button v-for="d in vision.drafts.filter(d=>d.review_status!=='confirmed')" :key="d.id" @click="photoClient.draft(d.id).then(useCandidates)">{{d.payload?.items?.map(i=>i.name).join('、')||'未核对菜品'}} ›</button></view>
  <view class="capture-settings"><text class="capture-field-label">就餐方式</text>
  <view class="scope-grid"><button v-for="s in ['单人餐盘','家庭共享桌菜']" :key="s" :class="{active:captureScope===s}" :aria-pressed="captureScope===s" :hover-class="locked||saved?'none':'capture-pressed'" :hover-start-time="0" :hover-stay-time="50" :disabled="locked||!!saved" @click="setScope(s)">{{s}}</button></view>
  <view v-if="people.length>1" class="member-picks"><button v-for="p in people" :key="p.memberId" :class="{active:p.selected}" :disabled="locked||!!saved" :aria-pressed="p.selected" @click="togglePerson(p)">{{p.selected?'✓ ':''}}{{p.name}}</button></view>
  <text class="capture-field-label capture-time-label">用餐时间</text>
  <view class="meal-time"><AppIcon name="calendar" :size="34"/><picker :range="mealKeys.map(k=>mealLabels[k])" :disabled="locked||!!saved" @change="mealType=mealKeys[$event.detail.value]"><view>{{mealLabels[mealType]}} <text>⌄</text></view></picker><picker mode="date" :value="date" :disabled="locked||!!saved" @change="date=$event.detail.value"><view>{{date.slice(5).replace('-','月')}}日</view></picker><picker mode="time" :value="time" :disabled="locked||!!saved" @change="time=$event.detail.value"><view>{{time}} <text>›</text></view></picker></view>
  </view>
  <view v-if="hasDishes" class="foods-card"><view class="section-heading"><text>{{source==='照片识别后核对'?'核对本餐菜品':'本餐食物'}}</text><button :disabled="locked||!!saved" @click="manual">修改菜品 ›</button></view><scroll-view class="food-strip" scroll-x><view class="food-strip-inner"><view v-for="d in dishes" :key="d.name" class="food-tile"><FoodImageSlot :src="d.image_url" :label="d.name" class="food-thumb"/><text>{{d.name}}</text></view></view></scroll-view></view>
  <view v-if="hasDishes" class="people-card"><text class="field-title">每个人吃了什么</text><view v-for="p in selected" :key="p.memberId" class="person-row"><view class="person-heading"><view class="person-avatar" aria-hidden="true">{{p.name.slice(0,1)}}</view><text class="person-name">{{p.name}}</text><view class="portion-choices"><button v-for="n in portions" :key="n" :class="{active:p.portion===n&&!p.noneConfirmed}" :aria-pressed="p.portion===n&&!p.noneConfirmed" :disabled="locked||!!saved||p.noneConfirmed||!p.dishes.length" @click="p.portion=n">{{n}}</button></view></view><button class="person-dishes" :disabled="locked||!!saved" @click="openPortions"><text>{{p.noneConfirmed?'未吃这些菜':p.dishes.join(' · ')||'确认吃过的菜品'}}</text><text>{{p.dishes.length||p.noneConfirmed?'修改':'选择'}} ›</text></button></view>
   <view class="oil-row"><text>烹饪用油 <text>选填</text></text><picker :range="oils" :value="Math.max(0,oils.indexOf(oil))" :disabled="locked||!!saved" @change="oil=oils[$event.detail.value]"><view>{{oil}} ›</view></picker></view>
  </view>
  <view v-if="hasDishes&&!saved" class="nutrition-state"><text>营养数据</text><text>未知</text></view>
  <view v-if="hasDishes&&!saved" class="save-actions"><button class="save-secondary" :disabled="busy||((!saver.read()||saver.read().editable)&&!canSave)" @click="save()">{{saver.read()&&!saver.read().editable?'恢复原保存请求':'仅保存'}}</button><button class="save-primary" :disabled="busy||((!saver.read()||saver.read().editable)&&!canSave)" @click="save(true)">保存并聊聊这一餐</button></view>
  <view v-if="pendingGroup&&!saved" class="card recognition-card"><text v-for="r in pendingGroup.rows.filter(r=>r.phase==='saved')" :key="r.memberId">{{people.find(p=>p.memberId===r.memberId)?.name}}已保存</text><button v-if="pendingGroup.rows.some(r=>r.phase==='rejected')&&!pendingGroup.editable" :disabled="busy" @click="recheckRejected">重新核对未保存成员</button></view>
  <view v-if="saved" class="card recognition-card"><text class="section-title">这一餐已保存</text><text>{{saved.rows.map(r=>people.find(p=>p.memberId===r.memberId)?.name).filter(Boolean).join(' · ')}}</text><button class="primary-button" @click="chatWithSaved">继续聊聊这一餐</button><button class="secondary-button" @click="uni.navigateTo({url:'/pages/records/index'})">查看饮食记录</button><button class="text-link" @click="newMeal">记录新的一餐</button></view>
  </view>
  <text v-if="!hasDishes&&!saved" class="capture-endnote">记录前，请核对菜品与实际份量</text>
  <view v-if="editing" class="portion-mask" @click.self="editing=false"><view class="portion-dialog"><view class="dialog-header"><text>确认吃过的菜和份量</text><button aria-label="关闭份量调整" @click="editing=false">×</button></view><scroll-view class="dialog-body" scroll-y :style="{height:Math.min(680,180+portionDraft.length*360)+'rpx'}"><view v-for="p in portionDraft" :key="p.memberId" class="person-adjustment"><view class="adjustment-heading"><text>{{p.name}}</text><button class="not-eaten" :class="{active:p.noneConfirmed}" :disabled="busy" @click="p.noneConfirmed=true;p.dishes=[]">未吃这些菜</button></view><view class="dish-picks"><button v-for="d in dishes" :key="d.name" :class="{active:p.dishes.includes(d.name)}" :aria-pressed="p.dishes.includes(d.name)" :disabled="busy" @click="toggleDish(p,d.name)">{{d.name}}</button></view><template v-if="!p.noneConfirmed"><view class="portion-choices dialog-portions"><button v-for="n in portions" :key="n" :class="{active:p.portion===n}" :disabled="busy" @click="p.portion=n">{{n}}</button></view><input v-model="p.grams" type="digit" class="field-input" :disabled="busy" placeholder="实际克数（选填）"/></template></view></scroll-view><view class="dialog-footer"><text v-if="portionError" class="inline-error">{{portionError}}</text><view class="dialog-actions"><button class="secondary-button" @click="editing=false">取消</button><button class="primary-button" @click="applyPortions">确认</button></view></view></view></view>
 </view>
</template>

<style scoped>
.nav-spacer{width:80rpx}
.foods-card{margin-top:22px;padding-bottom:18px;border-bottom:1px solid #eeedf4}.section-heading,.person-heading,.adjustment-heading,.dialog-header,.oil-row,.nutrition-state{display:flex;align-items:center;justify-content:space-between;gap:8px}.section-heading,.field-title,.adjustment-heading{font-size:15px;font-weight:500}.section-heading button,.person-dishes,.oil-row,.text-link,.small{font-size:12px;color:var(--ui-muted)}.section-heading button,.person-dishes,.oil-row,.text-link{min-height:44px}.food-strip{white-space:nowrap}.food-strip-inner{display:flex;gap:9px;padding-top:4px}.food-tile{flex:none;width:71px;white-space:normal}.food-thumb{width:71px;height:64px;border-radius:9px}.food-tile>text{display:block;margin-top:5px;text-align:center;font-size:12px;line-height:1.5;overflow-wrap:anywhere}
.people-card{padding-top:18px}.field-title{display:block;margin-bottom:4px}.person-row,.person-adjustment{padding:10px 0;border-bottom:1px solid #eeedf4}.person-heading{justify-content:flex-start;flex-wrap:wrap}.person-avatar{display:flex;align-items:center;justify-content:center;flex:none;width:32px;height:32px;border-radius:50%;background:#f1f1f7;color:var(--ui-muted);font-size:12px}.person-name{font-size:13px;max-width:90px;overflow-wrap:anywhere}.portion-choices{display:flex;flex:1;gap:4px;margin-left:auto;min-width:220px}.portion-choices button,.dish-picks button,.not-eaten{min-height:44px;padding:6px 8px;border:1px solid #e9e7ef;border-radius:8px;background:#f8f8fb;color:var(--ui-muted);font-size:12px;line-height:1.5}.portion-choices button{flex:1;white-space:nowrap}.person-dishes{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;text-align:left;line-height:1.6}.person-dishes>text:first-child{flex:1;min-width:0;overflow-wrap:anywhere}.person-dishes>text:last-child{flex:none}.oil-row{margin-top:4px}.oil-row>text>text{margin-left:6px}.oil-row picker{display:flex;align-items:center;min-height:44px}.nutrition-state{padding:8px 0;margin-top:12px;font-size:14px}.nutrition-state>text:last-child{color:var(--ui-muted)}
.save-actions{position:fixed;z-index:20;left:0;right:0;bottom:0;display:flex;gap:8px;padding:10px 18px calc(env(safe-area-inset-bottom) + 10px);box-sizing:border-box;background:#fff;border-top:1px solid #eeedf4}.save-actions button{display:flex;align-items:center;justify-content:center;min-width:0;min-height:46px;padding:8px 6px;border-radius:999px;font-size:13px;line-height:1.4}.save-secondary{flex:.8;border:1px solid #d9d6e2;background:#fff;color:var(--ui-text)}.save-primary{flex:1.4;background:var(--ui-accent);color:#fff}.recognition-card{display:flex;flex-direction:column;gap:10px;line-height:1.65}.text-link{font-size:13px}
.portion-mask{position:fixed;inset:0;z-index:100;display:flex;align-items:flex-end;background:var(--ui-overlay)}.portion-dialog{display:flex;flex-direction:column;width:100%;max-height:90vh;overflow:hidden;border-radius:22px 22px 0 0;background:#fff}.dialog-header{flex:none;padding:12px 14px 4px;font-size:16px;font-weight:500}.dialog-header button{min-width:44px;min-height:44px;font-size:22px;color:var(--ui-muted)}.dialog-body{max-height:58vh;min-height:0}.person-adjustment{margin:0 14px}.dish-picks{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.dialog-portions{margin:10px 0 6px}.field-input{margin:6px 0 0;font-size:13px}.dialog-footer{flex:none;padding:8px 14px calc(env(safe-area-inset-bottom) + 12px);border-top:1px solid #eeedf4}.dialog-actions{display:flex;gap:8px}.dialog-actions button{flex:1;min-width:0;font-size:14px}
@media(max-width:390px){.portion-choices{flex-basis:100%;margin-left:0;min-width:0}}
/* #ifdef H5 */
.save-actions,.portion-dialog{max-width:480px;margin-left:auto;margin-right:auto}
/* #endif */

/* One recording card over the same fixed blue/purple wash as conversation history. */
.scan-screen{position:relative;z-index:0;background:var(--ui-canvas);padding:0 18px calc(env(safe-area-inset-bottom) + 110px);color:var(--ui-text)}
.capture-page-wash{position:fixed;z-index:-1;top:0;left:0;right:0;height:360px;pointer-events:none;background-image:radial-gradient(ellipse at 0% 0%,rgba(125,174,255,.65),rgba(125,174,255,0) 72%),radial-gradient(ellipse at 100% 0%,rgba(206,178,245,.55),rgba(206,178,245,0) 75%);background-repeat:no-repeat;background-size:100% 100%}
.scan-screen .icon-button{min-width:44px;min-height:44px}
.capture-card{min-width:0;margin-top:16px;padding:22px 18px 20px;border:1px solid rgba(255,255,255,.94);border-radius:28px;background:linear-gradient(165deg,rgba(255,255,255,.92),#fff 48%);box-shadow:inset 0 1px 0 #fff,0 8px 28px rgba(75,69,107,.035)}
.capture-card-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px}
.capture-card-heading>view:first-child{min-width:0;display:flex;flex-direction:column;gap:5px}
.capture-card-title{font-size:21px;font-weight:500;line-height:1.45;color:var(--ui-text)}
.capture-card-caption{font-size:12px;line-height:1.6;color:var(--ui-muted)}
.photo-preview{overflow:hidden}.photo-preview image{width:100%;height:100%}.photo-placeholder{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center}
.photo-actions{display:flex;position:relative}.photo-actions button{display:flex;flex:1;align-items:center;justify-content:center}
.other-methods{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:center;position:relative}.scope-grid{display:flex}.scope-grid button{flex:1}
.member-picks{display:flex;flex-wrap:wrap}.member-picks button{border:1px solid #eeedf4;border-radius:999px;background:#fff}
.meal-time{display:flex;align-items:center;box-sizing:border-box}.meal-time picker{display:flex;align-items:center}
.capture-leaf{display:flex;align-items:center;justify-content:center;width:34px;height:34px;flex:none;border-radius:12px;background:#edf6f2;color:#7aab99;transform:rotate(-7deg)}
.capture-leaf-glyph{position:relative;width:15px;height:12px;border:1.3px solid currentColor;border-radius:80% 0 80% 0;transform:rotate(-18deg)}
.capture-leaf-glyph:after{content:'';position:absolute;width:13px;height:1px;background:currentColor;left:-2px;top:8px;transform:rotate(-38deg);transform-origin:left center}
.photo-preview{height:176px;margin-top:0;border-radius:20px;background:linear-gradient(150deg,#f0f3fc,#f7f7fc 55%,#f2eff9)}
.photo-placeholder{gap:12px;color:#666276;font-size:15px;line-height:1.5}
.capture-camera-tile{display:flex;align-items:center;justify-content:center;width:44px;height:44px;border-radius:13px;color:#fff;background:linear-gradient(140deg,#ffdc85,#ed9e35);box-shadow:inset 1px 1px 1px rgba(255,255,255,.8),0 5px 10px rgba(226,160,62,.17);transform:rotate(-6deg)}
.capture-camera-tile :deep(.app-icon){width:26px!important;height:26px!important;transform:rotate(6deg)}
.photo-placeholder .capture-photo-caption{margin-top:-6px;font-size:11px;line-height:1.6;color:#858191}
.photo-actions{gap:10px;margin:14px 0 0}
.photo-actions button{min-width:0;min-height:48px;padding:0 8px;gap:8px;border-radius:16px;font-size:14px;font-weight:400;line-height:1.5;box-shadow:none}
.photo-actions .capture-primary{background:var(--ui-accent);color:#fff;border:1px solid var(--ui-accent);box-shadow:0 3px 8px rgba(48,55,57,.08)}
.photo-actions .capture-secondary{background:#fff;border:1px solid #e9e7ef;color:#575363}
.photo-actions .capture-primary :deep(.app-icon){width:18px!important;height:18px!important}
.capture-album-glyph{position:relative;display:block;flex:none;width:18px;height:18px}
.capture-album-glyph:before,.capture-album-glyph:after{content:'';position:absolute;width:12px;height:12px;border:1.3px solid currentColor;border-radius:2px}
.capture-album-glyph:before{left:0;top:0;opacity:.6}.capture-album-glyph:after{left:4px;top:4px;background:#fff}
.other-methods{gap:10px;padding:7px 0 12px;margin:0;color:#e6e3ed}
.other-methods button{display:flex;align-items:center;justify-content:center;min-width:0;min-height:44px;padding:0;color:#787384;font-size:12px;line-height:1.5;white-space:nowrap}
.other-methods>text{position:absolute;left:50%;top:7px;bottom:12px;display:flex;align-items:center;transform:translateX(-50%);pointer-events:none;font-size:11px}
.capture-settings{border-top:1px solid #f0eef5;padding-top:18px}
.capture-field-label{display:block;margin-bottom:10px;font-size:12px;line-height:1.5;color:#817b8c}
.scope-grid{gap:4px;padding:4px;background:#f1f1f7;border-radius:15px}
.scope-grid button{min-width:0;min-height:44px;padding:8px 4px;border-radius:12px;color:#817b8c;font-size:13px;line-height:1.5;white-space:nowrap}
.scope-grid .active{background:#fff;color:#46414f;box-shadow:0 2px 6px rgba(75,69,107,.045);font-weight:400}
.member-picks{gap:8px;margin-top:12px}
.member-picks button{min-height:44px;padding:6px 14px;border-color:#eeedf4;color:var(--ui-muted);font-size:12px}
.member-picks .active{background:#f2f0f7;border-color:#dcd6eb;color:#61566e}
.capture-time-label{margin-top:19px}
.meal-time{gap:8px;margin-top:0;padding:2px 10px;min-height:54px;flex-wrap:nowrap;border:1px solid #eeedf4;border-radius:15px;background:#fcfcff;color:var(--ui-text);font-size:13px}
.meal-time> :deep(.app-icon){width:17px!important;height:17px!important;color:#9a91b4}
.meal-time picker{min-width:0;min-height:46px;flex-shrink:0}
.meal-time picker:last-child{margin-left:auto}

.meal-time text{color:#91899f}
.capture-endnote{display:block;text-align:center;margin-top:18px;font-size:11px;line-height:1.6;color:#95909e}
.capture-notice{margin:0 0 14px;color:var(--ui-muted);font-size:12px;line-height:1.7}
.recognition-card{margin:16px 0;padding:16px;border-radius:18px;border-color:#eeedf4;background:#fafaff;color:var(--ui-text);font-size:13px}
.capture-card .safe-note{margin:10px 0;color:var(--ui-muted);font-size:12px}
.capture-card .inline-error{font-size:13px}
.section-heading button,.person-dishes>text:last-child,.text-link{color:#6e617f}
.portion-choices .active,.dish-picks .active,.not-eaten.active{color:#61566e;background:#f2f0f7;border-color:#cfc5df}
.foods-card{padding:0 0 18px;margin-top:22px;border-color:#eeedf4}
.people-card{padding-left:0;padding-right:0}
.save-actions{background:rgba(255,255,255,.98);border-color:#eeedf4}
.save-primary{background:var(--ui-accent)}
.photo-actions button,.scope-grid button{transform:translateY(0) scale(1);transition:transform 180ms cubic-bezier(.2,.9,.3,1.25)}
.capture-card .capture-pressed{transform:translateY(1px) scale(.96);transition:transform 70ms ease-out}
.capture-card button[disabled]{transform:none;transition:none}
/* Strengthen text locally while retaining the existing size and color hierarchy. */
.scan-screen{font-weight:500}
.scan-screen .nav-title,.scan-screen .capture-card-title,.scan-screen .capture-field-label,.scan-screen .meal-time,.scan-screen .photo-placeholder>text:not(.capture-photo-caption){font-weight:600}
.scan-screen button,.scan-screen .scope-grid .active{font-weight:600}
.scan-screen .capture-card-caption,.scan-screen .capture-photo-caption,.scan-screen .capture-endnote,.scan-screen input,.scan-screen textarea{font-weight:500}
@media(max-width:350px){.scan-screen{padding-left:12px;padding-right:12px}.capture-card{padding-left:14px;padding-right:14px;border-radius:25px}.photo-actions button{gap:6px;font-size:13px}.meal-time{gap:6px;padding-left:8px;padding-right:8px;font-size:12px}.other-methods{gap:10px}.scope-grid button{font-size:12px}.portion-choices{min-width:0}}
@media(max-height:480px){.capture-page-wash{height:260px}}
@media(prefers-reduced-motion:reduce){.photo-actions button,.scope-grid button,.capture-card .capture-pressed{transition:none;transform:none}}
/* #ifdef H5 */
.capture-page-wash{max-width:480px;margin-left:auto;margin-right:auto}
/* #endif */

</style>
