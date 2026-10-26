import { isMockMode, isCommerceEnabled } from './config.js'
import { resolveAppEntry } from './app-entry.js'
import { captureInvitation, rememberInvitation } from './family-invitations.js'
import { storageContext } from './storage.js'
import { getSession } from './session.js'
const apiPages = new Set(['pages/index/index', 'pages/invite/index', 'pages/account/index', 'pages/family-shared/index',
  'pages/records/index', 'pages/meal-photo/index', 'pages/indicators/index', 'pages/chat/agent', 'pages/chat/camera', 'pages/chat/history', 'pages/profile/member', 'pages/scan/index', 'pages/records/detail', 'pages/memories/index', 'pages/feedback/index', 'pages/exclusive-plans/index', 'pages/exclusive-plans/detail', 'pages/exclusive-plans/schedule', 'pages/health/vision', 'pages/health/plans',
  'pages/family-select/index', 'pages/my/index', 'pages/profile/index', 'pages/settings/privacy',
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
let forwarding = false, navigationFlight = null, entryCheck = null, installed = false
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
  if (entry === '/pages/onboarding/index' && ['/pages/profile/index','/pages/profile/member','/pages/family-shared/index','/pages/reports/index','/pages/reports/detail','/pages/health/vision'].includes(path)) return requested
  return entry
}
function currentRoute(options) {
  const pages = typeof getCurrentPages === 'function' ? getCurrentPages() : []
  const page = pages.at(-1)
  return '/' + launchRoute(page ? {path:page.route,query:page.options || {}} : options || {path:'pages/index/index'}).replace(/^\//,'')
}
function forward(method, options) {
  const scope=storageContext(),account=getSession(),previous=navigationFlight
  const current=()=>scope===storageContext()||!account?.householdId&&account?.accountId===getSession()?.accountId&&account?.token===getSession()?.token
  if (previous?.scope===scope && previous.method===method && previous.url===options.url) {
    previous.done.then(result=>{options[result.failed?'fail':'success']?.(result.value);options.complete?.(result.value)})
    return previous.done
  }
  let settle
  const flight={scope,method,url:options.url,done:new Promise(resolve=>{settle=resolve})}
  navigationFlight=flight
  function finish(failed,value) {
    if(flight.finished)return
    flight.finished=true
    if(navigationFlight===flight)navigationFlight=null
    settle({failed,value})
    options[failed?'fail':'success']?.(value);options.complete?.(value)
  }
  void (async()=>{
    try {
      if(previous)await previous.done
      if(!current()) {finish(true,{errMsg:method+':fail 账号已变化',code:'SESSION_CHANGED'});return}
      let url=options.url
      if(!isMockMode && url.split('?')[0]!=='/pages/index/index') url=protectedDestination(url,await resolveAppEntry())
      else if(isMockMode&&!canOpenPage(url))url='/pages/chat/index'
      if(!current()) {finish(true,{errMsg:method+':fail 账号已变化',code:'SESSION_CHANGED'});return}
      if(['reLaunch','redirectTo','switchTab'].includes(method)&&url===currentRoute()) {finish(false,{errMsg:method+':ok'});return}
      let outcome
      const target={...options,url,success:value=>{outcome={failed:false,value}},fail:value=>{outcome={failed:true,value}},complete:value=>finish(outcome?.failed??/:fail/.test(value?.errMsg||''),outcome?.value||value)}
      // 静态 API 调用供 H5 编译器识别；锁保留至原生导航回调完成。
      const navigate={navigateTo:()=>uni.navigateTo(target),redirectTo:()=>uni.redirectTo(target),reLaunch:()=>uni.reLaunch(target),switchTab:()=>uni.switchTab(target)}
      forwarding=true
      try { navigate[method]() } finally { forwarding=false }
    } catch(error) {
      finish(true,{errMsg:method+':fail '+(error.message||'导航未完成'),code:error.code})
    }
  })()
  return flight.done
}
export function checkCurrentEntry(options) {
  if (isMockMode) return
  captureInvitation(options)
  if(navigationFlight)return navigationFlight.done
  if(entryCheck)return entryCheck
  const initialRoute=currentRoute(options)
  if (initialRoute === '/pages/index/index') return
  const scope=storageContext(),account=getSession()
  const current=()=>scope===storageContext()||!account?.householdId&&account?.accountId===getSession()?.accountId&&account?.token===getSession()?.token
  entryCheck=(async()=>{
    try {
      const entry=await resolveAppEntry()
      if(!current()||navigationFlight)return
      const route=currentRoute(options),target=protectedDestination(route,entry)
      if(target!==route) {
        const result=await forward('reLaunch',{url:target})
        if(result.failed&&result.value.code!=='SESSION_CHANGED')uni.showToast({title:result.value.errMsg,icon:'none'})
      }
    } catch(error) {
      if(scope===storageContext()&&error.code!=='SESSION_CHANGED') {
        uni.showToast({title:error.message||'请重新读取登录状态',icon:'none'})
        if([401,403,404].includes(Number(error.code)))await forward('reLaunch',{url:'/pages/index/index'})
      }
    }
  })().finally(()=>{entryCheck=null})
  return entryCheck
}
export function installRouteGuards() {
  if(installed)return
  installed=true
  for (const method of ['navigateTo', 'redirectTo', 'reLaunch', 'switchTab']) {
    uni.addInterceptor(method, { invoke(options) {
      if (forwarding) return
      const url = options.url || ''
      const match = url.match(/^\/?pages\/invite\/index\?[^#]*\btoken=([^&]+)/)
      if (match) { try { rememberInvitation(decodeURIComponent(match[1])) } catch { return false } }
      if(isMockMode&&canOpenPage(url))return
      void forward(method,options)
      return false
    } })
  }
}
