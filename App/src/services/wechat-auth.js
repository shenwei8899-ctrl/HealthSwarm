import { request } from './request.js'
import { getSession, setSession, clearSession, sessionRevision } from './session.js'
import { createWechatAuthClient } from './wechat-auth-client.js'
import { canUsePasswordLogin, canUseBusinessLogin } from './config.js'
import { createBusinessAuthClient } from './business-auth-client.js'

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
const business = canUseBusinessLogin ? createBusinessAuthClient({
  send: request,
  session: { read: getSession, save: setSession, clear: clearSession, revision: sessionRevision },
}) : null
// 所有页面共用同一登录、恢复与家庭选择入口；本机联调仍由后端验证密码和权限。
export const wechatAuth = business ? {
  ...business,
  login: ({ identifier, password } = {}) => business.login(identifier, password),
} : client
