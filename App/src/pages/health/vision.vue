<script setup>
import { computed, reactive, ref } from 'vue'
import { onLoad, onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import HealthMealEditor from '../../components/HealthMealEditor.vue'
import { createHealthVisionClient, visionState } from '../../services/health-vision-client.js'
import { newHealthRequestId } from '../../services/health-task-flow.js'
import { sessionRevision } from '../../services/session.js'
import { previewMealPhoto } from '../../services/health-upload.js'
const state = reactive(visionState()), route = ref({}), files = ref([]), payload = ref(null), reason = ref(''), accept = ref(false), consent = ref(false)
const client = createHealthVisionClient({ state })
const previewPath=ref('')
const title = computed(() => state.kind === 'report' ? '报告上传与核对' : '饮食照片与核对')
const dirty = computed(() => !!payload.value && JSON.stringify(payload.value) !== JSON.stringify(state.draft?.payload))
const statuses = { pending: '等待处理', running: '正在处理', success: '处理完成', failed: '处理失败', cancelled: '已取消' }
let selecting = false, pickerHidden = false, pageRevision = '', alive = true
onLoad(options => { route.value = { memberId: options.memberId || '', kind: options.kind === 'meal' ? 'meal' : 'report' } })
onShow(() => {
  alive = true
  if ((selecting || pickerHidden) && pageRevision === sessionRevision()) { pickerHidden = false; return }
  pageRevision = sessionRevision(); files.value = []; payload.value = null; previewPath.value=''; consent.value = false
  void client.open(route.value.memberId, route.value.kind)
})
function hide() { if (selecting) { pickerHidden = true; return }; alive = false; client.discard(); files.value = []; payload.value = null; previewPath.value='' }
onHide(hide); onUnload(() => { selecting = false; pickerHidden = false; hide() })
function pick(file = false) {
  if (state.busy || state.pending) return
  selecting = true; const revision = sessionRevision()
  const done = result => {
    if (alive && revision === sessionRevision()) files.value = (result.tempFiles || []).map(item => ({ path: item.path || item.tempFilePath, name: item.name || '照片', size: item.size }))
    selecting = false
  }
  const fail = error => { selecting = false; if (alive && revision === sessionRevision() && !/cancel/i.test(error.errMsg || '')) state.error = '选择文件失败，请检查权限后重试。' }
  if (file && typeof uni.chooseMessageFile === 'function') uni.chooseMessageFile({ count: state.kind === 'meal' ? 3 : 20, type: 'file', extension: state.kind === 'meal' ? ['jpg', 'jpeg', 'png', 'webp'] : ['pdf', 'jpg', 'jpeg', 'png', 'webp'], success: done, fail })
  else if (file && typeof uni.chooseFile === 'function') uni.chooseFile({ count: state.kind === 'meal' ? 3 : 20, type: 'all', extension: state.kind === 'meal' ? ['.jpg', '.jpeg', '.png', '.webp'] : ['.pdf', '.jpg', '.jpeg', '.png', '.webp'], success: done, fail })
  else if (file) { selecting = false; state.error = '当前环境不支持微信聊天文件，请使用照片或手动录入。' }
  else uni.chooseImage({ count: state.kind === 'meal' ? 3 : 9, sourceType: ['camera', 'album'], sizeType: ['original'], success: done, fail })
}
function editCurrent() { payload.value = state.draft ? JSON.parse(JSON.stringify(state.draft.payload)) : null; reason.value = ''; accept.value = false;previewPath.value='' }
async function draft(row) { await client.draft(row); editCurrent() }
async function manual() { await client.manual(); editCurrent() }
async function readJob(row) { await client.readJob(row); if (state.draft) editCurrent() }
async function save() { await client.saveDraft(payload.value, reason.value); if (!state.blocked && !state.error) editCurrent() }
function addField() { payload.value.fields.push({ field_id: newHealthRequestId(), name: '', value_raw: '', value_numeric: null, unit_raw: '', reference_raw: '', source: 'manual', observation_code: 'unknown', evidence: null, excluded: false }) }
function excludePage(index, excluded) {
  const current = new Set(payload.value.excluded_pages || [])
  excluded ? current.add(index) : current.delete(index)
  payload.value.excluded_pages = [...current]
}
async function acceptPolicy() { if (consent.value) await client.acceptConsent() }
async function preview(uploadId,pageIndex) {
  const revision=sessionRevision(),draftId=state.draft?.id;previewPath.value=''
  try{const path=await previewMealPhoto(uploadId,pageIndex);if(alive&&revision===sessionRevision()&&state.draft?.id===draftId)previewPath.value=path}
  catch(error){if(alive&&revision===sessionRevision()){state.error=error.message;if([401,403,404,410].includes(Number(error.code))){client.discard();payload.value=null;state.error='原图或授权已失效，请重新读取。'}}}
}
</script>
<template>
  <view class="screen health-vision"><AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack()">‹</button><text class="nav-title">{{title}}</text></view></AppNavBar>
    <view class="page-heading"><text class="display-title">{{state.kind==='report'?'先核对，再保存':'把这一餐，记清楚'}}</text><text class="subtitle">识别内容为待确认候选。仅由你确认后保存正式记录。</text></view>
    <text v-if="state.error" class="inline-error">{{state.error}}</text><text v-if="state.notice" class="safe-note">{{state.notice}}</text><text v-if="state.busy" class="safe-note">正在核对服务端状态…</text>
    <button v-if="!state.members.length" class="secondary-button" :disabled="state.busy" @click="client.open(route.memberId,route.kind)">重新读取授权成员</button>
    <view v-if="state.members.length" class="card section">
      <text class="section-title">记录归属</text><view class="choices"><button v-for="member in state.members" :key="member.id" :class="{active:state.memberId===member.id}" :disabled="state.busy||!!state.pending" @click="files=[];payload=null;consent=false;client.open(member.id,route.kind)">{{member.display_name}}</button></view>
      <template v-if="state.policy&&!state.consent"><text class="helper">{{state.kind==='report'?'报告识别':'饮食照片识别'}}处理方：{{state.policy.processor}}；政策版本：{{state.policy.policy_version}}。</text><checkbox-group @change="consent=$event.detail.value.includes('yes')"><label><checkbox value="yes" :checked="consent"/>我已核对并同意本用途的数据处理</label></checkbox-group><button class="secondary-button" :disabled="!consent||state.busy||!!state.pending" @click="acceptPolicy">确认同意</button></template>
      <text v-if="!state.policy" class="safe-note">识别服务尚未就绪，可以恢复已有任务或手动核对录入。</text>
      <view class="choices"><button class="secondary-button" :disabled="state.busy||!!state.pending" @click="pick()">拍照 / 相册</button><button class="secondary-button" :disabled="state.busy||!!state.pending" @click="pick(true)">微信聊天文件</button></view>
      <text class="helper">静态JPEG／PNG／WebP图片每张不超过{{state.limits.image_mb}}MiB。{{state.kind==='report'?'报告PDF不超过'+state.limits.pdf_mb+'MiB，最多'+state.limits.report_pages+'页。':'同餐最多'+state.limits.meal_images+'张照片。'}}</text>
      <text v-for="(file,index) in files" :key="index" class="helper">{{file.name}} · {{file.uploadId?'已上传，可复用':'待上传'}}</text><text v-if="state.busy&&files.length" class="helper">当前文件上传 {{state.progress}}%</text>
      <button class="primary-button" :disabled="state.busy||!files.length||!state.consent||!!state.pending" @click="client.recognize(files)">上传并识别</button>
      <button v-if="state.uploading" class="secondary-button" @click="client.cancelUpload()">取消当前文件上传</button>
      <button class="secondary-button" :disabled="state.busy||!!state.pending||state.blocked" @click="manual">手动录入候选</button>
      <button v-if="state.pending" class="primary-button" :disabled="state.busy" @click="client.retryPending()">用原请求确认上次操作</button><text v-if="state.pending" class="helper">上次提交结果尚未确认；原请求保留，请勿另建相同记录。</text>
    </view>
    <view v-if="state.memberId" class="card section"><text class="section-title">识别任务</text><button class="secondary-button" :disabled="state.busy" @click="client.page(0,0)">刷新 / 恢复任务与候选</button><text v-if="!state.jobs.length&&!state.busy&&!state.error" class="helper">本页暂无可读取的识别任务。</text>
      <view v-for="job in state.jobs" :key="job.task_id" class="job"><text>{{statuses[job.execution_status]||job.execution_status}} · {{Math.round((job.progress||0)*100)}}%</text><text v-if="job.error_code" class="inline-error">{{job.error_code}}；可重试或手动录入</text><view class="choices"><button :disabled="state.busy" @click="readJob(job)">读取进度 / 核对候选</button><button v-if="['pending','running'].includes(job.execution_status)" :disabled="state.busy" @click="client.cancel(job)">取消任务</button><button v-if="['failed','cancelled'].includes(job.execution_status)" :disabled="state.busy||!!state.pending" @click="client.retry(job)">明确重试识别</button></view></view>
      <view class="choices"><button :disabled="state.busy||state.jobsOffset===0" @click="client.page(Math.max(0,state.jobsOffset-20),state.draftsOffset)">上一页任务</button><button :disabled="state.busy||state.jobsNext===null" @click="client.page(state.jobsNext,state.draftsOffset)">下一页任务</button></view>
      <text class="section-title">已生成候选</text><button v-for="row in state.drafts" :key="row.id" class="secondary-button" :disabled="state.busy||!!state.pending" @click="draft(row)">候选 v{{row.version}} · {{row.review_status==='confirmed'?'已确认':'待核对'}} · {{row.created_at?.slice(0,10)}}</button><view class="choices"><button :disabled="state.busy||state.draftsOffset===0" @click="client.page(state.jobsOffset,Math.max(0,state.draftsOffset-20))">上一页候选</button><button :disabled="state.busy||state.draftsNext===null" @click="client.page(state.jobsOffset,state.draftsNext)">下一页候选</button></view>
    </view>
    <view v-if="state.draft&&payload" class="card section"><text class="section-title">核对候选 · v{{state.draft.version}}</text><text v-if="state.draft.review_status==='confirmed'" class="safe-note">该候选已确认；更正饮食请进入已保存记录。</text>
      <image v-if="previewPath" :src="previewPath" mode="widthFix" style="width:100%"/>
      <button v-for="photo in payload.photos||[]" :key="photo.upload_id" class="secondary-button" :disabled="state.busy" @click="preview(photo.upload_id)">核对原照片 {{photo.image_index+1}}</button>
      <HealthMealEditor v-if="state.kind==='meal'" :meal="payload" :disabled="state.busy||!!state.pending||state.blocked||state.draft.review_status==='confirmed'" :recipes="state.recipes" @search="client.searchRecipes"/>
      <template v-else><view v-for="page in payload.pages||[]" :key="page.page_index" class="job"><text>第{{page.page_index+1}}页 · {{page.status==='failed'?'识别失败，可重新识别或明确排除':'已处理'}}</text><button class="secondary-button" :disabled="state.busy" @click="preview(page.upload_id,page.upload_page_index)">核对这一页原图</button><button v-if="page.status==='failed'&&state.draft.review_status==='pending_confirmation'" class="secondary-button" :disabled="state.busy||dirty||!!state.pending||state.blocked" @click="client.reprocessPages([page.page_index])">重新识别这一页</button><label><switch :checked="(payload.excluded_pages||[]).includes(page.page_index)" :disabled="state.busy||!!state.pending||state.blocked||state.draft.review_status==='confirmed'" @change="excludePage(page.page_index,$event.detail.value)"/>排除此页，不保存该页指标</label></view>
        <view v-for="field in payload.fields" :key="field.field_id" class="job"><text v-if="field.evidence" class="helper">原文：{{field.evidence.raw_text}} · 第{{field.evidence.page_index+1}}页</text><text class="helper">{{field.source==='ocr'?'识别候选，待人工核对':'人工录入'}}</text><input v-model="field.name" class="field-input" placeholder="指标名称" :disabled="state.busy||!!state.pending||state.blocked||state.draft.review_status==='confirmed'"/><input v-model="field.value_raw" class="field-input" placeholder="报告原始结果" :disabled="state.busy||!!state.pending||state.blocked||state.draft.review_status==='confirmed'" @input="field.value_numeric=null"/><input v-model="field.unit_raw" class="field-input" placeholder="报告单位" :disabled="state.busy||!!state.pending||state.blocked||state.draft.review_status==='confirmed'"/><input v-model="field.reference_raw" class="field-input" placeholder="报告参考范围" :disabled="state.busy||!!state.pending||state.blocked||state.draft.review_status==='confirmed'"/><label><switch :checked="!field.excluded" :disabled="state.busy||!!state.pending||state.blocked||state.draft.review_status==='confirmed'" @change="field.excluded=!$event.detail.value"/>保留这一项</label></view><button class="secondary-button" :disabled="state.busy||!!state.pending||state.blocked||state.draft.review_status==='confirmed'" @click="addField">添加人工指标</button>
      </template>
      <template v-if="state.draft.review_status!=='confirmed'"><textarea v-model="reason" class="text-area" placeholder="填写核对与修改原因" :disabled="state.busy||!!state.pending||state.blocked"/><button class="secondary-button" :disabled="state.busy||!reason.trim()||!!state.pending||state.blocked" @click="save">保存候选修改</button><button :disabled="state.busy||!!state.pending" class="secondary-button" @click="draft(state.draft)">重新读取候选，核对当前版本</button>
        <button v-if="state.kind==='meal'" class="secondary-button" :disabled="state.busy||dirty||state.blocked||!!state.pending" @click="client.calculate()">计算已保存候选的营养</button><text v-if="state.calculation" class="helper">当前预览：{{state.calculation.totals.energy_kcal??'未知'}} kcal · {{state.calculation.complete?'数据完整':'存在缺失，不能当作零值'}}</text><label v-if="state.kind==='meal'"><switch :checked="accept" :disabled="state.busy||!!state.pending" @change="accept=$event.detail.value"/>接受缺失营养保持未知</label>
        <text v-if="dirty" class="helper">有未保存修改，请先保存候选，再确认正式记录。</text><button class="primary-button" :disabled="state.busy||dirty||state.blocked||!!state.pending||(state.kind==='meal'&&!state.calculation)" @click="client.confirm(accept)">已核对，确认保存正式记录</button>
      </template>
    </view>
    <text v-if="state.confirmation" class="safe-note">保存成功，共{{state.confirmation.target_ids.length}}条。饮食记录可在“实际饮食记录”中查看与更正。</text>
  </view>
</template>
<style scoped>.health-vision{padding-bottom:60rpx}.section,.job{display:flex;flex-direction:column;gap:20rpx}.section{padding:28rpx;margin:24rpx 0}.job{padding:22rpx;background:#f6f8f5;border-radius:18rpx}.choices{display:flex;gap:12rpx;flex-wrap:wrap}.choices button{font-size:25rpx;padding:12rpx 18rpx;background:#edf2ed}.choices button.active{background:#292a2e;color:#fff}.helper{font-size:25rpx;color:#63636b;line-height:1.65;word-break:break-word}.safe-note{text-align:left}.section-title{font-size:31rpx;font-weight:500}button[disabled]{opacity:.5}label{font-size:25rpx;line-height:1.7}</style>
