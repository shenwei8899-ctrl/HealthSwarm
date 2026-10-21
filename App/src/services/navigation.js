import { isMockMode, isCommerceEnabled } from './config.js'
const apiPages = new Set(['pages/index/index', 'pages/account/index', 'pages/family-shared/index',
  'pages/records/index', 'pages/meal-photo/index', 'pages/indicators/index', 'pages/chat/agent', 'pages/chat/camera', 'pages/chat/history', 'pages/profile/member', 'pages/scan/index', 'pages/records/detail', 'pages/memories/index', 'pages/feedback/index', 'pages/exclusive-plans/index', 'pages/health/vision', 'pages/health/plans',
  'pages/family-select/index', 'pages/my/index', 'pages/profile/index', 'pages/settings/privacy', 'pages/settings/health-profile',
  'pages/onboarding/index', 'pages/chat/index', 'pages/shop/index', 'pages/recipe/index',
  'pages/orders/index', 'pages/orders/detail', 'pages/address/index', 'pages/address/edit'])
const commercePages = new Set(['pages/purchase/index'])
export function launchRoute(options) {
  const query = Object.entries(options?.query || {}).map(([key, value]) => encodeURIComponent(key) + '=' + encodeURIComponent(String(value))).join('&')
  return (options?.path || '') + (query ? '?' + query : '')
}
export function registerApiPages(pages) { pages.forEach(page => apiPages.add(page.replace(/^\//, '').split('?')[0])) }
export function canOpenPage(url) {
  const path = (url || '').replace(/^\//, '').split('?')[0]
  return isMockMode || path === 'pages/cook/index' && isCommerceEnabled && /[?&]commerce=1(?:&|$)/.test(url) || apiPages.has(path) || isCommerceEnabled && (commercePages.has(path) ||
    path === 'pages/shop/index' && /[?&]commerce=1(?:&|$)/.test(url) && !/[?&](meal|daily|bundle|plan|source)=/.test(url))
}
export function guardInitialH5Route(location, history) {
  const route = location.hash.slice(1)
  // Normalize before Uni initializes its router; onLaunch navigation is too late for H5 deep links.
  if (route && route !== '/' && !canOpenPage(route)) history.replaceState(null, '', location.pathname + location.search + '#/pages/index/index')
}
export function installRouteGuards() {
  for (const method of ['navigateTo', 'redirectTo', 'reLaunch', 'switchTab']) {
    uni.addInterceptor(method, { invoke(options) {
      if (!canOpenPage(options.url)) { uni.showToast({ title: '服务暂不可用，请稍后重试', icon: 'none' }); return false }
    } })
  }
}
