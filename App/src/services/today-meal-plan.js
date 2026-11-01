import { readDailyMealPlan } from './daily-meal-plan.js'
import { createHealthTaskFlow } from './health-task-flow.js'
import { referenceSelection } from './reference-meal-plan.js'
import { storageContext, scopedStorage } from './storage.js'
import { localDate } from '../utils/meal-state.js'

const active = status => ['queued','dispatched','pending','running','cancel_requested'].includes(status)
const stopped = status => ['failed','rejected','interrupted','cancelled','needs_input'].includes(status)
export function todayMealPlanState() {
  return { phase:'idle',date:'',plan:null,issue:false,label:'正在打开今日餐单' }
}

// The menu owns its task. It never reads or writes the chat composer, history,
// active conversation, or the chat's task-storage namespace.
export function createTodayMealPlan({ state, onPlan = () => {}, read = readDailyMealPlan,
  createFlow = createHealthTaskFlow, context = storageContext, storage = scopedStorage,
  day = localDate, schedule = setTimeout, cancel = clearTimeout, pollLimit = 45 } = {}) {
  let generation = 0, timer = null, flow = null, disposed = false
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
  function clear() { stop(); Object.assign(state,todayMealPlanState()) }
  async function open(profile) {
    if (disposed) return
    stop()
    const ticket = generation, scope = context(), date = day(), family = profile?.householdId
    Object.assign(state,todayMealPlanState(),{phase:'loading',date})
    const current = () => !disposed && ticket === generation && scope === context() && date === day()
    const fail = (privateData = false) => {
      if (!current()) return
      if (privateData) state.plan = null
      state.issue = true; state.phase = state.plan ? 'ready' : 'error'
      if (timer !== null) cancel(timer)
      timer = null
      const previous = flow; flow = null; previous?.pause()
    }
    let polls = 0
    const adopt = plan => {
      if (!current()) return
      state.plan = plan.status === 'ready' ? plan : null
      state.issue = stopped(plan.pending?.status)
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
          adopt(plan)
          const task = flow?.getState()
          if (active(plan.pending?.status)) { poll(); return }
          if (state.plan) { flow?.pause(); return }
          if (stopped(plan.pending?.status) || stopped(task?.status) || task?.result?.type === 'needs_input' || task?.invalidated) {
            fail(!!task?.invalidated); return
          }
          // The read model can lag task completion or an uncertain submission.
          // Wait for its authoritative plan; never repeat the generation POST.
          poll()
        } catch (error) { fail([401,403,404,409,410].includes(Number(error.code))) }
      },2000)
    }
    try {
      if (!family) { fail(true); return }
      let plan = await read(family,date)
      if (!current()) { if (ticket === generation) clear(); return }
      adopt(plan)
      if (active(plan.pending?.status)) { if (!state.plan) state.phase = 'generating'; poll(); return }
      if (state.plan) return
      // A task awaiting required input is not permission to invent an answer.
      if (plan.pending?.status === 'needs_input') { fail(); return }
      state.phase = 'generating'; state.label = '正在安排今天的三餐'
      const selection = referenceSelection(profile,'安排今天的三餐',{today:date})
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
      if (task.result?.type === 'needs_input') { fail(); return }
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
      const accepted = await owned.submit('生成今日早餐、午餐和晚餐的参考餐单。')
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
