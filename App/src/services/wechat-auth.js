import { request } from './request.js'
import { getSession, setSession, clearSession, sessionRevision } from './session.js'
import { createWechatAuthClient } from './wechat-auth-client.js'
import { createBusinessAuthClient } from './business-auth-client.js'
import { canUsePasswordLogin } from './config.js'

let isWechat = false
// #ifdef MP-WEIXIN
isWechat = true
// #endif

const client = createWechatAuthClient({
  send: request,
  session: { read: getSession, save: setSession, clear: clearSession, revision: sessionRevision },
  appId: (import.meta.env || {}).VITE_WECHAT_APPID || '',
  isWechat,
  allowPasswordLogin: canUsePasswordLogin,
  getCode: () => new Promise((resolve, reject) => {
    uni.login({ provider: 'weixin', timeout: 10000,
      success: result => result.code ? resolve(result.code) : reject(new Error('微信未返回登录凭证，请重试')),
      fail: () => reject(new Error('微信登录未完成，请重试')),
    })
  }),
})
const business = createBusinessAuthClient({ send: request,
  session: { read: getSession, save: setSession, clear: clearSession, revision: sessionRevision } })
export const wechatAuth = {
  ...client,
  loginWithPassword: business.login,
  restore: () => getSession()?.authSource === 'business' ? business.restore() : client.restore(),
  selectFamily: id => getSession()?.authSource === 'business' ? business.selectFamily(id) : client.selectFamily(id),
  cancelPending() { business.cancelPending(); client.cancelPending() },
  logout() { business.cancelPending(); client.logout() },
}
