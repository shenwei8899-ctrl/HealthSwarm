import { scopedStorage } from './storage.js'
import { createEntryResolver, createEntryCoordinator } from './entry-routing.js'
import { wechatAuth } from './wechat-auth.js'
import { loadCloudProfile } from './cloud-profile.js'
import { getSession } from './session.js'
import { pendingInvitation, invitationRoute } from './family-invitations.js'
const resolve = createEntryResolver({ auth: wechatAuth, readProfile: () => loadCloudProfile({openConsultation:false,readConfiguration:false}), pendingPreparation: () => !!scopedStorage.getStorageSync('onboarding-preparation-pending'),
  session: getSession, invitation: pendingInvitation, invitationRoute })
export const resolveAppEntry = createEntryCoordinator({ resolve, session: getSession,
  invitation: pendingInvitation,
  pendingPreparation: () => !!scopedStorage.getStorageSync('onboarding-preparation-pending'),
  profileState: () => {
    const profile = scopedStorage.getStorageSync('family-profile-v2')
    return profile ? [profile.source, profile.householdId, profile.completeProfile === true, profile.onboarded === true] : null
  },
})

export function rememberChatEntry(profile) {
  const session=getSession()
  if (!session?.token || !session.householdId || session.householdId!==profile?.householdId ||
      !(profile.completeProfile || profile.onboarded) || pendingInvitation() ||
      scopedStorage.getStorageSync('onboarding-preparation-pending')) return
  resolveAppEntry.remember('/pages/chat/index')
}

// This is only permission to render a page shell. Its data still comes from
// authenticated APIs, and the entry is revalidated after native navigation.
export function immediateShellEntry() {
  const account = getSession()
  if (!account?.token || account.isDemo || !account.accountId || !account.householdId ||
      !Number.isFinite(account.expiresAt) || account.expiresAt * 1000 <= Date.now()) return null
  const family = account.families?.find(item => item.id === account.householdId)
  if (!family) return null
  const invitation = pendingInvitation()
  if (invitation) return invitationRoute(invitation)
  if (scopedStorage.getStorageSync('onboarding-preparation-pending')) return '/pages/onboarding/preparing'
  if (family.onboardingRequired === false) return '/pages/chat/index'
  return null
}
