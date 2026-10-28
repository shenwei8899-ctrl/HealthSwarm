import { scopedStorage } from './storage.js'
import { createEntryResolver, createEntryCoordinator } from './entry-routing.js'
import { wechatAuth } from './wechat-auth.js'
import { loadCloudProfile } from './cloud-profile.js'
import { getSession } from './session.js'
import { pendingInvitation, invitationRoute } from './family-invitations.js'
const resolve = createEntryResolver({ auth: wechatAuth, readProfile: () => loadCloudProfile({openConsultation:false}), pendingPreparation: () => !!scopedStorage.getStorageSync('onboarding-preparation-pending'),
  session: getSession, invitation: pendingInvitation, invitationRoute })
export const resolveAppEntry = createEntryCoordinator({ resolve, session: getSession,
  invitation: pendingInvitation,
  pendingPreparation: () => !!scopedStorage.getStorageSync('onboarding-preparation-pending'),
  profileState: () => {
    const profile = scopedStorage.getStorageSync('family-profile-v2')
    return profile ? [profile.source, profile.householdId, profile.completeProfile === true, profile.onboarded === true] : null
  },
})
