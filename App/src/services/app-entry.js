import { scopedStorage, storageContext } from './storage.js'
import { createEntryResolver } from './entry-routing.js'
import { wechatAuth } from './wechat-auth.js'
import { loadCloudProfile } from './cloud-profile.js'
import { getSession } from './session.js'
import { pendingInvitation, invitationRoute } from './family-invitations.js'
const resolve = createEntryResolver({ auth: wechatAuth, readProfile: () => loadCloudProfile({openConsultation:false,readConfiguration:false}), pendingPreparation: () => !!scopedStorage.getStorageSync('onboarding-preparation-pending'),
  session: getSession, invitation: pendingInvitation, invitationRoute })
let pending = null, cached = null
const lifetime = 60000
function context() {
  return JSON.stringify([storageContext(), pendingInvitation(), !!scopedStorage.getStorageSync('onboarding-preparation-pending')])
}
export function rememberChatEntry(profile) {
  const session=getSession()
  if (!session?.token || !session.householdId || session.householdId!==profile?.householdId ||
      !(profile.completeProfile || profile.onboarded) || pendingInvitation() ||
      scopedStorage.getStorageSync('onboarding-preparation-pending')) return
  cached={key:context(),entry:'/pages/chat/index',time:Date.now()}
}
export function resolveAppEntry({force=false} = {}) {
  const key=context()
  if (force) cached=null
  if (!force && cached?.key===key && Date.now()-cached.time>=0 && Date.now()-cached.time<lifetime) return Promise.resolve(cached.entry)
  if (pending?.key===key) return pending.promise
  const flight={key}
  flight.promise=resolve().then(entry=>{
    if (entry.split('?')[0]==='/pages/chat/index' && context()===key) cached={key,entry,time:Date.now()}
    return entry
  }).finally(()=>{if(pending===flight)pending=null})
  pending=flight
  return flight.promise
}
