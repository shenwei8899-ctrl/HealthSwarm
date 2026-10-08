<script setup>
import {onLoad} from '@dcloudio/uni-app'
onLoad(o=>uni.redirectTo({url:'/pages/shop/index?meal='+(o.meal||'dinner')}))
</script><template><view class="screen"><text>正在打开本餐安排与购买清单…</text></view></template>
