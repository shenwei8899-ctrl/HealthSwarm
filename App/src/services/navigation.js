import { isMockMode } from './config.js'
const apiPages = new Set(['pages/index/index', 'pages/account/index'])
export function registerApiPages(pages) { pages.forEach(page => apiPages.add(page.replace(/^\//, '').split('?')[0])) }
export function canOpenPage(url) { return isMockMode || apiPages.has((url || '').replace(/^\//, '').split('?')[0]) }
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
