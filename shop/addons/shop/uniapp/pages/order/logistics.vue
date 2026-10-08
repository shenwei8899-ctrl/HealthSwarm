<template>
	<view>
		<view class="" v-if="vuex_config.logisticstype=='kd100'"><web-view :webview-styles="webviewStyles" :src="url"></web-view></view>
		<view class="u-p-30" v-else>
			<u-time-line>
				<u-time-line-item nodeTop="2" v-for="(item, index) in list" :key="index">					
					<template v-slot:content>
						<view>
							<view class="u-order-title">{{ item.Remark }}</view>
							<view class="u-order-desc">{{ item.AcceptStation }}</view>
							<view class="u-order-time">{{ item.AcceptTime }}</view>
						</view>
					</template>
				</u-time-line-item>
			</u-time-line>
			<view class="u-flex u-row-center fa-empty top-15" v-if="!list.length">
				<image src="../../static/image/data.png" mode=""></image>
				<view class="u-tips-color">暂无更多的物流信息~</view>
			</view>
		</view>
	</view>
</template>

<script>
export default {
	onLoad(e) {
		this.order_sn = e.order_sn || '';
		if (this.vuex_config.logisticstype=='kd100') {
			this.url = `https://m.kuaidi100.com/app/query/?coname=${e.coname || ''}&nu=${e.nu}&com=${e.com || ''}`;
		} else {
			uni.setNavigationBarTitle({
				title: '物流信息'
			});
			this.getLogistics();
		}
	},
	onReady() {
		uni.setNavigationBarColor({
			frontColor: this.theme.color,
			backgroundColor: this.theme.bgColor,
			animation: {
				duration: 400,
				timingFunc: 'easeIn'
			}
		});
	},
	data() {
		return {			
			url: '',
			webviewStyles: {},
			order_sn: '',
			list: []
		};
	},
	methods: {
		getLogistics() {
			this.$api.logistics({ order_sn: this.order_sn }).then(({ code, data, msg }) => {
				if (code) {
					this.list = data;
				}else{
					this.$u.toast(msg);
					setTimeout(()=>{
						uni.$u.route({
							type:'back'
						})
					},1500)
				}
			});
		}
	}
};
</script>

<style lang="scss" scoped>
.u-order-title {
	color: #333333;
	font-weight: bold;
	font-size: 30rpx;
}

.u-order-desc {
	color: rgb(140, 140, 140);
	font-size: 28rpx;
	margin: 6rpx 0;
}

.u-order-time {
	color: rgb(165, 165, 165);
	font-size: 26rpx;
}
</style>
