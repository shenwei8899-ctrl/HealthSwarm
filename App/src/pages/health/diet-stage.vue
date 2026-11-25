<script setup>
import { computed, reactive, ref } from 'vue'
import { onLoad, onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import { createDietStageClient, currentStageWeek, dietStageState, stageGoalOptions } from '../../services/diet-stage-client.js'
import { sessionRevision } from '../../services/session.js'

const state = reactive(dietStageState()), client = createDietStageClient({ state })
const route = ref({}), editor = ref(false), reviewOpen = ref(false), nextStage = ref(false)
const selected = ref([]), custom = ref(''), draft = ref(null), draftId = ref(''), editWeek = ref(null)
const historyOpen = ref(false)
const value = computed(() => state.value), stage = computed(() => value.value?.stage)
const week = computed(() => currentStageWeek(value.value))
const completed = computed(() => stage.value && (stage.value.status !== 'active' || value.value.today >= stage.value.review_on))
const readonly = computed(() => value.value?.can_edit === false || stage.value?.status === 'completed')
const goalOptions = computed(() => [...new Set([...stageGoalOptions, ...(value.value?.existing_goals || [])])])
const elapsed = computed(() => stage.value ? Math.max(1, Math.floor((Date.parse(value.value.today) - Date.parse(stage.value.starts_on)) / 86400000) + 1) : 0)
let loadedRevision = -1, active = false
onLoad(options => { route.value = options })
onShow(async () => {
  active = true
  if (loadedRevision !== sessionRevision()) {
    editor.value = false; draft.value = null; editWeek.value = null; selected.value = []; custom.value = ''
    await client.open(route.value.familyId || '', route.value.memberId || '')
    loadedRevision = sessionRevision()
  } else await client.reload()
  if (!active) return
  const jobs = value.value?.jobs || []
  const pending = jobs.find(job => job.status === 'pending')
  if (pending) { await showJob(pending.id); return }
  const savedDraft = jobs.find(job => job.kind === 'draft' && job.status === 'ready')
  if (savedDraft) {
    await showJob(savedDraft.id)
    if (!active || state.job?.status === 'ready') return
  }
  const latest = jobs.find(job => job.kind === 'review')
  if (latest) await showJob(latest.id)
})
onHide(() => { active = false; client.stop() })
onUnload(() => { active = false; client.discard() })
function begin(next = false) {
  nextStage.value = next; selected.value = [...(stage.value?.goals || value.value?.existing_goals || [])].slice(0, 2)
  custom.value = ''; draft.value = null; editor.value = true; draftId.value = ''
}
function choose(goal) {
  if (selected.value.includes(goal)) selected.value = selected.value.filter(value => value !== goal)
  else if (selected.value.length < 2) selected.value.push(goal)
  else uni.showToast({ title: '先关注一至两个目标', icon: 'none' })
}
function consumeJob() {
  const job = state.job
  if (job?.status === 'ready' && job.kind === 'draft') {
    draft.value = JSON.parse(JSON.stringify(job.result)); draftId.value = job.id
    editor.value = true; nextStage.value = !!completed.value
  }
}
async function showJob(id) {
  await client.job(id); consumeJob()
  if (active && state.job?.status === 'pending') client.poll(id, consumeJob)
}
async function generate(kind) {
  await client.generate(kind, { goals: kind === 'draft' ? selected.value : [], note: kind === 'draft' ? custom.value.trim() : '' })
  if (active && state.job?.id) { await showJob(state.job.id); if (kind === 'review') reviewOpen.value = true }
}
async function save() {
  if (!draft.value?.goals.every(text => text.trim()) || !draft.value.actions.every(item => item.title.trim())) {
    return uni.showToast({ title: '请补充目标和行动内容', icon: 'none' })
  }
  await client.save(draft.value, draftId.value, { next: nextStage.value })
  if (!state.error && !state.pending) { editor.value = false; draft.value = null }
}
async function count(action, delta, toggle = false) {
  if (state.busy || readonly.value || completed.value) return
  const actions = week.value.actions.map(item => ({ ...item }))
  const target = actions.find(item => item.id === action.id)
  target.count = toggle ? (target.count >= target.target ? 0 : target.target) : Math.max(0, Math.min(target.target, target.count + delta))
  await client.saveWeek(week.value, actions)
}
function changeWeek() { editWeek.value = JSON.parse(JSON.stringify(week.value)) }
async function saveActions() {
  await client.saveWeek(week.value, editWeek.value.actions)
  if (!state.error && !state.pending) editWeek.value = null
}
async function retry() {
  await client.retry()
  if (state.job?.id) await showJob(state.job.id)
}
function closeEditor() {
  if (state.busy) return
  editor.value = false; draft.value = null
}
async function openHistory(id = '') {
  await client.history(id)
  const job = value.value?.jobs?.find(item => item.kind === 'review')
  if (job) await showJob(job.id)
}
</script>
<template>
  <view class="stage-screen">
    <AppNavBar title="饮食目标与行动"><template #left><button class="stage-back" aria-label="返回" @click="uni.navigateBack()">‹</button></template></AppNavBar>
    <view v-if="!value && state.busy" class="stage-empty"><text>正在读取目标与行动…</text></view>
    <view v-if="state.error" class="stage-error" role="alert"><text>{{state.error}}</text><button :disabled="state.busy" @click="state.pending ? retry() : client.reload()">{{state.pending?'重试原操作':'重新读取'}}</button></view>
    <view v-if="state.pending && !state.error" class="stage-error"><text>上次提交结果尚未确认</text><button :disabled="state.busy" @click="retry">确认原操作结果</button></view>
    <template v-if="value">
      <view class="stage-heading"><text class="stage-person">{{value.name}}的饮食安排</text><text class="stage-title">{{stage?'把目标，放进每一周':'从一个小目标开始'}}</text><text class="stage-caption">{{stage?'每周做一点，慢慢找到适合自己的节奏。':'结合已有资料，一起安排接下来约三个月的饮食行动。'}}</text></view>
      <view v-if="stage" class="stage-card stage-target">
        <view class="stage-row"><text class="stage-label">{{stage.status==='completed'?'已结束阶段':completed?'本阶段已到复盘时间':'本阶段目标'}}</text><button v-if="!readonly && !completed" class="stage-link" :disabled="state.busy" @click="begin(false)">调整</button></view>
        <text v-for="(goal,i) in stage.goals" :key="i" class="stage-goal"><text class="goal-number">0{{i+1}}</text>{{goal}}</text>
        <view class="stage-dates"><text>{{stage.starts_on}} 至 {{stage.review_on}}</text><text v-if="!completed">第 {{elapsed}} 天</text></view>
      </view>
      <view v-else class="stage-card stage-start"><view class="stage-start-mark">01</view><text class="stage-block-title">先选方向，再慢慢行动</text><text class="stage-caption">选择你关心的目标，也可以写下自己的想法。AI 整理建议，由你确认开始。</text><button class="stage-primary" :disabled="state.busy || readonly" @click="begin(false)">制定本阶段目标</button></view>
      <template v-if="stage">
        <view class="stage-row stage-section-heading"><text class="stage-block-title">{{completed?'行动记录':'本周行动'}}</text><button v-if="week && !readonly && !completed" class="stage-link" :disabled="state.busy" @click="changeWeek">调整清单</button></view>
        <view v-if="week" class="stage-card stage-checklist">
          <view class="stage-row stage-week-meta"><text>{{week.starts_on.slice(5)}} — {{week.ends_on.slice(5)}}</text><text>完成 {{week.completed}} / {{week.total}}</text></view>
          <view class="stage-progress"><view :style="{width:week.total ? (week.completed / week.total * 100)+'%' : '0%'}"/></view>
          <view v-for="action in week.actions" :key="action.id" class="stage-action" :class="{'is-done':action.count>=action.target}">
            <button class="stage-check" :disabled="state.busy || readonly || completed" :aria-label="(action.count>=action.target?'撤销完成：':'完成：')+action.title" @click="count(action,0,true)">{{action.count>=action.target?'✓':''}}</button>
            <view class="stage-action-copy"><text class="stage-action-title">{{action.title}}</text><view v-if="action.target>1" class="stage-counter"><text>已完成 {{action.count}} / {{action.target}} 次</text><button :disabled="state.busy || readonly || completed || action.count===0" aria-label="撤销一次" @click="count(action,-1)">−</button><button :disabled="state.busy || readonly || completed || action.count>=action.target" aria-label="记一次" @click="count(action,1)">＋</button></view></view>
          </view>
          <text class="stage-caption stage-small">完成后轻点划掉，也可以再次点击撤销。</text>
        </view>
        <view v-else-if="!completed" class="stage-card"><text class="stage-caption">正在接续新一周的行动安排。</text><button v-if="!readonly" class="stage-secondary" :disabled="state.busy || state.job?.status==='pending'" @click="generate('week')">准备本周行动</button></view>
        <view v-else class="stage-card"><text class="stage-caption">本阶段已结束，可展开下方历史清单回顾。</text></view>
        <view class="stage-card stage-review">
          <button class="stage-review-toggle" :aria-expanded="reviewOpen" @click="reviewOpen=!reviewOpen"><view><text class="stage-block-title">阶段复盘</text><text class="stage-caption">AI 整理这段时间的变化与下一步建议</text></view><text>{{reviewOpen?'−':'＋'}}</text></button>
          <view v-if="reviewOpen" class="stage-review-body">
            <template v-if="state.job?.kind==='review' && state.job?.status==='ready'">
              <text class="stage-label">总结截至 {{state.job.as_of}}</text><text class="stage-review-text">{{state.job.result.summary}}</text>
              <text v-for="(item,i) in state.job.result.observations" :key="'o'+i" class="stage-review-text">· {{item}}</text>
              <view v-if="state.job.reports?.length" class="stage-report"><text class="stage-label">报告中的变化</text><view v-for="item in state.job.reports" :key="item.code"><text>{{item.name}}{{item.supplemental?' · 阶段结束后补充':''}}</text><text>{{item.previous?.observed_at||'暂无上次结果'}} {{item.previous?.value_raw||''}} → {{item.current.observed_at}} {{item.current.value_raw}} {{item.current.unit_raw}}</text><text v-if="item.delta!==null">数值差 {{item.delta}}</text><text class="stage-caption">{{item.note}}</text></view></view>
              <text v-else class="stage-caption">暂无可对比的新报告，也可以先回顾饮食执行情况。</text>
              <text class="stage-label">下一步建议</text><text v-for="(item,i) in state.job.result.next_steps" :key="'n'+i" class="stage-review-text">· {{item}}</text>
            </template>
            <text v-else class="stage-caption">{{state.job?.status==='pending'?'正在后台整理，离开后也会继续。':state.job?.error||'结合已有饮食记录、行动和相关对话，回顾这段时间。新体检报告不是必填项。'}}</text>
            <button class="stage-secondary" :disabled="state.busy || state.job?.status==='pending' || readonly" @click="generate('review')">{{state.job?.status==='ready'?'更新阶段总结':'整理阶段总结'}}</button>
            <button v-if="completed && stage.status==='active' && state.job?.kind==='review' && state.job?.status==='ready'" class="stage-primary" :disabled="state.busy || readonly" @click="begin(true)">确认复盘，制定下一阶段目标</button>
          </view>
        </view>
        <view v-if="value.weeks.length>1 || completed" class="stage-history"><button class="stage-link" :aria-expanded="historyOpen" @click="historyOpen=!historyOpen">历周行动 {{historyOpen?'−':'＋'}}</button><template v-if="historyOpen"><view v-for="item in value.weeks" :key="item.id" class="stage-old-week"><text>{{item.starts_on}} · 完成 {{item.completed}} / {{item.total}}</text><text v-for="action in item.actions" :key="action.id" :class="{'old-done':action.count>=action.target}">{{action.count>=action.target?'✓':'○'}} {{action.title}} {{action.target>1? action.count+'/'+action.target+'次':''}}</text></view></template></view>
      </template>
      <view v-if="value.history.length>1" class="stage-history"><text class="stage-label">历次阶段</text><button v-for="item in value.history" :key="item.id" class="stage-history-button" :disabled="state.busy" @click="openHistory(item.id)">{{item.starts_on}} · {{item.goals.join('、')}} ›</button><button class="stage-link" :disabled="state.busy" @click="openHistory()">返回当前阶段</button></view>
    </template>
    <view v-if="state.job?.status==='pending'" class="stage-working" role="status">正在整理{{state.job.kind==='review'?'阶段复盘':'行动建议'}}…</view>
    <view v-if="editor || editWeek" class="stage-mask" @touchmove.stop.prevent>
      <view class="stage-sheet" role="dialog" aria-modal="true" :aria-label="editWeek?'调整行动清单':'制定阶段目标'">
        <view class="stage-row stage-sheet-heading"><text class="stage-block-title">{{editWeek?'调整行动清单':draft?'核对目标与行动':'选择本阶段方向'}}</text><button class="stage-close" aria-label="关闭" :disabled="state.busy" @click="editWeek ? editWeek=null : closeEditor()">×</button></view>
        <scroll-view scroll-y class="stage-sheet-scroll">
          <template v-if="editWeek">
            <view v-for="(action,i) in editWeek.actions" :key="action.id||i" class="stage-draft-action"><input v-model="action.title" maxlength="200" placeholder="行动内容"/><view class="stage-row"><text>本周次数</text><picker :range="[1,2,3,4,5,6,7]" :value="action.target-1" @change="action.target=Number($event.detail.value)+1;action.count=Math.min(action.count,action.target)"><text>{{action.target}} 次 ⌄</text></picker><button v-if="editWeek.actions.length>1" class="stage-link" @click="editWeek.actions.splice(i,1)">移除</button></view></view>
            <button v-if="editWeek.actions.length<5" class="stage-secondary" @click="editWeek.actions.push({id:null,title:'',target:1,count:0})">＋ 添加行动</button>
          </template>
          <template v-else-if="draft">
            <text class="stage-caption">{{draft.reason}}</text><text class="stage-label stage-space">本阶段目标</text><input v-for="(_,i) in draft.goals" :key="i" v-model="draft.goals[i]" class="stage-input" maxlength="80" placeholder="目标内容"/>
            <text class="stage-label stage-space">第一周行动建议</text><view v-for="(action,i) in draft.actions" :key="i" class="stage-draft-action"><input v-model="action.title" maxlength="200"/><view class="stage-row"><text>本周次数</text><picker :range="[1,2,3,4,5,6,7]" :value="action.target-1" @change="action.target=Number($event.detail.value)+1"><text>{{action.target}} 次 ⌄</text></picker></view></view>
            <text class="stage-caption">确认后生效。正在执行的当周清单会保留，可再单独调整。</text>
          </template>
          <template v-else>
            <text class="stage-caption">先关注一至两个方向，也可以让 AI 结合已有资料推荐。</text><view class="stage-options"><button v-for="goal in goalOptions" :key="goal" :class="{chosen:selected.includes(goal)}" :aria-pressed="selected.includes(goal)" @click="choose(goal)">{{goal}}</button></view><text class="stage-label">我自己的想法</text><textarea v-model="custom" class="stage-custom" maxlength="1000" placeholder="例如：工作忙时总是吃得很晚，希望慢慢调整……"/><text class="stage-caption">将结合当前成员已有的健康资料、饮食记录和相关自述整理建议。</text>
          </template>
          <text v-if="state.error" class="stage-error">{{state.error}}</text>
          <text v-if="state.job?.status==='failed' || state.job?.status==='stale'" class="stage-error">{{state.job.error}}</text>
        </scroll-view>
        <button class="stage-primary stage-sheet-submit" :disabled="state.busy || state.job?.status==='pending' || !!state.pending" @click="editWeek ? saveActions() : draft ? save() : generate('draft')">{{state.busy?'正在处理…':editWeek?'保存行动清单':draft?(nextStage?'确认并开始下一阶段':'确认目标与行动'):'生成目标与行动建议'}}</button>
      </view>
    </view>
  </view>
</template>
<style scoped>
.stage-screen{min-height:100vh;box-sizing:border-box;padding:0 21px calc(36px + env(safe-area-inset-bottom));background:#f3f2fb;color:#39364e}.stage-back{width:44px;height:44px;font-size:30px;color:#6c6385}.stage-heading{padding:24px 2px 22px}.stage-person,.stage-caption,.stage-label{display:block;font-size:12px;line-height:1.7;color:#77718c}.stage-person{color:#8973b1;letter-spacing:1px}.stage-title{display:block;margin:10px 0;font-size:25px;font-weight:600;line-height:1.4;letter-spacing:-.5px}.stage-card{padding:21px;margin-bottom:18px;border-radius:23px;background:#fff;border:1px solid #f0edf7}.stage-target{background:#fdfcff;border-color:#e9e3f5}.stage-row{display:flex;align-items:center;justify-content:space-between;gap:12px}.stage-link{min-height:40px;padding:6px 0;background:transparent;color:#8260b5;font-size:12px;line-height:1.5}.stage-goal{display:flex;gap:13px;margin:13px 0;font-size:17px;line-height:1.6;font-weight:500}.goal-number{font-size:12px;color:#b1a1ca;line-height:27px}.stage-dates{display:flex;justify-content:space-between;gap:8px;margin-top:21px;padding-top:16px;border-top:1px solid #eeebf5;font-size:10px;color:#8a819c}.stage-block-title{display:block;font-size:16px;font-weight:600;line-height:1.6}.stage-start-mark{font-size:36px;color:#c9bbdf;font-weight:300;margin-bottom:20px}.stage-start .stage-caption{margin:12px 0 22px}.stage-primary,.stage-secondary{width:100%;min-height:46px;padding:12px 16px;border-radius:15px;font-size:14px;line-height:1.5}.stage-primary{background:#8062ad;color:white}.stage-secondary{margin-top:17px;background:#f0ebf8;color:#755a9d}.stage-primary[disabled],.stage-secondary[disabled]{opacity:.5}.stage-section-heading{margin:25px 2px 12px}.stage-week-meta{font-size:11px;color:#8d82a2}.stage-progress{height:3px;border-radius:3px;background:#f0edf5;margin:15px 0 9px;overflow:hidden}.stage-progress>view{height:100%;background:#a68bc9;transition:width .2s}.stage-action{display:flex;gap:13px;padding:19px 0;border-bottom:1px solid #f3f0f7}.stage-check{flex:none;width:26px;height:26px;min-height:26px;padding:0;line-height:24px;border:1px solid #d9cde8;border-radius:9px;color:white;background:#fff;font-size:16px}.is-done .stage-check{background:#b2a0ca;border-color:#b2a0ca}.stage-action-copy{flex:1;min-width:0}.stage-action-title{display:block;font-size:14px;line-height:1.8;overflow-wrap:anywhere}.is-done .stage-action-title{text-decoration:line-through;color:#9b92a9}.stage-counter{display:flex;align-items:center;gap:10px;margin-top:9px;font-size:11px;color:#94859f}.stage-counter>text{flex:1}.stage-counter button{width:36px;height:36px;line-height:34px;background:#f5f1fa;border-radius:10px;color:#806795;font-size:18px;padding:0}.stage-small{margin-top:14px;font-size:10px}.stage-review{padding:0;overflow:hidden}.stage-review-toggle{display:flex;align-items:center;justify-content:space-between;gap:16px;width:100%;padding:22px 21px;background:transparent;text-align:left;color:#7e669d}.stage-review-toggle>view{flex:1}.stage-review-toggle .stage-caption{margin-top:5px;font-size:11px}.stage-review-body{padding:0 21px 23px}.stage-review-text{display:block;margin:12px 0 17px;font-size:14px;line-height:1.9}.stage-report{padding:17px 14px;margin:20px 0;background:#f8f6fb;border-radius:15px}.stage-report>view{padding:14px 0;border-bottom:1px solid #eee9f4}.stage-report>view>text{display:block;font-size:12px;line-height:1.9}.stage-history{margin:26px 2px}.stage-old-week{margin:14px 0;padding:16px;border-radius:16px;background:#eae8f3}.stage-old-week>text{display:block;font-size:12px;line-height:1.9;margin-bottom:6px;color:#746b86}.old-done{text-decoration:line-through;opacity:.65}.stage-history-button{display:block;width:100%;text-align:left;margin-top:10px;padding:15px;background:#fff;border-radius:13px;font-size:12px;color:#786f8b}.stage-error{padding:14px;margin:12px 0;background:#fff5f3;border-radius:13px;color:#945f62;font-size:12px;line-height:1.8;display:block}.stage-error button{color:#8d5c70;font-size:12px;background:transparent;min-height:40px}.stage-empty{padding:55px 16px;text-align:center;color:#897f98;font-size:13px}.stage-working{position:fixed;bottom:18px;left:25px;right:25px;max-width:430px;margin:auto;padding:13px 18px;border-radius:15px;background:#494059;color:#fff;font-size:12px;text-align:center;z-index:40}.stage-mask{position:fixed;inset:0;z-index:180;display:flex;align-items:flex-end;background:rgba(44,39,61,.27)}.stage-sheet{width:100%;max-width:500px;max-height:88vh;margin:0 auto;padding:14px 22px calc(18px + env(safe-area-inset-bottom));box-sizing:border-box;border-radius:27px 27px 0 0;background:#f8f6fc;display:flex;flex-direction:column}.stage-sheet-heading{flex:none;margin-bottom:15px}.stage-close{width:44px;height:44px;padding:0;line-height:44px;font-size:25px;background:transparent;color:#9985b3}.stage-sheet-scroll{height:52vh;flex:auto;min-height:0}.stage-sheet-submit{margin-top:17px;flex:none}.stage-options{display:flex;flex-wrap:wrap;gap:9px;margin:20px 0 25px}.stage-options>button{font-size:12px;line-height:1.5;padding:12px 15px;border:1px solid #e6deef;border-radius:13px;background:#fff;color:#7b6d8b}.stage-options>button.chosen{background:#e9e0f6;border-color:#c3addf;color:#725095}.stage-custom{width:100%;height:120px;box-sizing:border-box;margin:12px 0 17px;padding:15px;border-radius:14px;background:#fff;font-size:14px;line-height:1.8;color:#4b405a}.stage-input,.stage-draft-action>input{width:100%;height:46px;box-sizing:border-box;padding:10px 13px;border-radius:12px;background:#fff;font-size:14px;color:#51465f;margin:10px 0}.stage-draft-action{margin:12px 0;padding:10px 12px 13px;border-radius:15px;background:#eee9f6;font-size:12px;color:#84728f}.stage-draft-action>input{background:#fff}.stage-draft-action picker{padding:10px;background:#fff;border-radius:9px}.stage-space{margin-top:20px}button:after{border:0}@media(min-width:520px){.stage-screen{max-width:520px;margin:auto}}@media(prefers-reduced-motion:reduce){.stage-progress>view{transition:none}}
</style>
