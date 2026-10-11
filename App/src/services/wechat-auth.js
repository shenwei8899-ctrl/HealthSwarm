import { request } from './request.js'
import { getSession, setSession, clearSession, sessionRevision } from './session.js'
import { createWechatAuthClient } from './wechat-auth-client.js'

let isWechat = false
// #ifdef MP-WEIXIN
isWechat = true
// #endif

export const wechatAuth = createWechatAuthClient({
  send: request,
  session: { read: getSession, save: setSession, clear: clearSession, revision: sessionRevision },
  appId: (import.meta.env || {}).VITE_WECHAT_APPID || '',
  isWechat,
  getCode: () => new Promise((resolve, reject) => {
    uni.login({ provider: 'weixin', timeout: 10000,
      success: result => result.code ? resolve(result.code) : reject(new Error('微信未返回登录凭证，请重试')),
      fail: () => reject(new Error('微信登录未完成，请重试')),
    })
  }),
})
