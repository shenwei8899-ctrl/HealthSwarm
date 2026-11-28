<script>
import { scopedStorage } from './services/storage.js'
import { checkCurrentEntry } from './services/navigation.js'
import { captureInvitation } from './services/family-invitations.js'
import { referralEntry } from './services/referral-entry.js'
export default {
  onLaunch(options) {
    captureInvitation(options)
    void referralEntry.capture(options)
    scopedStorage.setStorageSync('active-health-case-v1', null)
  },
  onShow(options) { void referralEntry.capture(options); void checkCurrentEntry(options) },
}
</script>

<style>
@import './styles/theme.css';
</style>
