import { readDailyMealPlan } from './daily-meal-plan.js'
import { createHealthTaskFlow } from './health-task-flow.js'
import { referenceSelection } from './reference-meal-plan.js'
import { storageContext, scopedStorage } from './storage.js'
import { localDate } from '../utils/meal-state.js'

const active = status => ['queued','dispatched','pending','running','cancel_requested'].includes(status)
const stopped = status => ['failed','rejected','interrupted','cancelled','needs_input'].includes(status)
export function todayMealPlanState() {
  return { phase:'idle',date:'',plan:null,verified:false,checking:false,issue:false,label:'正在读取今日餐单',notice:'',action:'',pending:null }
}

// The menu owns its task. It never reads or writes the chat composer, history,
// active conversation, or the chat's task-storage namespace.
export function createTodayMealPlan({ state, onPlan = () => {}, read = readDailyMealPlan,
  createFlow = createHealthTaskFlow, context = storageContext, storage = scopedStorage,
  day = localDate, schedule = setTimeout, cancel = clearTimeout, pollLimit = 45 } = {}) {
  let generation = 0, timer = null, flow = null, disposed = false, verifiedScope = ''
  const taskStorage = {
    getStorageSync: key => storage.getStorageSync('today-menu:' + key),
    setStorageSync: (key,value) => storage.setStorageSync('today-menu:' + key,value),
  }
  function stop() {
    generation++
    if (timer !== null) cancel(timer)
    timer = null
    const previous = flow; flow = null; previous?.pause()
  }
  function clear() { stop(); verifiedScope = ''; Object.assign(state,todayMealPlanState()) }
  async function open(profile, { readOnly = false } = {}) {
    if (disposed) return
    stop()
    const ticket = generation, scope = context(), date = day(), family = profile?.householdId
    const planScope = JSON.stringify([scope,family,date,profile?.selfMemberId,profile?.familyVersion])
    // A same-session snapshot is a preview until this read verifies it again.
    const previousPlan = verifiedScope === planScope ? state.plan : null
    Object.assign(state,todayMealPlanState(),{phase:previousPlan?'ready':'loading',date,plan:previousPlan,checking:true,
      notice:previousPlan?'正在核对最新餐单，稍后即可查看详情。':''})
    const current = () => !disposed && ticket === generation && scope === context() && date === day()
    const fail = (privateData = false, notice = '') => {
      if (!current()) return
      state.checking = false
      if (privateData) { state.plan = null; state.pending = null; state.verified = false; verifiedScope = '' }
      state.issue = true; state.phase = state.plan ? 'ready' : 'error'
      state.notice = notice || (privateData ? '餐单资料已变化，请刷新后重新核对。' : state.plan ? state.verified ? '暂未获取更新结果，已有餐单仍可查看。' : '暂未完成核对，已有餐单仅供预览，请刷新后查看详情。' : '暂未获取餐单结果，请稍后刷新。')
      state.action = 'refresh'
      if (timer !== null) cancel(timer)
      timer = null
      const previous = flow; flow = null; previous?.pause()
    }
    let polls = 0, readFailures = 0
    const updating = () => {
      state.notice = state.plan ? '正在更新餐单，已有餐次可继续查看。' : ''
      state.action = ''
    }
    const adopt = plan => {
      if (!current()) return
      state.plan = plan.status === 'ready' ? plan : null
      state.verified = !!state.plan
      state.checking = false
      verifiedScope = state.plan ? planScope : ''
      state.pending = plan.pending || null
      const needsInput = plan.pending?.status === 'needs_input'
      state.issue = needsInput || !!plan.needs_regeneration?.length
      state.notice = needsInput ? '还有配餐问题需要确认。' : plan.needs_regeneration?.length ? '部分餐次还需重新安排，已有餐次可继续查看。' : ''
      state.action = needsInput ? 'answer' : plan.needs_regeneration?.length ? 'regenerate' : ''
      if (active(plan.pending?.status)) updating()
      if (state.plan) { state.phase = 'ready'; onPlan(plan) }
    }
    const poll = () => {
      if (!current() || timer !== null) return
      if (polls++ >= pollLimit) { fail(); return }
      timer = schedule(async () => {
        timer = null
        if (!current()) { if (ticket === generation) clear(); return }
        try {
          const plan = await read(family,date)
          if (!current()) { if (ticket === generation) clear(); return }
          readFailures = 0
          adopt(plan)
          const task = flow?.getState()
          if (active(plan.pending?.status)) { poll(); return }
          if (plan.needs_regeneration?.length && active(task?.status)) { updating(); poll(); return }
          if (plan.pending?.status === 'needs_input') { state.phase = state.plan?'ready':'error'; flow?.pause(); return }
          if (state.plan) {
            if (stopped(plan.pending?.status)) fail(false,'本次更新已停止，已有餐单仍可查看。')
            else flow?.pause()
            return
          }
          if (stopped(plan.pending?.status) || stopped(task?.status) || task?.result?.type === 'needs_input' || task?.invalidated) {
            fail(!!task?.invalidated); return
          }
          // The read model can lag task completion or an uncertain submission.
          // Wait for its authoritative plan; never repeat the generation POST.
          poll()
        } catch (error) {
          if (!current()) return
          const privateData = [401,403,404,409,410].includes(Number(error.code))
          const transient = error.code === 'NETWORK_ERROR' || Number(error.code) >= 500
          if (!privateData && transient && ++readFailures < 3) { poll(); return }
          fail(privateData)
        }
      },2000)
    }
    try {
      if (!family) { fail(true); return }
      let plan = await read(family,date)
      if (!current()) { if (ticket === generation) clear(); return }
      adopt(plan)
      if (active(plan.pending?.status)) { if (!state.plan) state.phase = 'generating'; poll(); return }
      // A task awaiting required input is not permission to invent an answer.
      if (plan.pending?.status === 'needs_input') { state.phase = state.plan?'ready':'error'; return }
      if (state.plan && !plan.needs_regeneration?.length) return
      // Refresh only reads the original task; it must never repeat a generation POST.
      if (readOnly) {
        if (!state.plan) {
          fail()
          if (!plan.pending || stopped(plan.pending.status)) state.action = 'regenerate'
        }
        return
      }
      state.phase = state.plan?'ready':'generating'; state.label = '正在安排今天的三餐'
      updating()
      const selection = referenceSelection(profile,'安排今天的三餐',{today:date})
      if (plan.needs_regeneration?.length) {
        const first=plan.needs_regeneration[0],diners=plan.regeneration_participants?.[first]
        selection.meal_types = plan.needs_regeneration.filter(type=>!diners?.length||JSON.stringify([...(plan.regeneration_participants?.[type]||[])].sort())===JSON.stringify([...diners].sort()))
        if(diners?.length)selection.participant_ids=[...diners].sort()
      }
      selection.daily_base_version = plan.version
      const anchor = profile.members.find(member => selection.participant_ids.includes(member.id) && member.healthMemberId)
      if (!anchor) { fail(true); return }
      const owned = createFlow({storage:taskStorage,onChange: next => {
        if (current() && next.invalidated) fail(true)
      }})
      flow = owned
      await owned.open(anchor.healthMemberId,'reference_meal_preview',selection)
      if (!current()) return
      let task = owned.getState()
      if (task.invalidated || !task.available || task.consentOption) { fail(!!task.invalidated); return }
      if (task.result?.type === 'needs_input') {
        state.pending = { status:'needs_input',questions:task.result.questions,selection,request_id:task.requestId,thread_id:task.entry?.thread_id,member_id:anchor.healthMemberId }
        state.issue = true; state.notice = '还有配餐问题需要确认。'; state.action = 'answer'; state.phase = state.plan?'ready':'error'
        return
      }
      if (task.submitUnknown || active(task.status)) { poll(); return }
      if (stopped(task.status)) {
        await owned.open(anchor.healthMemberId,'reference_meal_preview',selection,{fresh:true})
        if (!current()) return
        task = owned.getState()
        if (task.invalidated || !task.available || task.consentOption) { fail(!!task.invalidated); return }
      }
      if (task.requestId) { poll(); return }
      if (!task.entry?.thread_id) await owned.createEntry()
      if (!current()) return
      task = owned.getState()
      if (!task.entry?.thread_id || task.error || task.invalidated) { fail(!!task.invalidated); return }
      const accepted = await owned.submit(plan.needs_regeneration?.length?'重新安排未配齐的餐次，保留其他餐次。':'生成今日早餐、午餐和晚餐的参考餐单。')
      if (!current()) return
      task = owned.getState()
      if (!accepted && !task.submitUnknown && !active(task.status)) {
        // Another device may have won the version/dispatch race.
        plan = await read(family,date)
        if (!current()) return
        adopt(plan)
        if (state.plan) return
        if (!active(plan.pending?.status)) { fail(!!task.invalidated); return }
      }
      poll()
    } catch (error) { fail([401,403,404,409,410].includes(Number(error.code))) }
  }
  return {open,pause:stop,clear,dispose(){stop();disposed=true;Object.assign(state,todayMealPlanState())}}
}
