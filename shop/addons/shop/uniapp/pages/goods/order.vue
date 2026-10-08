<template>
	<view class="u-skeleton">
		<!-- 顶部导航 -->
		<fa-navbar title="提交订单" :border-bottom="false"></fa-navbar>
		<view class="bg-white u-flex u-row-between u-p-30 u-m-b-20" @click="goPage('/pages/address/address?type=select')">
			<view class="u-skeleton-rect">
				<view class="text-weight">
					<text>{{ vuex_address.receiver || '请选择地址' }}</text>
					<text class="u-m-l-20">{{ vuex_address.mobile || '' }}</text>
				</view>
				<view class="u-tips-color u-p-t-10">{{ vuex_address.address || '' }}</view>
			</view>
			<view class="u-tips-color u-m-l-30"><u-icon name="arrow-right"></u-icon></view>
		</view>
		<view class="order-list u-skeleton-rect">
			<view class="item u-p-30 u-flex" v-for="(item, index) in list" :key="index">
				<image :src="(item.sku && item.sku.image) || item.goods.image" mode="aspectFill"></image>
				<view class="u-flex-1 right">
					<view class="u-line-2">{{ item.goods.title }}</view>
					<view class="u-line-1 title-sku u-font-24 u-tips-color u-m-t-5" v-if="item.sku">{{ item.sku_attr }}</view>
					<view class="u-flex u-row-between u-m-t-5">
						<text class="price u-font-30">{{ (item.sku && item.sku.price) || item.goods.price }}</text>
						<text class="u-tips-color">×{{ item.nums }}</text>
					</view>
				</view>
			</view>
		</view>
		<view class="notes u-skeleton-rect">
			<u-form ref="uForm" label-width="150">
				<u-form-item label="备注"><u-input v-model="memo" /></u-form-item>
				<u-form-item label="商品金额">
					<view class="price">
						￥
						<text v-text="order_info.goodsprice"></text>
					</view>
				</u-form-item>
				<u-form-item label="运费">
					<view class="price">
						￥
						<text v-text="order_info.shippingfee"></text>
					</view>
				</u-form-item>
				<u-form-item label-width="120" label="优惠券">
					<view class="coupon u-tips-color u-text-right price" @click="showCouponList" v-if="couponList.length">
						{{ coupon.user_coupon_id ? coupon.name + ' (-￥' + order_info.discount + ')' : '请选择优惠券' }}
					</view>
					<view class="coupon u-tips-color u-text-right" v-else>
						暂无可用优惠券
					</view>
				</u-form-item>
			</u-form>
		</view>
		<u-gap height="150" bg-color="#fffff"></u-gap>
		<!-- 底部导航条 -->
		<view class="footer-bar u-flex u-row-between">
			<view class="u-tips-color u-flex-1 u-skeleton-rect">
				<text>共</text>
				<text class="u-m-l-5 u-m-r-5">{{ totalNums }}</text>
				<text>件</text>
			</view>
			<view class="u-text-right u-font-30 u-flex-1 u-skeleton-rect">
				<text class="u-m-r-5">合计</text>
				<text class="price">￥{{ order_info.saleamount }}</text>
			</view>
			<view class="u-m-l-20">
				<u-button size="medium" hover-class="none" type="primary" :custom-style="{ width: '220rpx', backgroundColor: theme.bgColor, color: theme.color }" shape="circle" @click="add">
					提交订单
				</u-button>
			</view>
		</view>
		<fa-coupon v-model="show_coupon" :couponList="couponList" :mode="1" :totalPrice="totalPrice" @success="couponSuccess"></fa-coupon>
		<u-skeleton :loading="loading" :animation="true" bgColor="#FFF"></u-skeleton>
		<!-- 底部导航 -->
		<fa-tabbar></fa-tabbar>
	</view>
</template>

<script>
	export default {
		onLoad(e) {
			this.cart_ids = e.id;
			this.getDefAddress();
		},
		computed: {
			addressChange() {
				return this.vuex_address;
			},
			totalNums() {
				return this.list.reduce(function(total, item) {
					return total + parseInt(item.nums);
				}, 0);
			},
			totalPrice() {
				return this.couponTotalPrice;
			},
			saleAmount() {
				if (!this.totalPrice) {
					return 0;
				}
				return (Math.max(0, parseFloat(this.totalPrice) + parseFloat(this.order_info.shippingfee))).toFixed(2);
			}
		},
		watch: {
			addressChange(val, oldVal) {
				this.reCalculate();
			}
		},
		data() {
			return {
				cart_ids: '',
				list: [],
				order_info: {},
				memo: '',
				loading: true,
				show_coupon: false,
				couponList: [],
				couponTotalPrice: 0,
				coupon: {}
			};
		},
		methods: {
			getDefAddress() {
				this.$api.defAddress().then(res => {
					if (res.code) {
						this.$u.vuex('vuex_address', res.data);
					} else {
						this.$u.vuex('vuex_address', {});
					}
				});
			},
			reCalculate() {
				this.$api
					.orderCarts({
						ids: this.cart_ids,
						address_id: this.vuex_address.id,
						user_coupon_id: this.coupon.user_coupon_id,
					})
					.then(res => {
						if (res.code) {
							res.data.goods_list.map(item => {
								item.checked = false;
								item.cart_nums = item.nums;
							});
							this.list = res.data.goods_list;
							this.order_info = res.data.order_info;
							this.couponList = res.data.coupons;
							this.couponTotalPrice = res.data.couponTotalPrice;
							this.loading = false;
						}
					});
			},
			showCouponList() {
				if (!this.vuex_address.id) {
					this.$u.toast('请选择地址后再选择优惠券');
					return;
				}
				this.show_coupon = true;
			},
			couponSuccess(e) {
				console.log(e)
				this.coupon = e;
				this.reCalculate();
			},
			add() {
				if (!this.vuex_address.id) {
					this.$u.toast('请选择地址');
					return;
				}
				this.$api
					.orderAdd({
						ids: this.cart_ids,
						memo: this.memo,
						address_id: this.vuex_address.id,
						user_coupon_id: this.coupon.user_coupon_id || ''
					})
					.then(res => {
						console.log(res.code);
						if (res.code) {
							if (res.data.paystate) {
								this.goPage('/pages/order/detail?order_sn=' + res.data.order_sn);
							} else {
								this.goPage('/pages/order/payment?index=3&order_sn=' + res.data.order_sn);
							}
						} else {
							this.$u.toast(res.msg);
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
	.order-list {
		background-color: #ffffff;

		.item {
			border-bottom: 1px solid #f4f6f8;

			image {
				width: 200rpx;
				height: 150rpx;
				border-radius: 5rpx;
			}

			.right {
				padding-left: 20rpx;
				height: 150rpx;
				display: flex;
				flex-direction: column;
				justify-content: space-between;

				.title-sku {
					width: 450rpx;
				}
			}
		}
	}

	.notes {
		margin-top: 30rpx;
		padding: 0 30rpx;
		background-color: #ffffff;

		.price {
			width: 100%;
			text-align: right;
		}

		.coupon {
			width: 100%;
		}
	}
</style>