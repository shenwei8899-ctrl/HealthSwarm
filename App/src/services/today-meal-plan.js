import { createTodayMenuCache, profileKey } from './today-menu-cache.js'
import { readDailyMealPlan } from './daily-meal-plan.js'
import { createHealthTaskFlow } from './health-task-flow.js'
import { referenceSelection, isMealPlanCandidates } from './reference-meal-plan.js'
import { storageContext, scopedStorage } from './storage.js'
import { localDate } from '../utils/meal-state.js'

const active = status => ['queued','dispatched','pending','running','cancel_requested'].includes(status)
const stopped = status => ['failed','rejected','interrupted','cancelled','needs_input'].includes(status)
const mealTypes = ['breakfast','lunch','dinner']
const requiredMeals = plan => [...new Set([...(plan.needs_regeneration || []),
  ...mealTypes.filter(type => !plan.meals.some(meal => meal.meal_type === type))])]
export function todayMealPlanState() {
  return { phase:'idle',date:'',plan:null,verified:false,displayable:false,checking:false,issue:false,label:'正在读取今日餐单',notice:'',action:'',pending:null }
}

// The menu owns its task. It never reads or writes the chat composer, history,
// active conversation, or the chat's task-storage namespace.
export function createTodayMealPlan({ state, onPlan = () => {}, read = readDailyMealPlan,
  createFlow = createHealthTaskFlow, context = storageContext, storage = scopedStorage,
  day = localDate, schedule = setTimeout, cancel = clearTimeout, pollLimit = 150 } = {}) {
  const menuCache = createTodayMenuCache(storage)
  let generation = 0, timer = null, flow = null, disposed = false, verifiedScope = ''
  const taskStorage = {
    getStorageSync: key => storage.getStorageSync('today-menu:' + key),
    setStorageSync: (key,value) => storage.setStorageSync('today-menu:' + key,value),
  }
  function stop() {
    state.checking = false
    generation++
    if (timer !== null) cancel(timer)
    timer = null
    const previous = flow; flow = null; previous?.pause()
  }
  function clear() { stop(); verifiedScope = ''; Object.assign(state,todayMealPlanState()) }
  async function open(profile, { readOnly = false, retryFailed = false } = {}) {
    if (disposed) return
    stop()
    const cacheProfile = profile, ticket = generation, scope = context(), date = day(), family = profile?.householdId
    const planScope = JSON.stringify([scope,date,profileKey(profile || {})])
    // Restore the same-session display immediately; details and purchase verify independently.
    const previousPlan = verifiedScope === planScope && state.displayable ? state.plan : profile && family ? menuCache.read(scope,profile,date) : null
    Object.assign(state,todayMealPlanState(),{phase:previousPlan?'ready':'loading',date,plan:previousPlan,displayable:!!previousPlan,checking:true,notice:''})
    if (previousPlan) onPlan(previousPlan)
    const current = () => !disposed && ticket === generation && scope === context() && date === day()
    const fail = (privateData = false, notice = '', canRetry = false) => {
      if (!current()) return
      state.checking = false
      if (privateData) { state.plan = null; state.pending = null; state.verified = false; state.displayable = false; verifiedScope = ''; menuCache.clear() }
      state.issue = true; state.phase = state.plan ? 'ready' : 'error'
      state.notice = notice || (privateData ? '餐单资料已变化，请刷新后重新核对。' : state.plan ? state.verified ? '暂未获取更新结果，已有餐单仍可查看。' : '暂未完成核对，已有餐单仅供预览，请刷新后查看详情。' : '暂未获取餐单结果，请稍后刷新。')
      state.action = canRetry && !privateData ? 'regenerate' : 'refresh'
      if (!privateData && !notice && !canRetry && state.displayable) { state.notice = ''; state.action = ''; state.issue = false }
      if (timer !== null) cancel(timer)
      timer = null
      const previous = flow; flow = null; previous?.pause()
    }
    let polls = 0, readFailures = 0, ownSelection = null, ownMemberId = ''
    const updating = () => {
      state.label = polls >= 45 && (active(state.pending?.status) || active(flow?.getState()?.status))
        ? '三餐仍在生成，请稍候' : '正在搭配今天的三餐'
      state.notice = state.plan ? '正在更新餐单，已有餐次可继续查看。' : ''
      state.action = ''
    }
    const showCandidatePending = pending => {
      state.pending = pending
      state.checking = false; state.issue = true; state.phase = state.plan ? 'ready' : 'error'
      state.notice = '已生成待核对候选，个人适用性尚未确认；请到对话查看完整做法和来源。'
      state.action = 'candidates'; flow?.pause()
      return true
    }
    const adopt = plan => {
      if (!current()) return
      state.plan = plan.status === 'ready' ? plan : null
      state.verified = !!state.plan
      state.displayable = !!state.plan
      menuCache.write(scope,cacheProfile,date,state.plan)
      state.checking = false
      verifiedScope = state.plan ? planScope : ''
      state.pending = plan.pending || null
      const needsInput = plan.pending?.status === 'needs_input', incomplete = requiredMeals(plan).length > 0
      state.issue = needsInput || incomplete
      state.notice = needsInput ? '还有配餐问题需要确认。' : incomplete && state.plan ? '三餐尚未配齐，已有餐次可继续查看。' : ''
      state.action = needsInput ? 'answer' : incomplete && state.plan ? 'regenerate' : ''
      if (active(plan.pending?.status)) updating()
      if (plan.pending?.status === 'reference_candidates') showCandidatePending(plan.pending)
      if (state.plan) { state.phase = 'ready'; onPlan(plan) }
    }
    const taskNotice = task => task?.error || task?.notice || ({
      budget_price_unavailable:'营养咨询计费配置尚未就绪，请联系管理员。',
      budget_exceeded:'本月健康 AI 可用额度不足或待核账，请稍后再试。',
      reference_translation_correction_invalid:'餐单译文修正未通过，请重新生成餐单。',
      reference_save_correction_exhausted:'餐单修正未通过，请重新生成餐单。',
      health_execution_timeout:'本次餐单生成超时，没有保存任何餐单。请重新生成。',
      planner_output_invalid:'本次餐单结果无法核对，请重新安排。',
      planner_receipt_invalid:'本次餐单回执无法核对，请刷新状态。',
    })[task?.result?.code] || ''
    const followUp = task => {
      if (!ownSelection || task?.result?.type !== 'needs_input') return false
      state.pending = {status:'needs_input',questions:task.result.questions,selection:ownSelection,
        request_id:task.requestId,thread_id:task.entry?.thread_id,member_id:ownMemberId}
      state.checking = false; state.issue = true; state.notice = '还有配餐问题需要确认。'
      state.action = 'answer'; state.phase = state.plan ? 'ready' : 'error'
      flow?.pause()
      return true
    }
    const showCandidates = task => {
      if (!ownSelection || task?.result?.kind !== 'meal_plan_candidates' || !isMealPlanCandidates(task.result.data)) return false
      return showCandidatePending({status:'reference_candidates',selection:ownSelection,request_id:task.requestId,
        thread_id:task.entry?.thread_id,member_id:ownMemberId})
    }
    const poll = () => {
      if (!current() || timer !== null) return
      if (polls++ >= pollLimit) {
        fail(false,active(state.pending?.status) || active(flow?.getState()?.status)
          ? '餐单仍在处理中，可刷新状态继续查看原任务。' : '')
        return
      }
      timer = schedule(async () => {
        timer = null
        if (!current()) { if (ticket === generation) clear(); return }
        try {
          const plan = await read(family,date)
          if (!current()) { if (ticket === generation) clear(); return }
          readFailures = 0
          adopt(plan)
          if (plan.pending?.status === 'reference_candidates') return
          const ownedTask = flow?.getState()
          // Another device may have replaced our task. Only apply owned terminal
          // results to its matching pending task, or when no pending task exists.
          const task = !plan.pending || plan.pending.request_id === ownedTask?.requestId ? ownedTask : null
          if (ownedTask && !task) { const previous = flow; flow = null; previous.pause() }
          if (plan.pending?.status === 'needs_input') { state.phase = state.plan?'ready':'error'; flow?.pause(); return }
          if (followUp(task) || showCandidates(task)) return
          if (stopped(plan.pending?.status) || stopped(task?.status) || task?.invalidated || task?.result?.type === 'error') {
            fail(!!task?.invalidated,taskNotice(task) || (state.plan ? '本次更新已停止，已有餐单仍可查看。' : ''),true)
            return
          }
          if (active(plan.pending?.status)) { poll(); return }
          if (requiredMeals(plan).length && (task?.submitUnknown || active(task?.status))) { updating(); poll(); return }
          if (state.plan) {
            if (requiredMeals(plan).length && task?.status === 'completed') {
              // Wait until the saved read model confirms this exact group before
              // moving to another group's missing meals. Never repeat its POST.
              if (!readOnly && plan.version > ownSelection?.daily_base_version && ownSelection.meal_types.every(type=>!requiredMeals(plan).includes(type))) {
                await open(profile)
              } else poll()
            }
            else if (requiredMeals(plan).length && !readOnly) await open(profile)
            else flow?.pause()
            return
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
      if (plan.pending?.status === 'reference_candidates') return
      if (active(plan.pending?.status)) { if (!state.plan) state.phase = 'generating'; poll(); return }
      // A task awaiting required input is not permission to invent an answer.
      if (plan.pending?.status === 'needs_input') { state.phase = state.plan?'ready':'error'; return }
      if (state.plan && !requiredMeals(plan).length) return
      if (stopped(plan.pending?.status) && !retryFailed) {
        fail(false, state.plan ? '上次更新餐单失败，已有餐次仍可查看。' : '上次生成餐单失败，请点击重新安排。',true)
        return
      }
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
      const needed = requiredMeals(plan), firstDiners = plan.regeneration_participants?.[needed[0]] || selection.participant_ids
      selection.meal_types = needed.filter(type=>JSON.stringify([...(plan.regeneration_participants?.[type]||selection.participant_ids)].sort())===JSON.stringify([...firstDiners].sort()))
      selection.participant_ids = [...firstDiners].sort()
      selection.daily_base_version = plan.version
      const anchor = profile.members.find(member => selection.participant_ids.includes(member.id) && member.healthMemberId)
      if (!anchor) { fail(true); return }
      ownSelection = selection; ownMemberId = anchor.healthMemberId
      const owned = createFlow({storage:taskStorage,onChange: next => {
        if (current() && flow === owned && next.invalidated) fail(true)
      }})
      flow = owned
      await owned.open(anchor.healthMemberId,'reference_meal_preview',selection,{fresh:!!plan.needs_regeneration?.length})
      if (!current()) return
      let task = owned.getState()
      if (task.invalidated || !task.available || task.consentOption) { fail(!!task.invalidated,taskNotice(task)); return }
      if (followUp(task) || showCandidates(task)) return
      if (task.submitUnknown || active(task.status)) { poll(); return }
      if (stopped(task.status)) {
        await owned.open(anchor.healthMemberId,'reference_meal_preview',selection,{fresh:true})
        if (!current()) return
        task = owned.getState()
        if (task.invalidated || !task.available || task.consentOption) { fail(!!task.invalidated,taskNotice(task)); return }
      }
      if (task.requestId) { poll(); return }
      if (!task.entry?.thread_id) await owned.createEntry()
      if (!current()) return
      task = owned.getState()
      if (!task.entry?.thread_id || task.error || task.invalidated) { fail(!!task.invalidated); return }
      const requestedMeals = selection.meal_types.map(type=>({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'})[type]).join('、')
      const accepted = await owned.submit(`生成今日${requestedMeals}的参考餐单${selection.meal_types.length<3?'，保留其他已保存餐次。':'。'}`)
      if (!current()) return
      task = owned.getState()
      if (followUp(task) || showCandidates(task)) return
      if (stopped(task.status) || task.result?.type === 'error') { fail(!!task.invalidated,taskNotice(task),true); return }
      if (!accepted && !task.submitUnknown && !active(task.status)) {
        // Another device may have won the version/dispatch race.
        plan = await read(family,date)
        if (!current()) return
        adopt(plan)
        if (state.plan) return
        if (!active(plan.pending?.status)) { fail(!!task.invalidated,taskNotice(task)); return }
      }
      poll()
    } catch (error) {
      if (!current()) { if (ticket === generation) clear(); return }
      fail([401,403,404,409,410].includes(Number(error.code)))
    }
  }
  function isGenerating() {
    return !!flow && !state.action &&
      (state.phase==='generating' || !!state.plan && requiredMeals(state.plan).length>0)
  }
  return {open,isGenerating,pause:stop,clear,dispose(){stop();disposed=true;Object.assign(state,todayMealPlanState())}}
}
