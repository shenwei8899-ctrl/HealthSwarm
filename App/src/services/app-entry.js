import { createEntryResolver } from './entry-routing.js'
import { wechatAuth } from './wechat-auth.js'
import { loadCloudProfile } from './cloud-profile.js'
import { getSession } from './session.js'
export const resolveAppEntry = createEntryResolver({ auth: wechatAuth, readProfile: loadCloudProfile, session: getSession })
