<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar title="详情" :border-bottom="false"></fa-navbar>
		<view class="coupon-detail" v-if="info.id">
			<view class="bg-white u-flex u-row-between u-col-center">
				<view class="left">
					<view class="u-p-30">
						<view class="u-flex">
							<view class="">
								{{ info.result == 1 ? '￥' : '打' }}
								<text :style="[{ fontSize: '70rpx', fontWeight: 'bold', color: theme.bgColor }]">
									{{ info.result_data && info.result_data.number }}
								</text>
								{{ info.result == 1 ? '元' : '折' }}
							</view>
							<view class="u-m-l-30">
								<view class="u-font-40">优惠券</view>
								<view class="u-font-26">COUPON</view>
							</view>
						</view>
						<view class="u-m-t-30">
							<view class="u-border u-p-10 u-font-24" v-if="info.result == 0">
								订单满
								<text class="text-weight u-m-l-5 u-m-r-5">{{ info.result_data.money }}</text>
								打
								<text class="text-weight u-m-l-5 u-m-r-5">{{ info.result_data.number }}</text>
								折
							</view>
							<view class="u-border u-p-10 u-font-24" v-else>
								订单满
								<text class="text-weight u-m-l-5 u-m-r-5">{{ info.result_data.money }}</text>
								减
								<text class="text-weight u-m-l-5 u-m-r-5">{{ info.result_data.number }}</text>
								元
							</view>
						</view>
					</view>
				</view>
				<view class="receive">
					<block v-if="info.is_received"><u-button size="mini" :disabled="true" hover-class="none">已领取</u-button></block>
					<block v-else-if="info.received_num >= info.give_num"><u-button size="mini" :disabled="true" hover-class="none">已被领完</u-button></block>
					<block v-else-if="info.expired && !info.is_received"><u-button size="mini" :disabled="true" hover-class="none">已过期</u-button></block>
					<block v-else-if="!info.online"><u-button size="mini" hover-class="none">未可领取</u-button></block>
					<block v-else>
						<u-button size="mini" type="primary" :custom-style="{ backgroundColor: theme.bgColor, color: theme.color }" hover-class="none" @click="give">
							立即领取
						</u-button>
					</block>
				</view>
			</view>
			<view class="bg-white u-p-30 u-m-t-30">
				<view class="text-weight">温馨提示：</view>
				<view class="u-m-t-10">
					<text class="u-m-r-10">•</text>
					每人限领{{ info.allow_num }}张
				</view>
				<view class="u-m-t-10">
					<text class="u-m-r-10">•</text>
					仅限量{{ info.give_num }}张，赶快领取！
				</view>
				<view class="u-m-t-10" v-if="info.mode == 'fixation'">
					<text class="u-m-r-10">•</text>
					领取后{{ info.use_times }}天内有效
				</view>
				<view class="u-m-t-10" v-else>
					<text class="u-m-r-10">•</text>
					领取后{{ info.use_times | formatreceive }}
				</view>
			</view>
			<view class="u-m-t-30">
				<view class="bg-white title">
					<text class="stroke"></text>
					<view>可使用商品</view>
				</view>
				<view class="goods-list">
					<view
						class="item u-flex u-row-between u-col-center"
						v-for="(item, index) in info.goods"
						:key="index"
						@click="goPage('/pages/goods/detail?id=' + item.id)"
					>
						<view class="images"><image :src="item.image" mode="aspectFill"></image></view>
						<view class="right">
							<view class="u-p-15 name">
								<text class="u-line-2">{{ item.title }}</text>
							</view>
							<view class="u-p-l-15 u-p-r-15 u-flex u-row-between u-tips-color">
								<view class="">
									<text class="u-m-r-5">销量</text>
									<text>{{ item.sales }}</text>
								</view>
								<view class="">
									<text class="u-m-r-5">浏览</text>
									<text>{{ item.views || 0 }}</text>
								</view>
							</view>
							<view class="u-flex u-row-between u-p-15">
								<view class="price">
									<text>￥{{ item.price }}</text>
								</view>
								<text class="market_price u-tips-color">￥{{ item.marketprice }}</text>
							</view>
						</view>
						<!--  -->
					</view>
					<!-- 空数据 -->
					<view class="u-flex u-row-center fa-empty" v-if="!info.goods.length">
						<image src="../../static/image/data.png" mode=""></image>
						<view class="u-tips-color">暂无更多的商品数据~</view>
					</view>
				</view>
			</view>
		</view>
		<!-- 预订日历 -->
		<view class="" v-if="is_show">
			<fa-calendar
				v-model="value"
				:price="goods_info.price"
				:calendar="goods_info.calendar"
				:orderCalendar="goods_info.order_calendar"
				@confirm="calendarConfirm"
			></fa-calendar>
		</view>
	</view>
</template>

<script>
export default {
	onLoad(e) {
		this.id = e.id || '';
		this.getCouponDetail();
	},
	data() {
		return {
			id: '',
			info: {},
			goods_info: {},
			is_show: false,
			value: false
		};
	},
	methods: {
		getCouponDetail() {
			this.$api.couponDetail({ id: this.id }).then(res => {
				if (res.code == 1) {
					this.info = res.data;
				} else {
					this.$u.toast(res.msg);
				}
			});
		},
		clickSwiper(index, item) {
			console.log(index, item);
			this.goPage('/pages/hotel/detail?id=' + item.id);
		},
		collect(id, index, status) {
			this.$api.optionCollect({ goods_id: id, type: 0 }).then(res => {
				if (res.code) {
					if (status) {
						this.$u.toast('取消收藏成功');
						this.$set(this.info.goods[index], 'isCollect', 0);
					} else {
						this.$u.toast('添加收藏成功');
						this.$set(this.info.goods[index], 'isCollect', 1);
					}
				} else {
					this.$u.toast(res.msg);
				}
			});
		},
		toBooking(id) {
			this.$api.houseDetail({ id: id }).then(res => {
				if (res.code == 1) {
					this.goods_info = res.data;
					this.is_show = true;
					setTimeout(() => {
						this.value = true;
					}, 100);
				} else {
					this.$u.toast(res.msg);
				}
			});
		},
		calendarConfirm(e, dom) {
			if (JSON.stringify(e) == '{}') {
				this.$u.toast('请选择入住和离店日期');
				return;
			}
			if (!dom) {
				return;
			}
			this.goPage('/pages/hotel/booking?id=' + this.goods_info.id + '&start_time=' + e.start + '&end_time=' + e.end);
		},
		give() {
			this.$api.drawCoupon({ id: this.info.id }).then(res => {
				this.$u.toast(res.msg);
				if (res.code == 1) {
					this.is_update = true;
					this.getCouponDetail();
				}
			});
		}
	}
};
</script>

<style lang="scss">
page {
	background-color: #f4f6f8;
}
</style>

<style lang="scss" scoped>
.coupon-detail {
	padding: 30rpx;
	.left {
		flex: 1;
		margin-right: 30rpx;
		border-right: 1px dashed #ddd;
		position: relative;
		&::before {
			content: '';
			display: block;
			width: 30rpx;
			height: 30rpx;
			position: absolute;
			right: -15rpx;
			top: -15rpx;
			background-color: #f4f6f8;
			border-radius: 100rpx;
		}
		&::after {
			content: '';
			display: block;
			width: 30rpx;
			height: 30rpx;
			position: absolute;
			right: -15rpx;
			bottom: -15rpx;
			background-color: #f4f6f8;
			border-radius: 100rpx;
		}
	}
	.receive {
		width: 170rpx;
	}
	.number {
		font-size: 50rpx;
		font-weight: bold;
	}
	.goods-list {
		border-top: 1px solid #f4f6f8;
		.item {
			background-color: #ffffff;
			padding: 30rpx;
			border-bottom: 1px solid #f4f6f8;
			.images {
				width: 220rpx;
				height: 200rpx;
				image {
					border-radius: 10rpx;
					width: 100%;
					height: 100%;
				}
			}
			.right {
				flex: 1;
			}
			.market_price {
				text-decoration: line-through;
				margin-left: 10rpx;
			}
		}
	}
	.title {
		position: relative;
		padding: 30rpx 30rpx 30rpx 35rpx;
		.stroke {
			&::before {
				content: '';
				width: 8rpx;
				height: 30rpx;
				background-color: #374486;
				position: absolute;
				top: 35%;
				left: 20rpx;
				border-radius: 20rpx;
			}
		}
	}
}
</style>
