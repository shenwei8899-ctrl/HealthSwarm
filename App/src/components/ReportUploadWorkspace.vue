<script setup>
import { computed, ref } from 'vue'
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'
import { visionPermissions } from '../services/health-vision-client.js'
import { reportRecognitionError } from '../services/report-recognition-error.js'

const props = defineProps({ state: Object, files: Array, payload: Object, reason: String, consent: Boolean, previewPath: String, dirty: Boolean })
const emit = defineEmits(['back', 'reload', 'member', 'pick', 'remove', 'recognize', 'manual', 'recover', 'configuration', 'page', 'job', 'cancel', 'retry', 'draft', 'preview', 'reprocess', 'exclude', 'add-field', 'save', 'confirm', 'new-report', 'update:reason', 'update:consent'])
const historyOpen = ref(false)
const permissions = computed(() => visionPermissions(props.state))
const member = computed(() => props.state.members.find(row => row.id === props.state.memberId))
const ready = computed(() => props.state.memberStatus === 'ready')
const stage = computed(() => props.state.confirmation ? 'saved' : props.state.draft && props.payload ? 'review' : props.state.job || props.state.pending ? 'processing' : 'upload')
const step = computed(() => stage.value === 'saved' ? 3 : ['review', 'processing'].includes(stage.value) ? 2 : 1)
const locked = computed(() => props.state.busy || !!props.state.pending)
const editable = computed(() => permissions.value.edit && !locked.value && !props.state.blocked && props.state.draft?.review_status !== 'confirmed')
const canPick = computed(() => ready.value && permissions.value.upload && !locked.value)
const canRecognize = computed(() => canPick.value && permissions.value.recognize && !!props.state.policy && !!props.files.length && (props.consent || props.state.consent))
const status = computed(() => ({
  idle: ['正在准备报告上传', '请稍候，正在确认报告归属。'],
  loading: ['正在读取成员', '正在确认报告归属，请稍候。'],
  failed: ['暂时无法读取成员', '请检查网络后重新加载，稍后也可以继续上传。'],
  empty: ['暂无可用的报告成员', '请返回家庭档案核对成员资料和家庭关系。'],
  'selection-required': ['请选择报告所属成员', '原成员当前不可用，请选择下方有权限的成员。'],
  revoked: ['成员资料或授权已变化', '请重新读取成员，再继续核对报告。'],
}[props.state.memberStatus] || ['', '']))
const jobLabels = { pending: '等待识别', running: '正在识别', success: '识别完成', failed: '识别失败', cancelled: '已取消' }
const activeCount = computed(() => props.state.jobs.filter(row => ['pending', 'running'].includes(row.execution_status)).length + props.state.drafts.filter(row => row.review_status !== 'confirmed').length)
function chooseMember(event) { const row = props.state.members[Number(event.detail.value)]; if (row && row.id !== props.state.memberId) emit('member', row.id) }
function page(jobs, drafts) { emit('page', jobs, drafts) }
</script>

<template>
  <view class="screen report-workspace">
    <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="emit('back')">‹</button><text class="nav-title">上传报告</text></view></AppNavBar>
    <view class="report-heading"><text class="report-title">{{stage==='review'?'核对报告指标':stage==='saved'?'报告已存入档案':'上传体检报告'}}</text><text class="report-subtitle">{{stage==='review'?'对照原报告确认结果，再保存到成员档案。':stage==='saved'?'每一项健康记录，都归属对应的家庭成员。':'拍下报告或导入文件，核对后存入成员档案。'}}</text></view>
    <view class="report-steps" aria-label="上传、核对、保存"><view v-for="(label,index) in ['上传报告','核对指标','保存档案']" :key="label" :class="{'is-current':step===index+1,'is-complete':step>index+1}"><text class="step-dot">{{step>index+1?'✓':index+1}}</text><text>{{label}}</text></view></view>

    <view v-if="!ready" class="report-card member-state" role="status">
      <view class="state-symbol"><AppIcon name="family" :size="48"/></view><text class="card-title">{{status[0]}}</text><text class="report-note">{{status[1]}}</text>
      <view v-if="state.memberStatus==='selection-required'" class="member-options"><button v-for="row in state.members" :key="row.id" :disabled="state.busy" @click="emit('member',row.id)">{{row.display_name}} ›</button></view>
      <template v-else-if="!['idle','loading'].includes(state.memberStatus)"><button class="secondary-button" :disabled="state.busy" @click="emit('reload')">重新加载成员</button><button v-if="state.memberStatus==='empty'" class="text-action" @click="emit('back')">返回家庭档案 ›</button></template>
    </view>
    <view v-else class="report-member"><view><text class="member-label">报告归属</text><text class="member-name">{{member?.display_name}}</text></view><picker :range="state.members.map(row=>row.display_name)" :value="state.members.findIndex(row=>row.id===state.memberId)" :disabled="locked" @change="chooseMember"><view class="member-switch">切换成员 ›</view></picker></view>
    <text v-if="state.error" class="report-error" role="alert">{{state.error}}</text>
    <view v-if="state.pending&&ready" class="report-card recovery-card"><text class="card-title">继续上次操作</text><text class="report-note">上次提交的结果尚未确认，继续读取即可，无需重复上传。</text><button class="primary-button" :disabled="state.busy" @click="emit('recover')">{{state.busy?'正在确认…':'确认上次操作结果'}}</button></view>

    <template v-if="stage==='upload'||!ready">
      <view class="report-card upload-card">
        <view class="section-heading"><text class="card-title">添加报告</text><text class="section-caption">图片 / PDF</text></view>
        <button class="upload-source" :disabled="!canPick" @click="emit('pick',false)"><view class="source-symbol"><AppIcon name="camera" :size="42"/></view><view class="source-copy"><text>拍照或从相册选择</text><text>保持文字清晰，完整拍下报告页</text></view><text class="source-arrow">›</text></button>
        <button class="upload-source" :disabled="!canPick" @click="emit('pick',true)"><view class="source-symbol"><AppIcon name="record" :size="42"/></view><view class="source-copy"><text>从微信聊天导入</text><text>选择聊天中的报告图片或 PDF</text></view><text class="source-arrow">›</text></button>
        <view v-for="(file,index) in files" :key="index" class="selected-file"><AppIcon name="record" :size="32"/><view><text>{{file.name}}</text><text>{{file.uploadId?'已上传，可继续识别':'已选择，等待上传'}}</text></view><button :disabled="locked" aria-label="移除文件" @click="emit('remove',index)">×</button></view>
        <text class="file-limits">图片每张 ≤ {{state.limits.image_mb}} MiB；PDF ≤ {{state.limits.pdf_mb}} MiB，最多 {{state.limits.report_pages}} 页。</text>
      </view>
      <template v-if="ready">
        <text v-if="!permissions.upload" class="permission-note">{{permissions.view?'当前成员仅开放报告查看。上传新报告需要报告上传授权。':'当前成员尚未开放报告上传授权，请确认成员权限后继续。'}}</text>
        <text v-else-if="!permissions.recognize" class="permission-note">当前成员的报告访问不可用，请重新读取家庭成员。</text>
        <view v-if="!state.policy" class="service-note"><text>{{state.configurationError||'正在检查识别服务…'}}</text><button :disabled="locked" @click="emit('configuration')">重新检查 ›</button></view>
        <view v-if="state.policy&&permissions.recognize" class="processing-policy">
          <checkbox-group @change="emit('update:consent',$event.detail.value.includes('yes'))"><label><checkbox value="yes" color="#75658c" :checked="consent||state.consent" :disabled="locked||state.consent"/><text>{{state.consent?'已同意本次报告识别':'同意本次报告识别的数据处理'}}</text></label></checkbox-group>
        </view>
      </template>
      <view v-if="state.uploading" class="upload-progress" role="status"><text>正在上传文件 · {{state.progress}}%</text><progress :percent="state.progress" activeColor="#75658c" backgroundColor="#eae8f0" stroke-width="3"/><button class="text-action" @click="emit('cancel','upload')">取消上传</button></view>
      <button class="primary-button upload-primary" :disabled="!canRecognize" @click="emit('recognize')">{{state.busy?'正在处理…':'开始识别'}}</button>
      <text class="save-note">识别结果经你核对后，才会保存。</text>
      <button v-if="ready&&permissions.edit" class="text-action manual-action" :disabled="locked||state.blocked" @click="emit('manual')">也可以手动录入指标 ›</button>
    </template>

    <view v-if="ready&&stage==='processing'&&!state.pending" class="report-card task-state">
      <view class="state-symbol"><AppIcon name="record" :size="48"/></view><text class="card-title">{{jobLabels[state.job?.execution_status]||'报告已提交'}}</text><text class="report-note">{{state.job?.execution_status==='success'?'识别结果已准备好，请继续核对。':['failed','cancelled'].includes(state.job?.execution_status)?'可以重试识别，或手动录入报告指标。':'你可以稍后回来，在历史任务中继续核对。'}}</text>
      <text v-if="state.notice" class="report-note">{{state.notice}}</text><text v-if="state.job?.error_code" class="report-error">{{reportRecognitionError(state.job.error_code)}}</text>
      <template v-if="permissions.view"><button class="primary-button" :disabled="locked" @click="emit('job',state.job)">{{state.job?.execution_status==='success'?'查看并核对结果':'刷新识别进度'}}</button><button v-if="['pending','running'].includes(state.job?.execution_status)&&permissions.edit" class="text-action" :disabled="locked" @click="emit('cancel',state.job)">取消这次识别</button><button v-if="['failed','cancelled'].includes(state.job?.execution_status)&&permissions.recognize&&permissions.edit" class="secondary-button" :disabled="locked" @click="emit('retry',state.job)">重新识别</button></template>
      <text v-else class="report-note">报告已提交。查看识别结果还需要报告查看授权。</text>
      <button v-if="permissions.edit&&['failed','cancelled'].includes(state.job?.execution_status)" class="text-action" :disabled="locked||state.blocked" @click="emit('manual')">手动录入指标 ›</button>
    </view>

    <view v-if="ready&&stage==='review'" class="report-review">
      <view class="section-heading"><text class="card-title">报告指标</text><text class="section-caption">{{state.draft.review_status==='confirmed'?'已保存':'待你核对'}}</text></view>
      <text v-if="!permissions.edit" class="permission-note">当前可查看报告；修改和保存指标需要档案编辑授权。</text>
      <image v-if="previewPath" class="report-preview" :src="previewPath" mode="widthFix"/>
      <view v-for="reportPage in payload.pages||[]" :key="reportPage.page_index" class="report-card report-page"><view class="section-heading"><text>第 {{reportPage.page_index+1}} 页</text><text class="section-caption">{{reportPage.status==='failed'?'识别未完成':'已识别'}}</text></view><button class="text-action" :disabled="state.busy" @click="emit('preview',reportPage.upload_id,reportPage.upload_page_index)">对照这一页原图 ›</button><button v-if="reportPage.status==='failed'&&state.draft.review_status==='pending_confirmation'&&permissions.recognize" class="secondary-button" :disabled="locked||dirty||state.blocked" @click="emit('reprocess',reportPage.page_index)">重新识别这一页</button><label class="keep-field"><switch color="#75658c" :checked="(payload.excluded_pages||[]).includes(reportPage.page_index)" :disabled="!editable" @change="emit('exclude',reportPage.page_index,$event.detail.value)"/><text>排除此页，不保存该页指标</text></label></view>
      <view v-for="field in payload.fields||[]" :key="field.field_id" class="report-card indicator-card"><view class="section-heading"><text class="card-title">{{field.name||'新增指标'}}</text><text class="section-caption">{{field.source==='ocr'?'识别结果':'手动录入'}}</text></view><text v-if="field.evidence" class="evidence">原文：{{field.evidence.raw_text}} · 第 {{field.evidence.page_index+1}} 页</text>
        <text class="field-label">指标名称</text><input v-model="field.name" class="field-input" placeholder="如：空腹血糖" :disabled="!editable" aria-label="指标名称"/>
        <view class="indicator-values"><text class="field-label">报告结果</text><textarea v-model="field.value_raw" class="text-area report-result" auto-height :maxlength="500" placeholder="按报告原文填写" :disabled="!editable" :aria-label="field.review_flags?.includes('checkbox_layout_unverified')?'报告勾选结果':'报告结果'" @input="field.value_numeric=null"/><text v-if="field.review_flags?.includes('checkbox_layout_unverified')" class="report-note">保留原表勾选文字，请对照原图核对左右耳及合并单元格。</text></view>
        <text class="field-label">报告参考范围</text><input v-model="field.reference_raw" class="field-input" placeholder="按报告填写，可留空" :disabled="!editable" aria-label="报告参考范围"/>
        <label class="keep-field"><switch color="#75658c" :checked="!field.excluded" :disabled="!editable" @change="field.excluded=!$event.detail.value"/><text>保留这一项指标</text></label>
      </view>
      <button v-if="permissions.edit&&state.draft.review_status!=='confirmed'" class="secondary-button" :disabled="!editable" @click="emit('add-field')">＋ 添加指标</button>
      <view v-if="permissions.edit&&state.draft.review_status!=='confirmed'" class="review-actions"><template v-if="dirty||state.blocked"><text class="field-label">核对与修改说明</text><textarea :value="reason" class="text-area" placeholder="说明本次核对或修改的原因" :disabled="!editable" @input="emit('update:reason',$event.detail.value)"/><button class="secondary-button" :disabled="!editable||!reason.trim()||!dirty" @click="emit('save')">保存指标修改</button><text class="report-note">修改保存后，再确认存入正式档案。</text></template><button class="text-action" :disabled="locked" @click="emit('draft',state.draft)">重新读取当前报告 ›</button><button class="primary-button" :disabled="!editable||dirty" @click="emit('confirm')">已核对，保存到档案</button></view>
      <text v-else-if="state.draft.review_status==='confirmed'" class="save-note">这份报告已核对并保存。</text>
    </view>
    <view v-if="ready&&stage==='saved'" class="report-card saved-state"><view class="saved-symbol">✓</view><text class="card-title">已保存 {{state.confirmation.target_ids.length}} 项报告指标</text><text class="report-note">已核对并读取正式记录，可返回成员档案查看。</text><button class="primary-button" @click="emit('back')">返回成员档案</button><button class="text-action" :disabled="locked" @click="emit('new-report')">继续上传报告 ›</button></view>

    <template v-if="ready">
      <button v-if="stage!=='upload'&&stage!=='saved'" class="text-action new-report" :disabled="locked" @click="emit('new-report')">上传另一份报告 ›</button>
      <view v-if="permissions.view" class="report-history"><button class="history-toggle" :aria-expanded="historyOpen" @click="historyOpen=!historyOpen"><text>待核对与历史任务<text v-if="activeCount" class="history-count">{{activeCount}}</text></text><text>{{historyOpen?'⌃':'⌄'}}</text></button>
        <view v-if="historyOpen" class="history-body"><button class="text-action" :disabled="state.busy" @click="page(0,0)">{{state.listStatus==='loading'?'正在读取…':'刷新任务与报告'}}</button><text v-if="state.listError" class="report-error">{{state.listError}}</text><text v-if="!state.jobs.length&&!state.drafts.length&&state.listStatus==='ready'" class="report-note">暂无待核对或历史报告。</text>
          <view v-for="job in state.jobs" :key="job.task_id" class="history-row"><view><text>{{jobLabels[job.execution_status]||'报告识别任务'}}</text><text>{{job.created_at?.slice(0,10)||'报告任务'}}</text></view><button :disabled="locked" @click="emit('job',job)">查看 ›</button></view>
          <view v-if="state.jobsOffset>0||state.jobsNext!==null" class="history-pages"><button :disabled="state.busy||state.jobsOffset===0" @click="page(Math.max(0,state.jobsOffset-20),state.draftsOffset)">上一页任务</button><button :disabled="state.busy||state.jobsNext===null" @click="page(state.jobsNext,state.draftsOffset)">下一页任务</button></view>
          <view v-for="row in state.drafts" :key="row.id" class="history-row"><view><text>{{row.review_status==='confirmed'?'已核对报告':'待核对报告'}}</text><text>{{row.created_at?.slice(0,10)}}</text></view><button :disabled="locked" @click="emit('draft',row)">查看 ›</button></view>
          <view v-if="state.draftsOffset>0||state.draftsNext!==null" class="history-pages"><button :disabled="state.busy||state.draftsOffset===0" @click="page(state.jobsOffset,Math.max(0,state.draftsOffset-20))">上一页报告</button><button :disabled="state.busy||state.draftsNext===null" @click="page(state.jobsOffset,state.draftsNext)">下一页报告</button></view>
        </view>
      </view>
    </template>
  </view>
</template>

<style scoped>
.report-workspace{--report-purple:#75658c;--report-line:rgba(116,113,127,.1);background-color:var(--ui-canvas);background-image:radial-gradient(ellipse at 0% 0%,rgba(151,179,238,.28),transparent 60%),radial-gradient(ellipse at 100% 8%,rgba(194,164,229,.25),transparent 62%),linear-gradient(180deg,#eff1fb 0%,#f6f7fa 48%,#eae8f5 100%);background-size:100% 680rpx,100% 800rpx,100% 100%;background-repeat:no-repeat;padding-left:40rpx;padding-right:40rpx;padding-bottom:calc(env(safe-area-inset-bottom) + 40rpx)}
.report-heading{margin:28rpx 0 0}.report-title{display:block;font-size:25px;font-weight:500;line-height:1.45}.report-subtitle{display:block;margin-top:12rpx;font-size:13px;line-height:1.8;color:var(--ui-muted)}
.report-steps{display:flex;justify-content:space-between;gap:10rpx;margin:40rpx 0;font-size:12px;color:var(--ui-muted)}.report-steps>view{display:flex;align-items:center;gap:10rpx;white-space:nowrap}.step-dot{display:flex;align-items:center;justify-content:center;flex:none;width:42rpx;height:42rpx;border-radius:50%;background:#e9e7ee;font-size:12px}.is-current{color:var(--ui-text)}.is-current .step-dot,.is-complete .step-dot{background:var(--report-purple);color:#fff}
.report-card{padding:34rpx;border:1rpx solid rgba(255,255,255,.95);border-radius:38rpx;background:rgba(255,255,255,.94);box-shadow:inset 0 1rpx 0 #fff;margin-bottom:24rpx}.card-title{display:block;font-size:16px;font-weight:500;line-height:1.6}.report-note{display:block;font-size:13px;color:var(--ui-muted);line-height:1.8;overflow-wrap:anywhere}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:16rpx}.section-caption{font-size:12px;color:var(--ui-muted);flex-shrink:0}
.report-member{display:flex;justify-content:space-between;align-items:center;gap:16rpx;padding:22rpx 28rpx;margin-bottom:24rpx;border-radius:32rpx;border:1rpx solid #fff;background:rgba(255,255,255,.62)}.report-member>view{display:flex;align-items:center;gap:24rpx;min-width:0}.member-label{font-size:12px;color:var(--ui-muted);flex:none}.member-name{font-size:14px;font-weight:500;overflow-wrap:anywhere}.member-switch{display:flex;align-items:center;min-height:44px;font-size:12px;color:var(--report-purple);white-space:nowrap}
.member-state,.task-state,.saved-state{text-align:center;padding-top:42rpx}.state-symbol{display:flex;justify-content:center;color:var(--report-purple);margin-bottom:18rpx}.member-state .report-note,.task-state .report-note,.saved-state .report-note{margin:14rpx 0 24rpx}.member-state .secondary-button{margin:20rpx auto 0;min-width:240rpx;width:max-content;border-radius:999rpx}.member-options{display:flex;flex-direction:column;margin-top:20rpx}.member-options button{min-height:44px;color:var(--report-purple);font-size:14px}.task-state .secondary-button{margin-top:20rpx}
.upload-card{padding-top:30rpx}.upload-source{width:100%;display:flex;align-items:center;gap:24rpx;text-align:left;padding:32rpx 0;min-height:140rpx}.upload-source+.upload-source{border-top:1rpx solid var(--report-line)}.source-symbol{display:flex;align-items:center;justify-content:center;flex:none;width:76rpx;height:84rpx;border-radius:24rpx;background:#f1eef7;color:var(--report-purple)}.source-copy{flex:1;min-width:0}.source-copy>text{display:block;font-size:14px;font-weight:500;line-height:1.6}.source-copy>text+text{font-size:12px;font-weight:400;color:var(--ui-muted);margin-top:6rpx}.source-arrow{font-size:40rpx;color:#9993a5}.file-limits{display:block;font-size:12px;color:var(--ui-muted);line-height:1.8;margin-top:18rpx}.selected-file{display:flex;align-items:center;gap:18rpx;padding:20rpx 0;border-top:1rpx solid var(--report-line);color:var(--report-purple)}.selected-file>view{flex:1;min-width:0}.selected-file text{display:block;font-size:13px;overflow-wrap:anywhere;color:var(--ui-text)}.selected-file text+text{font-size:12px;color:var(--ui-muted);margin-top:6rpx}.selected-file button{width:44px;min-height:44px;font-size:40rpx;flex:none}
.processing-policy{padding:10rpx 6rpx 20rpx;font-size:12px}.processing-policy label{display:flex;align-items:center;min-height:44px;gap:8rpx;line-height:1.7}.processing-policy checkbox{transform:scale(.78);flex:none}.permission-note{display:block;margin:20rpx 6rpx;font-size:13px;line-height:1.8;color:#726782}.service-note{display:flex;flex-direction:column;align-items:flex-start;gap:8rpx;padding:0 6rpx;margin:18rpx 0;font-size:12px;color:var(--ui-muted)}.service-note button{color:var(--report-purple);min-height:44px;font-size:12px}
.report-workspace .primary-button{width:100%;min-height:96rpx;font-size:15px}.upload-primary{margin-top:12rpx}.save-note{display:block;text-align:center;font-size:12px;color:var(--ui-muted);margin:18rpx 0 2rpx;line-height:1.8}.text-action{display:flex;align-items:center;justify-content:center;min-height:44px;color:var(--report-purple);font-size:13px;padding:8rpx 0}.manual-action,.new-report{margin:0 auto}.report-error{display:block;padding:18rpx 6rpx;font-size:13px;color:#a33d42;line-height:1.8;overflow-wrap:anywhere}.recovery-card .primary-button{margin-top:24rpx}.recovery-card .report-note{margin-top:10rpx}.upload-progress{display:flex;flex-direction:column;gap:14rpx;padding:18rpx 6rpx;font-size:13px;color:var(--report-purple)}
.report-review>.section-heading{margin:30rpx 2rpx 20rpx}.report-preview{display:block;width:100%;border-radius:20rpx;margin-bottom:24rpx}.report-page{padding:20rpx 28rpx}.report-page .text-action{justify-content:flex-start}.indicator-card{padding:28rpx}.indicator-card>.section-heading{margin-bottom:14rpx}.evidence{display:block;font-size:12px;color:var(--ui-muted);line-height:1.8;margin:12rpx 0;overflow-wrap:anywhere}.field-label{display:block;font-size:13px;color:var(--ui-muted);margin-top:16rpx}.indicator-card .field-input{width:100%;margin:10rpx 0 14rpx;height:88rpx;min-height:44px;font-size:14px;border-radius:22rpx;background:#faf9fc}.indicator-values{width:100%;min-width:0}.indicator-card .report-result{box-sizing:border-box;width:100%;min-height:300rpx;margin:10rpx 0 14rpx;padding:24rpx;border-radius:22rpx;background:#faf9fc;font-size:15px;line-height:1.8}.indicator-values .report-note{margin-bottom:14rpx}.keep-field{display:flex;align-items:center;gap:10rpx;min-height:44px;margin-top:12rpx;font-size:12px}.keep-field switch{transform:scale(.75);margin-left:-12rpx;flex:none}.review-actions{margin-top:26rpx}.review-actions .secondary-button{margin-top:20rpx}.review-actions .report-note{margin:14rpx 0;text-align:center}.review-actions .text-area{margin-top:12rpx;background:rgba(255,255,255,.8)}.saved-symbol{display:flex;align-items:center;justify-content:center;width:80rpx;height:80rpx;border-radius:50%;background:#f0eaf7;color:var(--report-purple);font-size:42rpx;margin:0 auto 22rpx}.saved-state .text-action{margin-top:14rpx}
.report-history{border-top:1rpx solid var(--report-line);margin-top:24rpx;padding-top:12rpx}.history-toggle{display:flex;justify-content:space-between;align-items:center;width:100%;min-height:96rpx;font-size:13px;color:var(--ui-muted);text-align:left}.history-count{display:inline-flex;align-items:center;justify-content:center;min-width:36rpx;height:36rpx;margin-left:12rpx;padding:0 10rpx;border-radius:999rpx;background:#eae5f2;color:var(--report-purple);font-size:12px}.history-row{display:flex;align-items:center;justify-content:space-between;gap:16rpx;padding:20rpx 0;border-top:1rpx solid var(--report-line);font-size:14px}.history-row text{display:block}.history-row text+text{font-size:12px;color:var(--ui-muted);margin-top:6rpx}.history-row button,.history-pages button{min-height:44px;font-size:13px;color:var(--report-purple)}.history-pages{display:flex;justify-content:space-between;gap:20rpx}.history-body>.report-note{margin:12rpx 0 20rpx}
@media(max-width:350px){.report-workspace{padding-left:30rpx;padding-right:30rpx}.report-card{padding-left:26rpx;padding-right:26rpx}.report-title{font-size:23px}.upload-source{gap:16rpx}.source-copy>text{font-size:14px}.source-symbol{width:68rpx}.report-steps{gap:8rpx;font-size:12px}.report-member{padding-left:22rpx;padding-right:22rpx}}
</style>
