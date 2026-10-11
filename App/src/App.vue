<script>
import { scopedStorage } from './services/storage.js'
import { canOpenPage } from './services/navigation.js'
export default {
  onLaunch(options) {
    if (options?.path && !canOpenPage(options.path)) uni.reLaunch({url:'/pages/index/index'})
    scopedStorage.setStorageSync('active-health-case-v1', null)
    console.info('家庭营养师原型已启动')
  },
}
</script>

<style>
@import './styles/theme.css';
</style>
