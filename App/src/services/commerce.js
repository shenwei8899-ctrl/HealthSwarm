import { ref } from "vue";
import { createCommerceClient } from "./commerce-client.js";
import { getSession, setSession, clearSession } from "./session.js";
import { isMockMode, isCommerceEnabled } from "./config.js";
import { getProfile, saveProfile, newMember, normalizeMember } from "../utils/profile.js";
import { scopedStorage } from "./storage.js";
import { storageContext, storageScope } from "./storage.js";
import { commerceApiBaseUrl } from "./config.js";

export const commerceSessionEpoch = ref(0);
export const usesCommerceIdentity = isMockMode && isCommerceEnabled;
export const usesAgentIdentity = !isMockMode && isCommerceEnabled;
function activateIdentity(result) {
  if (!usesCommerceIdentity) return;
  const accountId = "commerce:" + (result.identity_namespace || commerceApiBaseUrl) + ":" + result.userId;
  // This is a local profile namespace, not an Agent household or cloud identity.
  const householdId = "local-health:" + accountId;
  if (getSession()?.authSource === "commerce" && getSession()?.accountId === accountId && getSession()?.householdId === householdId) return;
  setSession({ accountId, householdId, authSource: "commerce", commerceMemberId: result.userId, localHealthOnly: true, isDemo: false });
  if (!scopedStorage.getStorageSync("family-profile-v2")) {
    const member = normalizeMember({ ...newMember(0), name: "我", relation: "本人", claimedBy: "creator" });
    saveProfile({ householdName: "我的家", usageMode: "个人使用", sharedDinerCount: 1, members: [member], defaultDiners: [member.id], goals: [], tastes: [], memories: [] });
  }
}
let isWechat = false;
// #ifdef MP-WEIXIN
isWechat = true;
// #endif
const native = (invoke) => (options) =>
  new Promise((resolve, reject) =>
    invoke({ ...options, success: resolve, fail: reject }),
  );
let baseUrl = commerceApiBaseUrl;
// #ifdef H5
if (/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(baseUrl)) baseUrl = "/commerce-api";
// #endif
export const commerce = createCommerceClient({
  baseUrl,
  authMode: usesAgentIdentity ? 'agent' : 'member',
  // #ifdef H5
  allowProxy: true,
  // #endif
  transport: native((options) => uni.request(options)),
  uploadTransport: native((options) => uni.uploadFile(options)),
  parent: { read: getSession, scope: storageContext, storageScope },
  storage: {
    get: (key) => uni.getStorageSync(key),
    set: (key, value) => { uni.setStorageSync(key, value); commerceSessionEpoch.value++; },
  },
  activateIdentity,
  deactivateIdentity: (session) => {
    if (usesCommerceIdentity && getSession()?.authSource === "commerce" && getSession()?.commerceMemberId === session?.userId) clearSession();
  },
  randomKey: () =>
    "mp-" +
    Date.now().toString(36) +
    "-" +
    Math.random().toString(36).slice(2) +
    "-" +
    Math.random().toString(36).slice(2),
  appId: (import.meta.env || {}).VITE_WECHAT_APPID || "",
  getWechatCode: isWechat
    ? async () => {
        const r = await native((options) => uni.login(options))({ provider: "weixin", timeout: 10000 });
        if (!r.code) throw new Error("微信未返回登录凭证，请重试");
        return r.code;
      }
    : null,
  pay: isWechat ? native((options) => uni.requestPayment(options)) : null,
});

export const commerceContext = () => storageContext() + ":commerce:" + commerce.sessionRevision();
