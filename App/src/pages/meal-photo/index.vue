<script setup>
import { reactive, ref, computed, watch } from 'vue'
import { onLoad, onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import { createMealPhotoClient, photoState } from '../../services/meal-photo-client.js'
import { newHealthRequestId } from '../../services/health-task-flow.js'
import { previewMealPhoto } from '../../services/health-upload.js'
import { sessionRevision } from '../../services/session.js'
const state = reactive(photoState()), client = createMealPhotoClient({ state })
const selectedMember = ref(''), consent = ref(false), acceptMissing = ref(false), reason = ref('核对照片中的实际摄入')
const query = ref(''), mappingItem = ref(null), mealType = ref('lunch')
const previewPath = ref('')
const now = new Date(Date.now() + 8 * 3600000).toISOString()
const mealDate = ref(now.slice(0,10)), mealTime = ref(now.slice(11,16))
const types = ['breakfast','lunch','dinner','snack'], labels = ['早餐','午餐','晚餐','加餐']
const statusNames = { pending:'等待识别',running:'识别中',success:'识别完成',completed:'识别完成',failed:'识别失败',cancelled:'已取消' }
let pageGeneration=0, mediaOverlay=false, openedRevision=''
const locked = computed(() => state.busy || !!state.pending)
const editable = computed(() => state.draft?.review_status === 'pending_confirmation' && !locked.value && !state.conflict)
const canRecognize = computed(() => state.config?.meal?.available && state.members.find(m=>m.id===state.memberId)?.scopes?.includes('ai_use'))
watch(() => [state.memberId,state.draft?.id,state.draft?.version], () => {previewPath.value='';acceptMissing.value=false;mappingItem.value=null}, {flush:'sync'})
watch(() => state.calculation, () => {acceptMissing.value=false}, {flush:'sync'})
onLoad(options => { selectedMember.value = options.memberId || '' })
onShow(() => {
  if(state.memberId && openedRevision===sessionRevision())return
  openedRevision=sessionRevision(); consent.value=false; acceptMissing.value=false; mappingItem.value=null; void client.open(selectedMember.value)
})
function hide() { pageGeneration++; client.discard(); consent.value=false; acceptMissing.value=false; mappingItem.value=null; previewPath.value='' }
onHide(() => { if(!mediaOverlay)hide() }); onUnload(hide)
function selectMember(id) { if(locked.value)return; selectedMember.value=id; consent.value=false; acceptMissing.value=false; mappingItem.value=null; void client.open(id) }
function pickPhoto() {
  if(locked.value || state.uploads.length>=3)return
  const member = state.memberId
  mediaOverlay=true
  uni.chooseImage({ count:1,sizeType:['compressed'],sourceType:['album','camera'],
    success: result => { if(state.memberId===member && result.tempFilePaths?.[0])void client.addPhoto(result.tempFilePaths[0]) },
    fail: e => { if(!/cancel/i.test(e.errMsg||''))state.error='无法读取照片，请检查相机或相册权限' },
    complete: () => { mediaOverlay=false },
  })
}
function changed() { client.changed(); acceptMissing.value=false }
function number(item, field, value) { item[field]=value===''?null:Number(value); if(field==='grams'){item.portion_reference_id=null;item.portion_count=null;item.portion_source=value===''?'unknown':'manual'} changed() }
function addItem() { if(!editable.value)return; state.meal.items.push({item_id:newHealthRequestId(),name:'未命名食物',grams:null,share_ratio:null,portion_source:'unknown',locations:[],candidates:[],uncertainties:[],visible_ingredients:[],adjustments:[],excluded:false});changed() }
function search(item) { mappingItem.value=item.item_id;query.value=item.name;void client.search(query.value) }
function mapSource(source) {
  if(!editable.value)return
  const item=state.meal.items.find(i=>i.item_id===mappingItem.value);if(!item)return
  item.food_id=source.type==='food'?source.id:null;item.recipe_version_id=source.type==='recipe'?source.id:null
  item.portion_reference_id=null;item.portion_count=null;item.adjustments=[];item.portion_source=item.grams?'manual':'unknown'
  mappingItem.value=null;changed()
}
async function start() { await client.start(mealType.value,`${mealDate.value}T${mealTime.value}:00+08:00`,consent.value); if(state.error)consent.value=false }
function records() { uni.navigateTo({url:'/pages/records/index'}) }
async function preview(id) { previewPath.value='';const epoch=pageGeneration,member=state.memberId;try{const path=await previewMealPhoto(id);if(epoch===pageGeneration&&member===state.memberId)previewPath.value=path}catch(e){if(epoch===pageGeneration)state.error=e.message} }
</script>
<template>
<view class="screen photo-flow">
  <AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack()">‹</button><text class="nav-title">拍照记餐</text></view></AppNavBar>
  <text class="display-title">核对后再记入饮食</text>
  <view v-if="previewPath" class="card section"><image :src="previewPath" mode="widthFix" style="width:100%"/><button @click="previewPath=''">关闭原图</button></view>
  <text class="safe-note">同一餐最多3张照片。识别只提供食物候选，实际份量由你核对，营养按已发布数据计算。</text>
  <text v-if="state.error" class="inline-error" role="alert">{{state.error}}</text><text v-if="state.notice" class="safe-note">{{state.notice}}</text>
  <text v-if="state.busy" class="safe-note">正在处理，请稍候…</text>
  <button v-if="!state.members.length" class="secondary-button" :disabled="state.busy" @click="client.open(selectedMember)">重新读取授权成员</button>
  <view class="choices"><button v-for="m in state.members" :key="m.id" :disabled="locked" :class="{active:m.id===state.memberId}" @click="selectMember(m.id)">{{m.display_name||m.name||m.relationship_label}}</button></view>
  <view v-if="state.memberId" class="card section">
    <text class="section-title">1. 上传同一餐照片</text>
    <picker :range="labels" :disabled="locked" @change="mealType=types[$event.detail.value]"><view class="field-input">{{labels[types.indexOf(mealType)]}} ›</view></picker>
    <picker mode="date" :value="mealDate" :disabled="locked" @change="mealDate=$event.detail.value"><view class="field-input">就餐日期 {{mealDate}} ›</view></picker>
    <picker mode="time" :value="mealTime" :disabled="locked" @change="mealTime=$event.detail.value"><view class="field-input">北京时间 {{mealTime}} ›</view></picker>
    <view v-for="(photo,index) in state.uploads" :key="photo.upload_id" class="choices"><button :disabled="locked" @click="preview(photo.upload_id)">查看照片 {{index+1}}</button><button :disabled="locked" @click="client.removePhoto(photo.upload_id)">从本次识别移除</button></view>
    <button class="secondary-button" :disabled="locked||state.uploads.length>=3" @click="pickPhoto">拍照或选择照片（{{state.uploads.length}}/3）</button>
    <text v-if="!canRecognize" class="safe-note">{{state.config?.meal?.reason||'需要成员 AI 使用授权'}}。可以查看已有任务和候选，或前往饮食记录人工记餐。</text>
    <template v-else><text class="safe-note">处理方 {{state.config.meal.processor}} · 政策 {{state.config.policy_version}}</text><label><switch :checked="consent" :disabled="locked" @change="consent=$event.detail.value"/>同意将本成员本餐照片交给上述服务识别</label></template>
    <button class="primary-button" :disabled="locked||!canRecognize||!consent||!state.uploads.length" @click="start">提交识别任务</button>
    <button class="secondary-button" @click="records">人工记餐 / 查看已确认记录</button>
  </view>
  <view v-if="state.pending" class="card section"><text>上次{{state.pending.operation==='confirm'?'确认记餐':state.pending.operation==='patch'?'保存候选':'任务提交'}}结果尚未确认，请恢复原请求。</text><button class="primary-button" :disabled="state.busy" @click="client.retryPending()">恢复原请求</button></view>
  <view v-if="state.memberId" class="card section">
    <text class="section-title">2. 查看识别任务和候选</text>
    <button v-for="job in state.jobs" :key="job.task_id" :disabled="locked||state.dirty" class="secondary-button" @click="client.job(job.task_id)">{{statusNames[job.execution_status]||job.execution_status}} · {{job.created_at}}</button>
    <view class="choices"><button :disabled="locked||state.jobsOffset===0" @click="client.page('jobs',Math.max(0,state.jobsOffset-20))">上一页任务</button><button :disabled="locked||state.jobsNext===null" @click="client.page('jobs',state.jobsNext)">下一页任务</button><button :disabled="locked" @click="client.page('jobs',0)">刷新任务</button></view>
    <view v-if="state.job" class="section"><text>当前任务：{{statusNames[state.job.execution_status]||state.job.execution_status}} {{state.job.progress}}%</text><text v-if="state.job.error_code">失败原因：{{state.job.error_code}}</text><text v-if="state.job.cancel_requested">已请求取消，最终状态以服务端为准。</text>
      <button :disabled="locked||state.dirty" @click="client.job(state.job.task_id)">刷新当前任务</button><button v-if="['pending','running'].includes(state.job.execution_status)" :disabled="locked" @click="client.cancel()">取消识别</button><button v-if="['failed','cancelled'].includes(state.job.execution_status)" :disabled="locked||!canRecognize" @click="client.retryJob()">重新尝试识别</button>
    </view>
    <button v-for="draft in state.drafts" :key="draft.id" class="secondary-button" :disabled="locked||state.dirty" @click="client.draft(draft.id)">{{draft.review_status==='confirmed'?'已确认':'待核对'}} · v{{draft.version}} · {{draft.created_at}}</button>
    <view class="choices"><button :disabled="locked||state.draftsOffset===0" @click="client.page('drafts',Math.max(0,state.draftsOffset-20))">上一页候选</button><button :disabled="locked||state.draftsNext===null" @click="client.page('drafts',state.draftsNext)">下一页候选</button></view>
  </view>
  <view v-if="state.draft&&state.meal" class="section">
    <text class="section-title">3. 核对食物和实际份量 · v{{state.draft.version}}</text>
    <text>{{labels[types.indexOf(state.meal.meal_type)]}} · {{state.meal.eaten_at}}</text>
    <view class="choices"><button v-for="photo in state.meal.photos" :key="photo.upload_id" :disabled="locked" @click="preview(photo.upload_id)">核对原图 {{photo.image_index+1}}</button></view>
    <text class="safe-note">未看见不代表没有油、糖或隐藏配料。克数填写整份食物的可食重量；本人比例填0到1，全部吃完填1。未知保持空白。</text>
    <text v-if="state.draft.review_status==='confirmed'">这份候选已确认，修改请前往饮食记录。</text>
    <view v-for="item in state.meal.items" :key="item.item_id" class="card section">
      <input v-model="item.name" :disabled="!editable" class="field-input" placeholder="食物名称" maxlength="120" @input="changed"/>
      <text v-if="item.candidates?.length">可能名称：{{item.candidates.join('、')}}</text><text>做法：{{item.cooking_method||'未知'}}</text>
      <text v-if="item.visible_ingredients?.length">可见食材：{{item.visible_ingredients.join('、')}}</text><text v-if="item.uncertainties?.length" class="safe-note">待核实：{{item.uncertainties.join('；')}}</text>
      <label><switch :checked="item.excluded" :disabled="!editable" @change="item.excluded=$event.detail.value;changed()"/>不计入本次摄入</label>
      <template v-if="!item.excluded"><text>可食重量（克）</text><input :value="item.grams??''" type="digit" class="field-input" :disabled="!editable" placeholder="未知留空" @input="number(item,'grams',$event.detail.value)"/><text>本人吃的比例（0–1）</text><input :value="item.share_ratio??''" type="digit" class="field-input" :disabled="!editable" placeholder="未知留空" @input="number(item,'share_ratio',$event.detail.value)"/>
        <text>{{item.recipe_version_id?'已匹配菜谱版本':item.food_id?'已匹配食品版本':'未匹配营养数据，营养保持未知'}}</text><button class="secondary-button" :disabled="!editable" @click="search(item)">选择食品或菜谱数据</button>
      </template>
    </view>
    <view v-if="mappingItem" class="card section"><input v-model="query" class="field-input" placeholder="搜索食品或菜谱"/><button :disabled="locked" @click="client.search(query)">搜索</button><button v-for="source in state.sources" :key="source.type+source.id" :disabled="!editable" @click="mapSource(source)">{{source.name}} · {{source.cooking_state}} · {{source.dataset_version}}（{{source.type==='food'?'食品':'菜谱'}}）</button><text v-if="!state.sources.length">暂无匹配数据，可保留未知。</text></view>
    <button :disabled="!editable||state.meal.items.length>=30" class="secondary-button" @click="addItem">补充漏识别的食物</button>
    <textarea v-model="reason" class="field-input" :disabled="!editable" placeholder="核对或修改原因" maxlength="500"/>
    <button class="primary-button" :disabled="!editable||!state.dirty||!reason.trim()" @click="client.saveDraft(reason)">保存核对结果</button>
    <button v-if="state.conflict||state.dirty" class="secondary-button" :disabled="locked" @click="client.draft(state.draft.id)">放弃本地修改并读取当前版本</button>
    <button class="primary-button" :disabled="!editable||state.dirty" @click="client.calculate()">计算当前版本营养</button>
  </view>
  <view v-if="state.calculation" class="card section"><text class="section-title">4. 确认记餐</text><text>能量 {{state.calculation.totals.energy_kcal??'未知'}} kcal · 蛋白质 {{state.calculation.totals.protein_g??'未知'}} g</text><text v-if="!state.calculation.complete">有营养或份量信息缺失，未知不计为零。</text><label v-if="!state.calculation.complete"><switch :checked="acceptMissing" :disabled="locked" @change="acceptMissing=$event.detail.value"/>接受不完整记录，缺失项保持未知</label><text>请确认这是本成员实际吃过的一餐。</text><button class="primary-button" :disabled="locked||state.dirty||(!state.calculation.complete&&!acceptMissing)" @click="client.confirm(acceptMissing)">确认并保存饮食记录</button></view>
  <view v-if="state.saved" class="card section"><text>确认已成功，记录已保存。</text><text v-if="state.saved.source_version">当前版本 {{state.saved.source_version}} · {{state.saved.snapshot?.nutrition?.totals?.energy_kcal??'未知'}} kcal</text><button @click="records">查看正式饮食记录</button></view>
</view>
</template>
<style scoped>
.photo-flow,.section{display:flex;flex-direction:column;gap:22rpx}.photo-flow{padding-bottom:80rpx}.section{padding:24rpx}.choices{display:flex;flex-wrap:wrap;gap:14rpx;align-items:center}.choices button{background:#eef0e8;padding:12rpx;font-size:24rpx;border-radius:12rpx}.choices .active{background:#246b50;color:white}.safe-note{text-align:left}.field-input{width:100%;box-sizing:border-box}.section text{overflow-wrap:anywhere}button[disabled]{opacity:.5}
</style>
