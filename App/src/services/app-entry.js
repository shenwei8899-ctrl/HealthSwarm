import { createEntryResolver } from './entry-routing.js'
import { wechatAuth } from './wechat-auth.js'
import { loadCloudProfile } from './cloud-profile.js'
import { getSession } from './session.js'
import { pendingInvitation, invitationRoute } from './family-invitations.js'
const resolve = createEntryResolver({ auth: wechatAuth, readProfile: loadCloudProfile,
  session: getSession, invitation: pendingInvitation, invitationRoute })
let pending = null
export function resolveAppEntry() {
  if (!pending) pending = resolve().finally(() => { pending = null })
  return pending
}
