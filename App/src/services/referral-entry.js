import { createReferralEntry } from './referral-entry-client.js'
import { request } from './request.js'
import { getSession } from './session.js'

export const referralEntry = createReferralEntry({
  storage: { getStorageSync: key => uni.getStorageSync(key), setStorageSync: (key, value) => uni.setStorageSync(key, value) },
  send: request, session: getSession,
})
