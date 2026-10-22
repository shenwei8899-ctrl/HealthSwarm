<script>
import { scopedStorage } from './services/storage.js'
import { checkCurrentEntry } from './services/navigation.js'
import { captureInvitation } from './services/family-invitations.js'
import { isMockMode } from './services/config.js'
export default {
  onLaunch(options) {
    captureInvitation(options)
    if (!isMockMode && options?.path && options.path !== 'pages/index/index') uni.reLaunch({url:'/pages/index/index'})
    scopedStorage.setStorageSync('active-health-case-v1', null)

  },
  onShow(options) { void checkCurrentEntry(options) },
}
</script>

<style>
@import './styles/theme.css';
</style>
