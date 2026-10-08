<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar title="商品订单" :border-bottom="false"></fa-navbar>
		<view class="wrap" :style="[wrapHeight]">
			<view class="u-tabs-box">
				<u-tabs-swiper
					:activeColor="theme.bgColor"
					ref="tabs"
					:list="list"
					:current="current"
					@change="change"
					:is-scroll="false"
					swiperWidth="750"
				></u-tabs-swiper>
			</view>
			<swiper class="swiper-box" :current="swiperCurrent" @transition="transition" @animationfinish="animationfinish">
				<swiper-item class="swiper-item" v-for="(swiper, key) in list" :key="key">
					<scroll-view
						scroll-y
						style="height: 100%;width: 100%;"
						@scrolltolower="reachBottom"
						:refresher-triggered="triggered"
						:refresher-enabled="false"
						:refresher-threshold="100"
						@refresherrefresh="refresher"						
					>
						<view class="page-box" v-if="orderList[key].length > 0">
							<view class="order" :class="{ 'u-m-t-30': rid }" v-for="(res, rid) in orderList[key]" :key="rid">
								<view class="top u-border-bottom">
									<view class="left u-tips-color">
										<text>订单编号:</text>
										<view class="store">{{ res.order_sn }}</view>
									</view>
									<view class="right">{{ res.status_text }}</view>
								</view>
								<view class="item" v-for="(item, index) in res.order_goods" :key="index" @click="goPage('/pages/goods/detail?id=' + item.goods_id)">
									<view class="left"><image :src="item.image" mode="aspectFill"></image></view>
									<view class="content">
										<view class="title u-line-1" v-text="item.title"></view>
										<view class="type u-line-2" v-text="item.attrdata || ''"></view>
										<view class="u-flex">
											<!-- 申请售后：已发货,订单正常 -->
											<view class="" v-if="item.salestate == 2">
												<u-tag text="退款中" mode="plain" shape="circle" size="mini" type="warning" />
											</view>
											<view class="" v-if="item.salestate == 3">
												<u-tag text="退货中" mode="plain" shape="circle" size="mini" type="warning" />
											</view>
											<view class="" v-if="item.salestate == 4">
												<u-tag text="已退款" mode="plain" shape="circle" size="mini" type="success" />
											</view>
											<view class="" v-if="item.salestate == 5">
												<u-tag text="已退货退款" mode="plain" shape="circle" size="mini" type="success" />
											</view>
										</view>
									</view>
									<view class="right">
										<view class="price">
											￥{{ priceInt(item.price) }}
											<text class="decimal">.{{ priceDecimal(item.price) }}</text>
										</view>
										<view class="number">×{{ item.nums }}</view>
									</view>
								</view>
								<view class="u-tips-color u-p-t-20" v-if="res.delivery_time">配送时间:{{ res.delivery_time | date('yyyy-mm-dd hh:MM:ss') }}</view>
								<view class="total" @click="goPage('/pages/order/detail?order_sn=' + res.order_sn)">
									<text class="u-m-r-20">共{{ res.order_goods.length }}件商品</text>
									<text class="u-m-r-20">运费￥{{res.shippingfee}}</text>
									 合计:
									<text class="total-price">
										￥{{ priceInt(res.saleamount) }}.
										<text class="decimal">{{ priceDecimal(res.saleamount) }}</text>
									</text>
								</view>
								<view class="bottom" @click.self="goPage('/pages/order/detail?order_sn=' + res.order_sn)">
									<view class="exchange btn" @click.stop="goPage('/pages/order/detail?order_sn=' + res.order_sn)">查看详情</view>
									<!-- 取消订单：未支付，订单正常 -->
									<view class="exchange btn" v-if="!res.orderstate && !res.paystate" @click.stop="(show = true), (order_index = rid)">取消订单</view>
									<!-- 立即支付：未失效，未支付 -->
									<view
										class="logistics btn"
										@click.stop="goPage('/pages/order/payment?order_sn=' + res.order_sn)"
										:style="[{ backgroundColor: theme.bgColor, color: theme.color }]"
										v-if="!res.paystate && !res.orderstate"
									>
										立即支付
									</view>
									<!-- 查看物流：已发货,已收货,订单正常，订单完成 -->
									<view class="logistics btn" v-if="res.shippingstate && [0, 3,4].includes(res.orderstate)" @click.stop="logistics(res)">查看物流</view>
									<!-- 确认收货：已发货 ,订单正常-->
									<view class="shipped btn" v-if="res.shippingstate == 1 && !res.orderstate" @click.stop="shipped(rid)">确认收货</view>
									<!-- 立即评价：已收货，订单正常，已支付 -->
									<view
										class="evaluate btn"
										v-if="res.shippingstate == 2 && !res.orderstate && res.paystate == 1"
										@click.stop="goPage('/pages/remark/remark?order_sn=' + res.order_sn)"
									>
										立即评价
									</view>
								</view>
							</view>
							<view class="u-p-30"><u-loadmore :status="loadStatus[key]" bgColor="#f2f2f2"></u-loadmore></view>
						</view>
						<view class="page-box" v-else>
							<view v-if="loadStatus[key]!='loadmore'">
								<view class="centre">
									<image src="../../static/image/order.png" mode=""></image>
									<view class="explain">
										您还没有相关的订单
										<view class="tips">可以去看看有那些想买的</view>
									</view>
									<view class="btn">
										<u-button
											size="medium"
											:custom-style="{ width: '220rpx', backgroundColor: theme.bgColor, color: theme.color }"
											shape="circle"
											@click="goPage('/pages/goods/goods')"
										>
											随便逛逛~
										</u-button>
									</view>
								</view>
							</view>
							<view class="u-p-t-60 u-flex u-row-center" v-else>
								<u-loading mode="flower" size="72"></u-loading>
							</view>
						</view>
					</scroll-view>
				</swiper-item>
			</swiper>
		</view>
		<u-modal v-model="show" content="确认取消订单吗？" @confirm="cancel" :show-cancel-button="true"></u-modal>
		<!-- 底部导航 -->
		<fa-tabbar></fa-tabbar>
	</view>
</template>

<script>
// 获取系统状态栏的高度
let systemInfo = uni.getSystemInfoSync();
export default {
	data() {
		return {
			is_first: false,
			orderList: [[], [], [], [], [], []],
			list: [
				{
					name: '全部',
					status: {}
				},
				{
					name: '待付款',
					status: {
						orderstate: 0,
						paystate: 0
					}
				},
				{
					name: '待发货',
					status: {
						orderstate: 0,
						paystate: 1,
						shippingstate: 0
					}
				},
				{
					name: '待收货',
					status: {
						orderstate: 0,
						paystate: 1,
						shippingstate: 1
					}
				},
				{
					name: '待评价',
					status: {
						orderstate: 0,
						paystate: 1,
						shippingstate: 2
					}
				},
				{
					name: '已完成',
					status: {
						orderstate: 3,
						paystate: 1
					}
				}
			],
			current: 0,
			swiperCurrent: 0,
			dx: 0,
			order_index: 0,
			show: false,
			loadStatus: ['loadmore', 'loadmore', 'loadmore', 'loadmore', 'loadmore', 'loadmore'],
			page: [1, 1, 1, 1, 1, 1],			
			triggered: false,
			_freshing:false,			
		};
	},
	onLoad(e) {
		this.current = e.status ? parseInt(e.status) : 0;
		if (!this.current) {
			this.getOrderList(this.current);
		} else {
			this.swiperCurrent = this.current;
		}
	},
	onShow() {		
		if (this.is_first) {
			if(!this.vuex_token){
				uni.$u.route({
					type:'back'
				})
				return;
			}
			this.page[this.current] = 1;
			this.orderList[this.current] = [];
			this.getOrderList(this.current);
		}
		this.is_first = true;
	},
	computed: {
		// 转换字符数值为真正的数值
		navbarHeight() {
			// #ifdef H5
			return 44;
			// #endif
			// #ifdef APP-PLUS
			return 44 + systemInfo.statusBarHeight;
			// #endif
			// #ifdef MP
			// 小程序特别处理，让导航栏高度 = 胶囊高度 + 两倍胶囊顶部与状态栏底部的距离之差(相当于同时获得了导航栏底部与胶囊底部的距离)
			let height = systemInfo.platform == 'ios' ? 44 : 48;
			return height + systemInfo.statusBarHeight;
			// #endif
		},
		wrapHeight() {
			return {
				height: (uni.getSystemInfoSync().windowHeight - this.navbarHeight)+ 'px'
			};
		},
		// 价格小数
		priceDecimal() {
			return val => {
				if (val !== parseInt(val)) return val.slice(-2);
				else return '00';
			};
		},
		// 价格整数
		priceInt() {
			return val => {
				if (val !== parseInt(val)) return val.split('.')[0];
				else return val;
			};
		}
	},
	watch: {
		current(newValue, oldValue) {			
			this.getOrderList(newValue, 'init');
		}
	},
	methods: {
		getOrderList(current, type) {
			if (type == 'init' && this.orderList[current].length > 0) {				
				return;
			}
			this.$api
				.orderList({
					page: this.page[current],
					...this.list[current].status
				})
				.then(result => {
					const { code, data: res, msg } = result;
					if (code) {
						res.data.forEach(item => {
							this.orderList[current].push(item);
						});
						if (res.current_page < res.last_page) {
							this.loadStatus.splice(this.current, 1, 'loadmore');
						} else {
							this.loadStatus.splice(this.current, 1, 'nomore');
						}
					}					
					this.triggered = false;
					this._freshing = false;
				});
		},
		cancel() {
			this.$api.orderCancel({ order_sn: this.orderList[this.current][this.order_index].order_sn }).then(res => {
				this.$u.toast(res.msg);
				if (res.code) {
					this.orderList[this.current] = [];
					this.getOrderList(this.current);
				}
			});
		},
		shipped(index) {
			this.$api.takedelivery({ order_sn: this.orderList[this.current][index].order_sn }).then(res => {
				this.$u.toast(res.msg);
				if (res.code) {
					this.orderList[this.current] = [];
					this.getOrderList(this.current);
				}
			});
		},	
		reachBottom() {
			// 此tab为空数据
			if (this.loadStatus[this.current] == 'loadmore') {
				this.page[this.current] = this.page[this.current] + 1;
				this.loadStatus.splice(this.current, 1, 'loading');
				this.getOrderList(this.current);
			}
		},
		// tab栏切换
		change(index) {
			this.swiperCurrent = index;
		},
		transition({ detail: { dx } }) {
			if(this.$refs.tabs.tabsInfo.length > 0){
				this.$refs.tabs.setDx(dx);
			}
		},
		animationfinish({ detail: { current } }) {
			this.$refs.tabs.setFinishCurrent(current);
			this.swiperCurrent = current;
			this.current = current;
		},		
		refresher() {
			if (this._freshing) return;
			this._freshing = true;
			//界面下拉触发，triggered可能不是true，要设为true ，否则无法重置
			if (!this.triggered){
				this.triggered = true;
			}
			this.page[this.current] = 1;
			this.orderList[this.current] = [];
			this.getOrderList(this.current);
		}		
	}
};
</script>

<style>
/* #ifndef H5 */
page {
	height: 100%;
	background-color: #f2f2f2;
}
/* #endif */
</style>

<style lang="scss" scoped>
.page-box {
	padding-top: 30rpx;
	display: flex;
	align-items: center;
	flex-direction: column;
}
.order {
	width: 710rpx;
	background-color: #ffffff;
	border-radius: 20rpx;
	box-sizing: border-box;
	padding: 30rpx;
	font-size: 28rpx;
	.top {
		padding-bottom: 20rpx;
		margin-bottom: 10rpx;
		display: flex;
		justify-content: space-between;
		.left {
			display: flex;
			align-items: center;
			font-size: 25rpx;
			.store {
				margin: 0 10rpx;
			}
		}
		.right {
			color: $u-type-warning-dark;
		}
	}
	.item {
		display: flex;
		padding: 20rpx 0;
		border-bottom: 1px solid #f4f6f8;
		justify-content: space-between;
		.left {
			margin-right: 20rpx;
			image {
				width: 200rpx;
				height: 150rpx;
				border-radius: 10rpx;
			}
		}
		.content {
			flex: 1;
			.title {
				font-size: 28rpx;
				line-height: 40rpx;
				width: 320rpx;
			}
			.type {
				margin: 10rpx 0;
				font-size: 24rpx;
				color: $u-tips-color;
			}
		}
		.right {
			margin-left: 10rpx;
			padding-top: 20rpx;
			text-align: right;
			.decimal {
				font-size: 24rpx;
				margin-top: 4rpx;
			}
			.number {
				color: $u-tips-color;
				font-size: 24rpx;
			}
		}
	}
	.total {
		margin-top: 20rpx;
		text-align: right;
		font-size: 24rpx;
		.total-price {
			font-size: 32rpx;
		}
	}
	.btn {
		line-height: 52rpx;
		width: 160rpx;
		border-radius: 26rpx;
		border: 2rpx solid $u-border-color;
		font-size: 26rpx;
		text-align: center;
		color: $u-type-info-dark;
		margin-left: 15rpx;
	}
	.shipped {
		color: $u-type-success;
		border-color: $u-type-success;
	}	
	.evaluate {
		color: $u-type-warning-dark;
		border-color: $u-type-warning-dark;
	}
	.bottom {
		display: flex;
		margin-top: 40rpx;
		padding: 0 10rpx;
		justify-content: flex-end;
		align-items: center;
	}
}
.centre {
	text-align: center;
	padding: 200rpx 0;
	font-size: 32rpx;
	image {
		width: 400rpx;
		height: 400rpx;
		margin-bottom: 20rpx;
	}
	.tips {
		font-size: 24rpx;
		color: #999999;
		margin-top: 20rpx;
	}
	.btn {
		margin: 80rpx auto;
		width: 200rpx;
		border-radius: 32rpx;
		line-height: 64rpx;
		color: #ffffff;
		font-size: 26rpx;
	}
}
.wrap {
	display: flex;
	flex-direction: column;
	width: 100%;
}
.swiper-box {
	flex: 1;
}
.swiper-item {
	height: 100%;
}
</style>
