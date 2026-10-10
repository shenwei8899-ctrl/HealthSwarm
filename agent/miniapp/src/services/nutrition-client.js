const SESSION_STORAGE_KEY = 'healthswarm.nutrition.session'

export class NutritionClientError extends Error {
  constructor(status, code, message) {
    super(message)
    this.name = 'NutritionClientError'
    this.status = status
    this.code = code
  }
}

/** 使用现有 Yuxi 账户读取当前授权成员，不在客户端推断身份。 */
export function createNutritionClient({ request, storage, apiBase = '/api' }) {
  if (typeof request !== 'function' || !storage) {
    throw new TypeError('需要请求适配器和会话存储')
  }
  const base = apiBase.replace(/\/+$/, '')
  let session = null
  let revision = 0
  const listeners = new Set()

  function getSession() {
    return session ? { ...session } : null
  }

  function subscribeSession(listener) {
    listeners.add(listener)
    listener(getSession(), revision)
    return () => listeners.delete(listener)
  }

  async function login(identifier, password) {
    const started = resetSession(true)
    if (typeof identifier !== 'string' || !identifier.trim() || typeof password !== 'string' || !password) {
      throw new NutritionClientError(422, 'credentials_required', '请填写账号和密码')
    }
    const body = await send('/auth/token', {
      method: 'POST',
      data: `username=${encodeURIComponent(identifier.trim())}&password=${encodeURIComponent(password)}`,
      contentType: 'application/x-www-form-urlencoded',
      expectedRevision: started,
    })
    requireCurrentRevision(started)
    const authenticated = sessionProjection(body)
    persistSession(authenticated)
    session = authenticated
    notifySession()
    return getSession()
  }

  async function restoreSession() {
    const started = resetSession(false)
    const stored = readStoredSession()
    if (!stored) return null
    let candidate
    try {
      candidate = sessionProjection(stored)
    } catch {
      removeStoredSession()
      return null
    }
    const profile = await send('/auth/me', {
      token: candidate.access_token,
      expectedRevision: started,
    })
    requireCurrentRevision(started)
    const authenticated = sessionProjection({ ...profile, access_token: candidate.access_token })
    if (authenticated.uid !== candidate.uid) {
      resetSession(true)
      throw new NutritionClientError(401, 'session_identity_changed', '保存的会话与当前账号不一致，请重新登录')
    }
    persistSession(authenticated)
    session = authenticated
    notifySession()
    return getSession()
  }

  function logout() {
    resetSession(true)
  }

  function listFamilies() {
    return authenticatedRequest('/family')
  }

  function getFamily(familyId) {
    return authenticatedRequest(`/family/${pathId(familyId)}`)
  }

  function listHealthMembers() {
    return authenticatedRequest('/health/v1/members')
  }

  function readProfileLink(healthId) {
    return authenticatedRequest(`/health/v1/members/${pathId(healthId)}/family-profile-link`)
  }

  function linkProfile(healthId, data) {
    if (data?.confirmed_identity !== true) {
      return Promise.reject(new NutritionClientError(422, 'identity_confirmation_required', '请明确确认两个成员是同一个本人'))
    }
    const payload = {
      family_id: pathId(data.family_id, false),
      source_member_id: pathId(data.source_member_id, false),
      confirmed_identity: true,
    }
    return authenticatedRequest(`/health/v1/members/${pathId(healthId)}/family-profile-link`, {
      method: 'POST',
      data: payload,
    })
  }

  function readFamilyProfile(healthId) {
    return authenticatedRequest(`/health/v1/members/${pathId(healthId)}/family-profile`)
  }

  /** 普通餐单直接使用业务接口，不触发模型或专业审批。 */
  function listMealPlans(memberId) {
    return authenticatedRequest(`/health/v1/members/${pathId(memberId)}/meal-plans`)
  }

  function readMealPlan(planId) {
    return authenticatedRequest(`/health/v1/meal-plans/${pathId(planId)}`)
  }

  function listPublishedRecipes(query = '') {
    if (typeof query !== 'string' || query.length > 120) {
      return Promise.reject(new NutritionClientError(422, 'invalid_recipe_query', '菜谱查询须为不超过120字的文本'))
    }
    return authenticatedRequest(`/health/v1/recipes?q=${encodeURIComponent(query)}`)
  }

  function listRecipePortions(recipeVersionId) {
    return authenticatedRequest(`/health/v1/portion-references?recipe_version_id=${pathId(recipeVersionId)}`)
  }

  function previewMealPlan(memberId, spec) {
    return authenticatedRequest(`/health/v1/members/${pathId(memberId)}/meal-plan-previews`, {
      method: 'POST', data: mealPlanSpecProjection(spec),
    })
  }

  function saveMealPlan(memberId, data) {
    const key = pathId(data?.client_request_id, false)
    return authenticatedRequest(`/health/v1/members/${pathId(memberId)}/meal-plans`, {
      method: 'POST', data: { preview_id: pathId(data?.preview_id, false), client_request_id: key }, requestKey: key,
    })
  }

  function swapMealPlan(planId, data) {
    if (!Number.isSafeInteger(data?.version) || data.version < 1
      || !Number.isInteger(data.dish_index) || data.dish_index < 0 || data.dish_index > 9
      || typeof data.reason !== 'string' || data.reason.length < 1 || data.reason.length > 500) {
      throw invalidMealPlanInput()
    }
    const key = pathId(data.client_request_id, false)
    const payload = {
      version: data.version,
      meal_type: mealType(data.meal_type),
      dish_index: data.dish_index,
      replacement: plannedDishProjection(data.replacement),
      reason: data.reason,
      client_request_id: key,
    }
    return authenticatedRequest(`/health/v1/meal-plans/${pathId(planId)}/swap`, {
      method: 'POST', data: payload, requestKey: key, matchVersion: payload.version,
    })
  }

  /** 读取当前审批的处理方与用途，不接收客户端模型配置。 */
  function readConsultationConfiguration() {
    return authenticatedRequest('/health/v1/configuration')
  }

  function setConsultationConsent(healthId, data) {
    if (typeof data?.accepted !== 'boolean' || typeof data.processor !== 'string' || !data.processor
      || typeof data.policy_version !== 'string' || !data.policy_version) {
      return Promise.reject(new NutritionClientError(422, 'consent_required', '请核对咨询处理方和政策并明确选择同意状态'))
    }
    return authenticatedRequest(`/health/v1/members/${pathId(healthId)}/processing-consents`, {
      method: 'POST',
      data: { purpose: 'consultation', accepted: data.accepted, processor: data.processor, policy_version: data.policy_version },
    })
  }

  function createDailyConsultation(healthId) {
    return authenticatedRequest(`/health/v1/members/${pathId(healthId)}/daily-consultations`, { method: 'POST' })
  }

  function createConsultation(healthId, data) {
    const key = pathId(data?.client_request_id, false)
    return authenticatedRequest(`/health/v1/members/${pathId(healthId)}/consultations`, {
      method: 'POST', data: { client_request_id: key }, requestKey: key,
    })
  }

  function listDailyConversations(healthId, before) {
    return authenticatedRequest(`/health/v1/members/${pathId(healthId)}/daily-conversations${before ? `?before=${encodeURIComponent(before)}` : ''}`)
  }

  function listMemberConsultations(healthId, { limit = 20, offset = 0 } = {}) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 50 || !Number.isSafeInteger(offset) || offset < 0) {
      return Promise.reject(new NutritionClientError(422, 'invalid_pagination', '咨询分页参数不符合接口要求'))
    }
    return authenticatedRequest(`/health/v1/members/${pathId(healthId)}/consultations?limit=${limit}&offset=${offset}`)
  }

  function readThreadHistory(threadId) {
    return authenticatedRequest(`/chat/thread/${pathId(threadId)}/history`)
  }

  /** 每次恢复沿用相同正文及请求键，成员和模型仍由固定线程决定。 */
  function submitConsultationRequest(threadId, data) {
    if (typeof data?.query !== 'string' || !data.query.trim()) {
      return Promise.reject(new NutritionClientError(422, 'question_required', '请填写营养问题'))
    }
    return authenticatedRequest('/agent/runs', {
      method: 'POST',
      data: { agent_slug: 'health-consultation', thread_id: pathId(threadId, false), query: data.query, meta: { request_id: pathId(data.request_id, false) } },
    })
  }

  function readAgentRequest(requestId) {
    return authenticatedRequest(`/agent/requests/${pathId(requestId)}`)
  }

  function readAgentRun(runId) {
    return authenticatedRequest(`/agent/runs/${pathId(runId)}`)
  }

  function readAgentRunResult(runId) {
    return authenticatedRequest(`/agent/runs/${pathId(runId)}/result`)
  }

  function readThreadActiveRun(threadId) {
    return authenticatedRequest(`/agent/thread/${pathId(threadId)}/active_run`)
  }

  function authenticatedRequest(path, options = {}) {
    if (!session) {
      return Promise.reject(new NutritionClientError(401, 'login_required', '请先登录'))
    }
    return send(path, { ...options, token: session.access_token, expectedRevision: revision })
  }

  function send(path, { method = 'GET', data, token, contentType = 'application/json', expectedRevision, requestKey, matchVersion }) {
    return new Promise((resolve, reject) => {
      const stale = () => revision !== expectedRevision
      const staleError = () => new NutritionClientError(0, 'stale_session', '账号会话已变更，请重新操作')
      const fail = (error) => {
        if (stale()) return reject(staleError())
        reject(error instanceof NutritionClientError
          ? error
          : new NutritionClientError(0, 'network_error', '无法连接营养服务，请检查网络后重试'))
      }
      const header = { 'Content-Type': contentType }
      if (token) header.Authorization = `Bearer ${token}`
      if (requestKey) header['Idempotency-Key'] = requestKey
      if (matchVersion !== undefined) header['If-Match'] = `"${matchVersion}"`
      try {
        request({
          url: `${base}${path}`,
          method,
          timeout: 15000,
          data,
          header,
          success(response) {
            if (stale()) return reject(staleError())
            const status = response?.statusCode
            if (!Number.isInteger(status)) {
              return reject(new NutritionClientError(0, 'invalid_response', '营养服务响应格式异常'))
            }
            if (status >= 200 && status < 300) return resolve(response.data)
            const error = responseError(status, response.data)
            if (status === 401) {
              try {
                resetSession(true)
              } catch (storageError) {
                return reject(storageError)
              }
            }
            reject(error)
          },
          fail,
        })
      } catch (error) {
        fail(error)
      }
    })
  }

  function resetSession(removeStored) {
    revision += 1
    session = null
    notifySession()
    if (removeStored) removeStoredSession()
    return revision
  }

  function requireCurrentRevision(expected) {
    if (revision !== expected) {
      throw new NutritionClientError(0, 'stale_session', '账号会话已变更，请重新操作')
    }
  }

  function notifySession() {
    for (const listener of listeners) {
      try {
        listener(getSession(), revision)
      } catch {
        // 页面监听失败不能改变已经验证的会话结果。
        console.error('营养会话监听器执行失败')
      }
    }
  }

  function readStoredSession() {
    try {
      return storage.getStorageSync(SESSION_STORAGE_KEY)
    } catch {
      throw new NutritionClientError(0, 'storage_unavailable', '无法读取登录会话，请检查本机存储')
    }
  }

  function persistSession(value) {
    try {
      storage.setStorageSync(SESSION_STORAGE_KEY, { ...value })
    } catch {
      throw new NutritionClientError(0, 'storage_unavailable', '无法保存登录会话，请检查本机存储')
    }
  }

  function removeStoredSession() {
    try {
      storage.removeStorageSync(SESSION_STORAGE_KEY)
    } catch {
      throw new NutritionClientError(0, 'storage_unavailable', '无法清除登录会话，请检查本机存储')
    }
  }

  return {
    getSession,
    subscribeSession,
    get sessionRevision() { return revision },
    login,
    restoreSession,
    logout,
    listFamilies,
    getFamily,
    listHealthMembers,
    readProfileLink,
    linkProfile,
    readFamilyProfile,
    listMealPlans,
    readMealPlan,
    listPublishedRecipes,
    listRecipePortions,
    previewMealPlan,
    saveMealPlan,
    swapMealPlan,
    readConsultationConfiguration,
    setConsultationConsent,
    createDailyConsultation,
    createConsultation,
    listDailyConversations,
    listMemberConsultations,
    readThreadHistory,
    submitConsultationRequest,
    readAgentRequest,
    readAgentRun,
    readAgentRunResult,
    readThreadActiveRun,
  }
}

/** 只复制业务DTO字段；服务端仍拥有日期、份量精度及发布版本校验。 */
function mealPlanSpecProjection(spec) {
  if (typeof spec?.plan_date !== 'string' || !spec.plan_date
    || !Array.isArray(spec.meals) || spec.meals.length !== 3) {
    throw invalidMealPlanInput()
  }
  const meals = spec.meals.map((meal) => {
    if (!Array.isArray(meal?.dishes) || meal.dishes.length < 1 || meal.dishes.length > 10) {
      throw invalidMealPlanInput()
    }
    return { meal_type: mealType(meal.meal_type), dishes: meal.dishes.map(plannedDishProjection) }
  })
  if (new Set(meals.map((meal) => meal.meal_type)).size !== 3) throw invalidMealPlanInput()
  return { plan_date: spec.plan_date, meals }
}

/** 计划量保留原始数值文本，不计算营养，也不接受嵌套健康对象。 */
function plannedDishProjection(dish) {
  const result = { recipe_version_id: pathId(dish?.recipe_version_id, false) }
  for (const key of ['grams', 'portion_count']) {
    const value = dish[key]
    if (value === undefined) continue
    if (value !== null && (typeof value !== 'string' && typeof value !== 'number'
      || typeof value === 'string' && !value.trim() || !Number.isFinite(Number(value)) || Number(value) <= 0)) {
      throw invalidMealPlanInput()
    }
    result[key] = value
  }
  if (dish.portion_reference_id !== undefined) {
    result.portion_reference_id = dish.portion_reference_id === null ? null : pathId(dish.portion_reference_id, false)
  }
  if (result.portion_reference_id
    ? result.grams != null || result.portion_count == null
    : result.portion_count != null) {
    throw invalidMealPlanInput()
  }
  return result
}

function mealType(value) {
  if (!['breakfast', 'lunch', 'dinner'].includes(value)) throw invalidMealPlanInput()
  return value
}

function invalidMealPlanInput() {
  return new NutritionClientError(422, 'invalid_meal_plan_input', '请核对三餐、菜谱版本、计划份量及换菜信息')
}

function sessionProjection(data) {
  if (!data || ['access_token', 'uid', 'username'].some((key) => typeof data[key] !== 'string' || !data[key])) {
    throw new NutritionClientError(0, 'invalid_response', '营养服务未返回有效账号会话')
  }
  return { access_token: data.access_token, uid: data.uid, username: data.username }
}

function pathId(value, encode = true) {
  if (typeof value !== 'string' || !value) {
    throw new NutritionClientError(422, 'member_id_required', '请选择服务端返回的家庭和成员')
  }
  return encode ? encodeURIComponent(value) : value
}

function responseError(status, body) {
  const detail = body?.detail ?? body
  const code = typeof body?.code === 'string' ? body.code
    : typeof detail?.error === 'string' ? detail.error
      : typeof detail?.code === 'string' ? detail.code : `http_${status}`
  const message = typeof body?.message === 'string' ? body.message
    : typeof detail === 'string' ? detail
      : typeof detail?.message === 'string' ? detail.message
      : status === 429 ? '请求过于频繁，请稍后再试'
        : status === 422 ? '请求参数不符合接口要求' : `营养服务请求失败（${status}）`
  return new NutritionClientError(status, code, message)
}
