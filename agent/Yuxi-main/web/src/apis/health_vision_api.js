import { apiGet, apiPost, apiPut, apiDelete, apiRequest, buildQuery } from './base'

const root = '/api/health/v1'
const draftPath = (kind, id) =>
  `${root}/${kind === 'report' ? 'report-extractions' : 'meal-drafts'}/${id}`
const idempotent = (data) => ({ headers: { 'Idempotency-Key': data.client_request_id } })

/** 健康接口统一走认证封装，不把私有对象地址暴露给页面。 */
export const healthVisionApi = {
  configuration: () => apiGet(`${root}/configuration`),
  configure: (data) => apiPut(`${root}/configuration`, data),
  members: () => apiGet(`${root}/members`),
  createMember: (data) => apiPost(`${root}/members`, data),
  grant: (id, data) => apiPut(`${root}/members/${id}/grants`, data),
  familyProfileLink: (id) => apiGet(`${root}/members/${id}/family-profile-link`),
  linkFamilyProfile: (id, data) => apiPost(`${root}/members/${id}/family-profile-link`, data),
  familyProfile: (id) => apiGet(`${root}/members/${id}/family-profile`),
  profileImportContext: (id, limit = 20, offset = 0) =>
    apiGet(`${root}/members/${id}/profile-import-context?${buildQuery({ limit, offset })}`),
  professionalProfile: (id) => apiGet(`${root}/members/${id}/external-profile-versions/current`),
  importProfessionalProfile: (id, data) =>
    apiPost(`${root}/members/${id}/external-profile-versions`, data),
  approvedQualityRules: (code) =>
    apiGet(`${root}/approved-quality-rules/${encodeURIComponent(code)}`),
  personalTargets: (id, data) => apiPost(`${root}/members/${id}/nutrition-targets`, data),
  consent: (id, data) => apiPost(`${root}/members/${id}/processing-consents`, data),
  createConsultation: (id, data) =>
    apiPost(`${root}/members/${id}/consultations`, data, idempotent(data)),
  createMealPlanner: (id, data) =>
    apiPost(`${root}/members/${id}/meal-planner`, data, idempotent(data)),
  createSafeMealPlanner: (id, data) =>
    apiPost(`${root}/members/${id}/safe-meal-plan-conversations`, data, idempotent(data)),
  createFamilyMealPlanner: (id, data) =>
    apiPost(`${root}/members/${id}/family-meal-planner`, data, idempotent(data)),
  previewMealPlan: (id, data) => apiPost(`${root}/members/${id}/meal-plan-previews`, data),
  mealPlans: (id) => apiGet(`${root}/members/${id}/meal-plans`),
  mealPlan: (id) => apiGet(`${root}/meal-plans/${id}`),
  mealPlanApproval: (id, version) =>
    apiGet(`${root}/meal-plans/${id}/approval-state?${buildQuery({ version })}`),
  saveMealPlan: (id, data) => apiPost(`${root}/members/${id}/meal-plans`, data, idempotent(data)),
  swapMealPlan: (id, data) =>
    apiPost(`${root}/meal-plans/${id}/swap`, data, {
      headers: { 'Idempotency-Key': data.client_request_id, 'If-Match': `"${data.version}"` }
    }),
  safeSwapMealPlan: (id, data) =>
    apiPost(`${root}/meal-plans/${id}/safe-swap`, data, {
      headers: { 'Idempotency-Key': data.client_request_id, 'If-Match': `"${data.version}"` }
    }),
  safeRegenerateMealPlan: (id, data) =>
    apiPost(`${root}/meal-plans/${id}/safe-regenerate`, data, {
      headers: { 'Idempotency-Key': data.client_request_id, 'If-Match': `"${data.version}"` }
    }),
  familySafeSwapMealPlan: (id, data) =>
    apiPost(`${root}/meal-plans/${id}/family-safe-swap`, data, {
      headers: { 'Idempotency-Key': data.client_request_id, 'If-Match': `"${data.version}"` }
    }),
  familySafeRegenerateMealPlan: (id, data) =>
    apiPost(`${root}/meal-plans/${id}/family-safe-regenerate`, data, {
      headers: { 'Idempotency-Key': data.client_request_id, 'If-Match': `"${data.version}"` }
    }),
  familyParticipationMealPlan: (id, data) =>
    apiPost(`${root}/meal-plans/${id}/family-participation`, data, {
      headers: { 'Idempotency-Key': data.client_request_id, 'If-Match': `"${data.version}"` }
    }),
  createDailyConsultation: (id) => apiPost(`${root}/members/${id}/daily-consultations`),
  memberMemory: (id) => apiGet(`${root}/members/${id}/memory`),
  memoryHistory: (id) => apiGet(`${root}/memory/${id}`),
  editMemory: (id, data) =>
    apiRequest(`${root}/memory/${id}`, {
      method: 'PATCH',
      headers: { 'Idempotency-Key': data.client_request_id, 'If-Match': `"${data.version}"` },
      body: JSON.stringify(data)
    }),
  revokeMemory: (id, data) =>
    apiPost(`${root}/memory/${id}/revoke`, data, {
      headers: { 'Idempotency-Key': data.client_request_id, 'If-Match': `"${data.version}"` }
    }),
  dailyHistory: (id, before) =>
    apiGet(`${root}/members/${id}/daily-conversations?${buildQuery({ before })}`),
  dailySummary: (thread) => apiGet(`${root}/daily-conversations/${thread}/summary`),
  refreshDailySummary: (thread) => apiPost(`${root}/daily-conversations/${thread}/summary`),
  upload: (data) => apiPost(`${root}/uploads`, data),
  removeUpload: (id) => apiDelete(`${root}/uploads/${id}`),
  preview: async (id, page = 0) => {
    const response = await apiGet(
      `${root}/uploads/${id}/preview?${buildQuery({ page_index: page })}`,
      {},
      true,
      'blob'
    )
    return response.blob()
  },
  createTask: (kind, data) =>
    apiPost(
      `${root}/${kind === 'report' ? 'report-tasks' : 'meal-photo-tasks'}`,
      data,
      idempotent(data)
    ),
  list: (memberId) => apiGet(`${root}/members/${memberId}/vision`),
  statistics: (memberId, kind) =>
    apiGet(`${root}/members/${memberId}/vision-statistics?${buildQuery({ kind })}`),
  cancel: (id) => apiPost(`${root}/vision-tasks/${id}/cancel`),
  task: (id) => apiGet(`${root}/vision-tasks/${id}`),
  retry: (id, data) => apiPost(`${root}/vision-tasks/${id}/retry`, data, idempotent(data)),
  reprocessReport: (data) =>
    apiPost(`${root}/report-page-tasks`, data, {
      headers: { 'Idempotency-Key': data.client_request_id, 'If-Match': `"${data.version}"` }
    }),
  manual: (data) => apiPost(`${root}/manual-drafts`, data),
  draft: (kind, id) => apiGet(draftPath(kind, id)),
  patch: (kind, id, data) =>
    apiRequest(draftPath(kind, id), {
      method: 'PATCH',
      headers: { 'If-Match': `"${data.version}"` },
      body: JSON.stringify(data)
    }),
  calculate: (id, version) => apiPost(`${draftPath('meal', id)}/calculate`, { version }),
  confirm: (kind, id, data) => apiPost(`${draftPath(kind, id)}/confirm`, data, idempotent(data)),
  records: (memberId, kind) =>
    apiGet(`${root}/members/${memberId}/${kind === 'report' ? 'observations' : 'diet-logs'}`),
  mealFeedback: (id) => apiGet(`${root}/diet-logs/${id}/feedback`),
  saveMealFeedback: (id, data) =>
    apiPut(`${root}/diet-logs/${id}/feedback`, data, {
      headers: { 'Idempotency-Key': data.client_request_id, 'If-Match': `"${data.version}"` }
    }),
  revokeMealFeedback: (id, data) =>
    apiPost(`${root}/diet-logs/${id}/feedback/revoke`, data, {
      headers: { 'Idempotency-Key': data.client_request_id, 'If-Match': `"${data.version}"` }
    }),
  foods: (query = '') => apiGet(`${root}/foods?${buildQuery({ q: query })}`),
  publishFood: (data) => apiPost(`${root}/foods`, data),
  recipes: (query = '') => apiGet(`${root}/recipes?${buildQuery({ q: query })}`),
  publishRecipe: (data) => apiPost(`${root}/recipes`, data),
  portions: (mapping) => apiGet(`${root}/portion-references?${buildQuery(mapping)}`),
  publishPortion: (data) => apiPost(`${root}/portion-references`, data)
}
