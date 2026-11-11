import { scopedStorage } from './storage.js'
import { createEntryResolver, createEntryCoordinator } from './entry-routing.js'
import { wechatAuth } from './wechat-auth.js'
import { loadCloudProfile } from './cloud-profile.js'
import { getSession } from './session.js'
import { pendingInvitation, invitationRoute } from './family-invitations.js'
const preparationPending = () => !!(scopedStorage.getStorageSync('onboarding-preparation-pending')||scopedStorage.getStorageSync('onboarding-preparation-active'))
const resolve = createEntryResolver({ auth: wechatAuth, readProfile: () => loadCloudProfile({openConsultation:false,readConfiguration:false}), pendingPreparation: preparationPending,
  session: getSession, invitation: pendingInvitation, invitationRoute })
export const resolveAppEntry = createEntryCoordinator({ resolve, session: getSession,
  invitation: pendingInvitation,
  pendingPreparation: preparationPending,
  profileState: () => {
    const profile = scopedStorage.getStorageSync('family-profile-v2')
    return profile ? [profile.source, profile.householdId, profile.completeProfile === true, profile.onboarded === true, profile.invitationReviewPending === true] : null
  },
})

export function rememberChatEntry(profile) {
  const session=getSession()
  if (!session?.token || !session.householdId || session.householdId!==profile?.householdId ||
      !(profile.completeProfile || profile.onboarded) || profile.invitationReviewPending || pendingInvitation() ||
      preparationPending()) return
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
  if (family.invitationReviewPending) return '/pages/onboarding/index'
  if (preparationPending()) return '/pages/onboarding/preparing'
  if (family.onboardingRequired === false) return '/pages/chat/index'
  return null
}
