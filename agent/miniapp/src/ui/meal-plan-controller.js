import { MEAL_TYPES, mealPlanMember, mealPlanLink, mealPlanList, mealPlanDetail, mealPlanPreview,
  mealPlanResult, publishedRecipes, recipePortions } from './meal-plan-projection.js'

const blankDish = () => ({ recipe_version_id: '', portion_mode: 'unknown', grams: '', portion_reference_id: '', portion_count: '' })
const blankDraft = () => ({ plan_date: '', meals: MEAL_TYPES.map(meal_type => ({ meal_type, dishes: [blankDish()] })) })
const initialState = () => ({ account: null, member: null, link: null, loading: false, listLoading: false,
  detailLoading: false, catalogLoading: false, previewLoading: false, busy: false, blocked: false, error: '', notice: '',
  plans: [], truncated: false, selectedPlanId: '', currentPlan: null, history: [], historyVersion: null, historySnapshot: null,
  draft: blankDraft(), recipes: [], recipeQuery: '', portions: {}, portionLoading: {}, preview: null, swap: null,
  writeUnknown: false, writeOperation: '', readBackPending: false, needsReload: false })
const copy = value => JSON.parse(JSON.stringify(value))
const protocol = message => Object.assign(new Error(message), { code: 'protocol_mismatch' })
const validation = message => Object.assign(new Error(message), { code: 'invalid_meal_plan_input' })
const uncertain = error => error?.status === 0 || (error?.status >= 500 && error?.status < 600)
const privateFailure = error => [401, 403, 404, 410].includes(error?.status) || error?.code === 'protocol_mismatch'

function requestId() {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, character => {
    const random = Math.floor(Math.random() * 16)
    return (character === 'x' ? random : (random & 3) | 8).toString(16)
  })
}
function amount(value, limit, label) {
  const number = typeof value === 'string' ? value.trim() : ''
  if (!/^\d+(?:\.\d{1,6})?$/.test(number) || Number(number) <= 0 || Number(number) > limit) {
    throw validation(`${label}须大于0、不超过${limit}，最多6位小数；未知份量请选择“未知”`)
  }
  return number
}
function validDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)
    || Number.isNaN(Date.parse(`${value}T00:00:00Z`)) || new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) !== value) {
    throw validation('请明确填写有效的计划日期')
  }
  return value
}

/** 页面内存控制器。普通业务不进入模型；退出、切号和拒读立即废弃所有私有数据与写入意图。 */
export function createMealPlanController({ client, onChange = () => {}, onUnauthorized = () => {}, newId = requestId }) {
  let state = initialState(), visible = false, epoch = 0, memberId = '', posting = false, writeIntent = null, readBack = null
  let listSequence = 0, detailSequence = 0, catalogSequence = 0, previewSequence = 0
  const portionSequences = new Map(), approvedRecipes = new Map()
  const emit = () => onChange(copy(state))
  const ticket = () => ({ epoch, revision: client.sessionRevision, uid: client.getSession()?.uid })
  const current = token => visible && token.epoch === epoch && token.revision === client.sessionRevision
    && !!token.uid && token.uid === client.getSession()?.uid
  function reset() {
    epoch += 1; posting = false; writeIntent = null; readBack = null
    portionSequences.clear(); approvedRecipes.clear(); state = initialState(); emit()
  }
  function revoke(message) {
    const account = state.account
    reset(); state.account = account; state.blocked = true; state.error = message; emit()
  }
  function handleError(error, token, relevant = true) {
    if (!current(token) || error?.code === 'stale_session') return
    // 拒读比选择序号更强：同一页面中任何已发请求的撤权都清除全部私有状态。
    if (privateFailure(error)) {
      revoke('当前餐单、来源或成员授权已不可读取。已清除内容，请返回核对身份、授权及真实关联。')
      if (error?.status === 401) onUnauthorized()
    } else if (relevant && error?.status === 409) {
      previewSequence += 1; writeIntent = null; readBack = null
      state.preview = null; state.swap = null; state.currentPlan = null; state.history = []; state.historyVersion = null; state.historySnapshot = null
      state.writeUnknown = false; state.writeOperation = ''; state.readBackPending = false; state.previewLoading = false
      state.needsReload = true; state.error = error.message || '餐单版本或来源已变化'
      state.notice = '请重新读取并明确选择当前餐单或重新预览；原待确认请求已废弃。'; emit()
    } else if (relevant) { state.error = error?.message || '服务暂不可用，请重新读取'; emit() }
  }
  const unsubscribe = client.subscribeSession(session => {
    reset(); state.account = session ? { uid: session.uid, username: session.username } : null; emit()
    if (!session && visible) onUnauthorized()
  })
  const unlocked = () => visible && !!state.member && !!state.link && !state.blocked && !state.loading
    && !state.needsReload && !posting && !writeIntent && !readBack
  function clearPreview() { previewSequence += 1; state.preview = null; state.previewLoading = false; state.busy = posting }
  function localError(error) { state.error = error.message; emit() }

  async function show(id) {
    reset(); visible = true; memberId = id
    const session = client.getSession()
    if (!session) { onUnauthorized(); return }
    state.account = { uid: session.uid, username: session.username }; state.loading = true; emit()
    const token = ticket()
    try {
      const rows = await client.listHealthMembers()
      if (!current(token)) return
      state.member = mealPlanMember(rows, memberId)
      const mapping = await client.readProfileLink(memberId)
      if (!current(token)) return
      state.link = mealPlanLink(mapping, memberId)
      await Promise.all([loadList(token), loadRecipes('', token)])
    } catch (error) { handleError(error, token) }
    finally { if (current(token)) { state.loading = false; emit() } }
  }
  function hide() { visible = false; reset() }
  function dispose() { hide(); unsubscribe() }
  function reload() { if (visible && !posting && !writeIntent && !readBack) return show(memberId) }

  async function loadList(token) {
    const sequence = ++listSequence; state.listLoading = true; emit()
    try {
      const value = await client.listMealPlans(memberId)
      if (!current(token) || sequence !== listSequence) return
      const page = mealPlanList(value, memberId)
      state.plans = page.plans; state.truncated = page.truncated; emit()
    } catch (error) { handleError(error, token, sequence === listSequence) }
    finally { if (current(token) && sequence === listSequence) { state.listLoading = false; emit() } }
  }
  async function loadRecipes(query, token) {
    const sequence = ++catalogSequence; state.recipeQuery = query; state.catalogLoading = true; emit()
    try {
      const value = await client.listPublishedRecipes(query)
      if (!current(token) || sequence !== catalogSequence) return
      state.recipes = publishedRecipes(value)
      state.recipes.forEach(row => approvedRecipes.set(row.id, row)); emit()
    } catch (error) { handleError(error, token, sequence === catalogSequence) }
    finally { if (current(token) && sequence === catalogSequence) { state.catalogLoading = false; emit() } }
  }
  function searchRecipes(query = '') {
    if (!unlocked()) return
    if (typeof query !== 'string' || query.length > 120) return localError(validation('菜谱查询须为不超过120字的文本'))
    return loadRecipes(query, ticket())
  }

  async function selectPlan(id) {
    if (!unlocked()) return
    const summary = state.plans.find(row => row.plan_id === id)
    if (!summary) return
    const token = ticket(), sequence = ++detailSequence
    clearPreview(); state.swap = null; state.selectedPlanId = id; state.currentPlan = null
    state.history = []; state.historyVersion = null; state.historySnapshot = null; state.error = ''; state.notice = summary.notice
    state.detailLoading = summary.supported; emit()
    if (!summary.supported) return
    try {
      const value = await client.readMealPlan(id)
      if (!current(token) || sequence !== detailSequence) return
      const detail = mealPlanDetail(value, memberId, id)
      state.currentPlan = detail.plan; state.history = detail.history; emit()
    } catch (error) { handleError(error, token, sequence === detailSequence) }
    finally { if (current(token) && sequence === detailSequence) { state.detailLoading = false; emit() } }
  }
  function showHistory(value = null) {
    if (!unlocked() || state.detailLoading || !state.currentPlan) return
    const row = value === null ? null : state.history.find(item => item.version === value)
    if (value !== null && !row) return
    state.historyVersion = row?.version ?? null; state.historySnapshot = row?.snapshot ?? null; state.swap = null; emit()
  }
  function setDate(value) {
    if (!unlocked()) return
    clearPreview(); state.draft.plan_date = typeof value === 'string' ? value : ''; state.error = ''; emit()
  }
  function dishAt(type, index) { return state.draft.meals.find(meal => meal.meal_type === type)?.dishes[index] }
  function changedDish(form, patch) {
    if (!patch || typeof patch !== 'object') throw validation('菜品输入无效')
    const next = { ...form }
    if (Object.hasOwn(patch, 'recipe_version_id') && patch.recipe_version_id !== form.recipe_version_id) {
      if (!state.recipes.some(row => row.id === patch.recipe_version_id)) throw validation('请选择当前读取的已发布菜谱版本')
      Object.assign(next, blankDish(), { recipe_version_id: patch.recipe_version_id })
    }
    if (Object.hasOwn(patch, 'portion_mode')) {
      if (!['unknown', 'grams', 'reference'].includes(patch.portion_mode)) throw validation('请选择未知、克数或已发布份量参考')
      if (patch.portion_mode !== next.portion_mode) Object.assign(next, { grams: '', portion_reference_id: '', portion_count: '' })
      next.portion_mode = patch.portion_mode
    }
    for (const key of ['grams', 'portion_reference_id', 'portion_count']) {
      if (Object.hasOwn(patch, key)) next[key] = typeof patch[key] === 'string' ? patch[key] : ''
    }
    return next
  }
  async function loadPortions(recipeId, token) {
    if (!recipeId) return
    const sequence = (portionSequences.get(recipeId) || 0) + 1; portionSequences.set(recipeId, sequence)
    state.portionLoading[recipeId] = true; emit()
    try {
      const value = await client.listRecipePortions(recipeId)
      // 发布参考属于菜谱版本，各菜位共用；改选某一菜位不能丢弃另一菜位仍需要的目录。
      if (!current(token) || portionSequences.get(recipeId) !== sequence) return
      state.portions[recipeId] = recipePortions(value, recipeId); emit()
    } catch (error) { handleError(error, token, portionSequences.get(recipeId) === sequence) }
    finally { if (current(token) && portionSequences.get(recipeId) === sequence) { state.portionLoading[recipeId] = false; emit() } }
  }
  function setDish(type, index, patch) {
    if (!unlocked()) return
    const form = dishAt(type, index)
    if (!form) return
    try {
      const next = changedDish(form, patch), recipeChanged = next.recipe_version_id !== form.recipe_version_id
      clearPreview(); Object.assign(form, next); state.error = ''; emit()
      if (recipeChanged) {
        return loadPortions(next.recipe_version_id, ticket())
      }
    } catch (error) { localError(error) }
  }
  function addDish(type) {
    if (!unlocked()) return
    const meal = state.draft.meals.find(row => row.meal_type === type)
    if (!meal) return
    if (meal.dishes.length >= 10) return localError(validation('每餐最多10道菜'))
    clearPreview(); meal.dishes.push(blankDish()); emit()
  }
  function removeDish(type, index) {
    if (!unlocked()) return
    const meal = state.draft.meals.find(row => row.meal_type === type)
    if (!meal || !Number.isInteger(index) || index < 0 || index >= meal.dishes.length) return
    if (meal.dishes.length <= 1) return localError(validation('每餐至少保留1道菜'))
    clearPreview(); meal.dishes.splice(index, 1)
    emit()
  }
  function dishInput(form) {
    if (!approvedRecipes.has(form.recipe_version_id)) throw validation('每道菜须明确选择已发布菜谱版本')
    const result = { recipe_version_id: form.recipe_version_id }
    if (form.portion_mode === 'grams') result.grams = amount(form.grams, 10000, '计划克数')
    else if (form.portion_mode === 'reference') {
      const portion = state.portions[form.recipe_version_id]?.find(row => row.id === form.portion_reference_id)
      if (!portion || portion.recipe_version_id !== form.recipe_version_id) throw validation('请读取并选择属于此菜谱版本的份量参考')
      result.portion_reference_id = portion.id; result.portion_count = amount(form.portion_count, 1000, '参考份量数量')
    } else if (form.portion_mode !== 'unknown') throw validation('份量方式无效')
    return result
  }
  async function preview() {
    if (!unlocked() || state.previewLoading) return
    let spec
    try { spec = { plan_date: validDate(state.draft.plan_date), meals: state.draft.meals.map(meal => ({
      meal_type: meal.meal_type, dishes: meal.dishes.map(dishInput),
    })) } } catch (error) { localError(error); return }
    const token = ticket(), sequence = ++previewSequence
    state.preview = null; state.previewLoading = true; state.busy = true; state.error = ''; state.notice = ''; emit()
    try {
      const value = await client.previewMealPlan(memberId, spec)
      if (!current(token) || sequence !== previewSequence) return
      const result = mealPlanPreview(value, memberId)
      if (result.plan_date !== spec.plan_date || result.meals.some((meal, index) => meal.dishes.length !== spec.meals[index].dishes.length
        || meal.dishes.some((dish, position) => dish.recipe_version_id !== spec.meals[index].dishes[position].recipe_version_id))) {
        throw protocol('服务返回的预览与当前选择不一致')
      }
      state.preview = result; emit()
    } catch (error) { handleError(error, token, sequence === previewSequence) }
    finally { if (current(token) && sequence === previewSequence) { state.previewLoading = false; state.busy = posting; emit() } }
  }

  function startSwap(type, index) {
    if (!unlocked() || state.detailLoading || !state.currentPlan?.editable || state.historyVersion !== null) return
    const dish = state.currentPlan.meals.find(meal => meal.meal_type === type)?.dishes[index]
    if (!dish || !Number.isInteger(index)) return
    clearPreview(); state.swap = { meal_type: type, dish_index: index, replacement: blankDish(), reason: '' }; state.error = ''; emit()
  }
  function setSwap(patch) {
    if (!unlocked() || !state.swap || !patch || typeof patch !== 'object') return
    try {
      const form = state.swap.replacement, next = patch.replacement ? changedDish(form, patch.replacement) : form
      const recipeChanged = next.recipe_version_id !== form.recipe_version_id
      state.swap.replacement = next
      if (Object.hasOwn(patch, 'reason')) state.swap.reason = typeof patch.reason === 'string' ? patch.reason : ''
      state.error = ''; emit()
      if (recipeChanged) {
        return loadPortions(next.recipe_version_id, ticket())
      }
    } catch (error) { localError(error) }
  }
  function cancelSwap() { if (unlocked()) { state.swap = null; emit() } }

  async function finishReadBack(token) {
    const expected = readBack
    if (!expected) return
    const sequence = ++detailSequence; ++listSequence
    state.detailLoading = true; state.listLoading = true; emit()
    try {
      const value = await client.readMealPlan(expected.plan_id)
      if (!current(token) || expected !== readBack || sequence !== detailSequence) return
      const detail = mealPlanDetail(value, memberId, expected.plan_id)
      if (detail.plan.version < expected.min_version) throw protocol('权威餐单版本低于已确认写入结果')
      const listed = await client.listMealPlans(memberId)
      if (!current(token) || expected !== readBack || sequence !== detailSequence) return
      const page = mealPlanList(listed, memberId)
      state.currentPlan = detail.plan; state.history = detail.history; state.selectedPlanId = expected.plan_id
      state.historyVersion = null; state.historySnapshot = null; state.plans = page.plans; state.truncated = page.truncated
      readBack = null; state.readBackPending = false; state.writeOperation = ''; state.error = ''
      state.notice = '写入已确认，已重新读取当前餐单与历史。当前版本可能包含后续修改，请核对。'; emit()
    } catch (error) {
      handleError(error, token)
      if (current(token) && readBack) {
        state.notice = '写入已确认，但权威详情或列表尚未读回。请继续读取结果，无需再次保存或换菜。'; emit()
      }
    } finally { if (current(token) && sequence === detailSequence) { state.detailLoading = false; state.listLoading = false; emit() } }
  }
  async function sendWrite(operation, retry) {
    if (posting || state.blocked || !visible || state.loading || state.needsReload || readBack) return
    if (retry) { if (!writeIntent || !state.writeUnknown || writeIntent.operation !== operation) return }
    else {
      if (!unlocked()) return
      try {
        if (operation === 'save') {
          if (!state.preview || state.previewLoading) return
          writeIntent = { operation, member_id: memberId, body: { preview_id: state.preview.preview_id, client_request_id: newId() } }
        } else {
          if (!state.swap || !state.currentPlan?.editable || state.historyVersion !== null || state.detailLoading) return
          const reason = state.swap.reason.trim()
          if (!reason || reason.length > 500) throw validation('请填写不超过500字的换菜原因')
          const replacement = dishInput(state.swap.replacement)
          writeIntent = { operation, member_id: memberId, plan_id: state.currentPlan.plan_id,
            body: { version: state.currentPlan.version, meal_type: state.swap.meal_type, dish_index: state.swap.dish_index,
              replacement, reason, client_request_id: newId() } }
        }
      } catch (error) { localError(error); return }
    }
    const original = writeIntent, token = ticket()
    posting = true; state.busy = true; state.error = ''; state.writeOperation = operation; emit()
    try {
      const response = operation === 'save' ? await client.saveMealPlan(original.member_id, copy(original.body))
        : await client.swapMealPlan(original.plan_id, copy(original.body))
      if (!current(token) || writeIntent !== original) return
      const result = mealPlanResult(response, memberId, operation === 'swap' ? original.plan_id : null)
      if (operation === 'swap' && result.version <= original.body.version) throw protocol('换菜返回的当前版本未向后推进')
      writeIntent = null; state.writeUnknown = false; clearPreview(); state.swap = null
      state.currentPlan = null; state.history = []; state.historyVersion = null; state.historySnapshot = null
      readBack = { plan_id: result.plan_id, min_version: result.version }; state.readBackPending = true; emit()
      await finishReadBack(token)
    } catch (error) {
      if (current(token) && writeIntent === original) {
        state.writeUnknown = uncertain(error)
        if (!state.writeUnknown) { writeIntent = null; state.writeOperation = '' }
        else state.notice = '服务端可能已提交。编辑已冻结，请明确恢复原请求；恢复使用同一内容和请求键。'
      }
      handleError(error, token)
    } finally { if (current(token)) { posting = false; state.busy = state.previewLoading; emit() } }
  }
  function save(retry = false) { return sendWrite('save', retry === true) }
  function confirmSwap(retry = false) { return sendWrite('swap', retry === true) }
  async function retryReadBack() {
    if (!readBack || !state.readBackPending || posting || state.blocked || !visible) return
    const token = ticket(); posting = true; state.busy = true; state.error = ''; emit()
    try { await finishReadBack(token) }
    finally { if (current(token)) { posting = false; state.busy = false; emit() } }
  }

  return { show, hide, dispose, reload, selectPlan, showHistory, setDate, setDish, addDish, removeDish, searchRecipes,
    preview, save, startSwap, setSwap, cancelSwap, confirmSwap, retryReadBack, getState: () => copy(state) }
}
