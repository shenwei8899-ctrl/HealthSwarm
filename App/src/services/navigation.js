import { isMockMode, isCommerceEnabled } from './config.js'
import { resolveAppEntry } from './app-entry.js'
import { captureInvitation, rememberInvitation } from './family-invitations.js'
const apiPages = new Set(['pages/index/index', 'pages/invite/index', 'pages/account/index', 'pages/family-shared/index',
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
  if (path === 'pages/shop/index') {
    if (/[?&]commerce=1(?:&|$)/.test(url)) return false
    if (isMockMode) return /[?&](meal|daily|bundle|source)=/.test(url)
    return /[?&]arrangement=[0-9a-f-]{36}(?:&|$)/i.test(url)
      && /[?&]version=[1-9][0-9]*(?:&|$)/.test(url)
      && /[?&]date=\d{4}-\d{2}-\d{2}(?:&|$)/.test(url)
      && /[?&](meal=(breakfast|lunch|dinner)|daily=1)(?:&|$)/.test(url)
      || /[?&]conversation=[0-9a-f-]{36}(?:&|$)/i.test(url)
  }
  return isMockMode || path === 'pages/cook/index' && isCommerceEnabled && /[?&]commerce=1(?:&|$)/.test(url)
    || apiPages.has(path) || isCommerceEnabled && commercePages.has(path)
}
let forwarding = false
export function guardInitialH5Route(location, history) {
  const route = location.hash.slice(1)
  const match = route.match(/^\/?pages\/invite\/index\?[^#]*\btoken=([^&]+)/)
  if (match) { try { rememberInvitation(decodeURIComponent(match[1])) } catch {} }
  if (!isMockMode && route && route !== '/' && route !== '/pages/index/index') {
    history.replaceState(null, '', location.pathname + location.search + '#/pages/index/index')
  } else if (route && route !== '/' && !canOpenPage(route)) history.replaceState(null, '', location.pathname + location.search + '#/pages/index/index')
}
export function protectedDestination(requested, entry) {
  const path = requested.split('?')[0]
  if (entry.startsWith('/pages/invite/index')) return entry
  if (entry === '/pages/chat/index') return canOpenPage(requested) ? requested : entry
  if (entry === '/pages/onboarding/index' && ['/pages/reports/index','/pages/reports/detail','/pages/health/vision'].includes(path)) return requested
  return entry
}
function forward(method, options) {
  // H5 按静态 API 调用导入路由能力；uni[method] 无法被编译器识别。
  const navigate = {
    navigateTo: () => uni.navigateTo(options),
    redirectTo: () => uni.redirectTo(options),
    reLaunch: () => uni.reLaunch(options),
    switchTab: () => uni.switchTab(options),
  }
  forwarding = true
  try { navigate[method]() } finally { forwarding = false }
}
export async function checkCurrentEntry(options) {
  if (isMockMode) return
  captureInvitation(options)
  const pages = typeof getCurrentPages === 'function' ? getCurrentPages() : []
  const page = pages.at(-1)
  const current = '/' + (options?.path ? launchRoute(options) : launchRoute({path:page?.route || 'pages/index/index',query:page?.options || {}})).replace(/^\//,'')
  if (current === '/pages/index/index') return
  try {
    const entry = await resolveAppEntry()
    const target = protectedDestination(current, entry)
    if (target !== current) forward('reLaunch', {url:target})
  } catch { forward('reLaunch', {url:'/pages/index/index'}) }
}
export function installRouteGuards() {
  for (const method of ['navigateTo', 'redirectTo', 'reLaunch', 'switchTab']) {
    uni.addInterceptor(method, { invoke(options) {
      if (forwarding) return
      const url = options.url || '', path = url.split('?')[0]
      const match = url.match(/^\/?pages\/invite\/index\?[^#]*\btoken=([^&]+)/)
      if (match) { try { rememberInvitation(decodeURIComponent(match[1])) } catch { return false } }
      if (path === '/pages/index/index') return
      if (isMockMode) {
        if (!canOpenPage(url)) { forward('redirectTo', {url:'/pages/chat/index'}); return false }
        return
      }
      void resolveAppEntry().then(entry => forward(method, {...options,url:protectedDestination(url,entry)}))
        .catch(error => { uni.showToast({title:error.message||'请重新读取登录状态',icon:'none'});forward('reLaunch',{url:'/pages/index/index'}) })
      return false
    } })
  }
}
