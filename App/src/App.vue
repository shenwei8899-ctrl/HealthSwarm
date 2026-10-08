<script>
export default {
  onLaunch() {
    uni.setStorageSync('active-health-case-v1', null)
    console.info('家庭营养师原型已启动')
  },
}
</script>

<style>
@import './styles/theme.css';
</style>
