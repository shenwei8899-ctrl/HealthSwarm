<template>
	<view class="u-skeleton">
		<!-- 顶部导航 -->
		<fa-navbar title="订单支付" :border-bottom="false" :backIndex="backIndex"></fa-navbar>
		<view class="u-p-30 bg-white u-m-b-30 u-flex u-row-center">
			<view class="u-m-r-10">
				<u-icon name="clock" size="32" :color="theme.bgColor"></u-icon>
			</view>
			<u-count-down :timestamp="order.expiretime" :color="theme.bgColor" separator-color="#616162" font-size="26" :showDays="false" separator="zh"></u-count-down>
			<text class="u-font-30">后失效</text>
		</view>
		<view class="list">
			<view class="u-tips-color u-font-28 u-p-30 u-border-bottom">订单编号 : {{ order.order_sn }}</view>
			<view class="item u-p-30 u-flex u-col-center" v-for="(item, index) in order.order_goods" :key="index">
				<image :src="item.image" mode="aspectFill"></image>
				<view class="u-flex-1 right">
					<view class="u-line-2">{{ item.title || '' }}</view>
					<view class="u-tips-color u-font-24 u-line-1 attrs">{{ item.attrdata || '' }}</view>
					<view class="u-flex u-row-between u-m-t-10">
						<text class="price u-font-30">{{ item.price }}</text>
						<text class="u-tips-color">×{{ item.nums }}</text>
					</view>
				</view>
			</view>
		</view>
		<view class="u-p-30 bg-white u-text-right u-border-top">
			<text class="u-m-r-20 u-tips-color">运费￥{{ order.shippingfee }}</text>
			<text class="u-m-r-20 u-tips-color">优惠￥{{ order.discount }}</text>
			合计
			<text class="price">￥{{ order.saleamount }}</text>
		</view>

		<view class="bg-white u-m-t-30" :data-init="_paytype_">
			<u-cell-group title="支付方式">
				<u-radio-group v-model="paytype" @change="radioGroupChange">
					<view class="paytype">
						<u-cell-item :icon-style="{ color: '#20D029' }" @click="paytype = 'wechat'" :arrow="false" icon="weixin-circle-fill" title="微信支付" hover-class="cell-hover-class">
							<u-radio slot="right-icon" name="wechat" :active-color="theme.bgColor"></u-radio>
						</u-cell-item>

						<!-- #ifndef MP-WEIXIN -->
						<u-cell-item :icon-style="{ color: '#00A1E9' }" v-if="!$util.isWeiXinBrowser()" @click="paytype = 'alipay'" :arrow="false" icon="zhifubao-circle-fill" title="支付宝支付" hover-class="cell-hover-class">
							<u-radio slot="right-icon" name="alipay" :active-color="theme.bgColor"></u-radio>
						</u-cell-item>
						<!-- #endif -->
					</view>
				</u-radio-group>
			</u-cell-group>
		</view>
		<u-gap height="180" bg-color="#f4f6f9"></u-gap>
		<view class="payment bg-white">
			<u-button type="primary" hover-class="none" :custom-style="{ backgroundColor: theme.bgColor, color: theme.color }" shape="circle" @click="submit">
				立即支付
			</u-button>
		</view>
		<u-skeleton :loading="loading" :animation="true" bgColor="#FFF"></u-skeleton>
	</view>
</template>

<script>
	import { loginfunc } from '@/common/fa.mixin.js';
	export default {
		mixins: [loginfunc],
		onLoad(e) {
			this.backIndex = parseInt(e.index) || 1;
			this.order_sn = e.order_sn || '';
			this.from = e.from || '';

			this.getOrder();
		},
		computed: {
			_paytype_() {
				// #ifdef H5
				if (!this._first) {
					this.paytype = this.vuex_config.defaultpaytype;
					if (this.paytype) {
						this._first = true;
					}
				}
				// #endif
				return this.paytype;
			}
		},
		data() {
			return {
				_first: false,
				backIndex: 1,
				paytype: 'wechat',
				order_sn: '',
				from: '',
				order: {},
				loading: true // 是否显示骨架屏组件
			};
		},
		methods: {
			radioGroupChange(e) {
				this.paytype = e;
			},
			getOrder() {
				this.$api
					.orderDetail({
						order_sn: this.order_sn
					})
					.then(res => {
						if (res.code) {
							this.loading = false;
							this.order = res.data;
							
							if (res.data.paystate > 0) {
								this.$u.toast('支付成功！');
								setTimeout(() => {
									this.$u.route('/pages/order/list');
								}, 1000);
								return;
							}
							
							// #ifdef H5
							//判断如果从获取openid页面返回则直接提交
							if (this.vuex_openid && this.from == 'openid') {
								this.submit();
								return;
							}
							// #endif
							
							if (this.order.orderstate != 0) {
								let msg = this.order.orderstate == 1 ? '订单已取消' : (this.order.orderstate == 2 ? '订单已失效' : '订单已完成');
								this.$u.toast(msg);
								
								setTimeout(() => {
									// 在H5 刷新导致路由丢失
									var pages = getCurrentPages();
									//有上次页面，关闭所有页面
									if (pages.length <= 1) {
										//默认到首页
										uni.reLaunch({
											url: '/pages/index/index',
											complete(res) {
												console.log(res);
											}
										});
										return;
									}
									uni.$u.route({
										type: 'back',
										delta: 1
									});
								}, 1500);
							}
						} else {
							this.$u.toast(res.msg);
							setTimeout(() => {
								uni.$u.route({ type: 'back' });
							}, 1000);
						}
					});
			},
			
			// #ifdef MP-WEIXIN
			submit: async function() {
				let res = await this.$api.payment({
					order_sn: this.order_sn,
					paytype: this.paytype,
					openid: this.vuex_openid || "",
					//获取微信登录的code，用于换openid
					logincode: await this.getMpCode(),
					method: 'miniapp'
				});
				if (!res.code) {
					this.$u.toast(res.msg);
					return;
				}
				uni.requestPayment({
					provider: 'wxpay',
					timeStamp: res.data.timeStamp,
					nonceStr: res.data.nonceStr,
					package: res.data.package,
					signType: res.data.signType,
					paySign: res.data.paySign,
					success: rest => {
						this.$u.toast('支付成功！');
						wx.requestSubscribeMessage({
							tmplIds: this.vuex_config.tpl_ids,
							complete: (res) => {
								console.log(res)
								if (res.errMsg == 'requestSubscribeMessage:ok') {
									this.$api.subscribe({ tpl_ids: res, order_sn: this.order.order_sn, openid: this.vuex_openid }).then(res => {
										console.log(res)
									})
								}
								this.$u.route('/pages/order/list');
							}
						})
					},
					fail: err => {
						this.$u.toast('fail:' + JSON.stringify(err));
					}
				});
			},
			// #endif

			// #ifdef H5
			submit: async function() {
				let data = {
					order_sn: this.order_sn,
					paytype: this.paytype,
					openid: this.vuex_openid || "",
					method: 'wap'
				};
				//在微信环境，且为微信支付
				if (this.$util.isWeiXinBrowser() && this.paytype == 'wechat') {
					data.method = 'mp';
					let res = await this.$api.payment(data);
					//如果未设置openid则跳转获取openid
					if (!this.vuex_openid) {
						this.goAuth('/pages/login/openid', 'snsapi_base');
						return;
					}
					if (!res.code) {
						this.$u.toast(res.msg);
						return;
					}
					window.WeixinJSBridge.invoke(
						'getBrandWCPayRequest', {
							appId: res.data.appId, // 公众号名称，由商户传入
							timeStamp: res.data.timeStamp, // 时间戳，自1970年以来的秒数
							nonceStr: res.data.nonceStr, // 随机串
							package: res.data.package,
							signType: res.data.signType, // 微信签名方式：
							paySign: res.data.paySign // 微信签名
						},
						result => {
							if (result.err_msg === 'get_brand_wcpay_request:ok') {
								this.$u.toast('支付成功！');
								this.$u.route('/pages/order/list');
							} else if (result.err_msg === 'get_brand_wcpay_request:cancel') {
								this.$u.toast('取消支付');
							} else {
								this.$u.toast('支付失败');
							}
						}
					);
				} else {

					data.returnurl = window.location.href;
					let res = await this.$api.payment(data);
					if (!res.code) {
						this.$u.toast(res.msg);
						return;
					}
					//URL地址
					if (res.data.toString().match(/^((?:[a-z]+:)?\/\/)(.*)/i)) {
						location.href = res.data;
						return;
					}

					//Form表单
					document.getElementsByTagName("body")[0].innerHTML = res.data;
					let form = document.querySelector("form");
					if (form && form.length > 0) {
						form.submit();
						return;
					}

					//Meta跳转
					let meta = document.querySelector('meta[http-equiv="refresh"]');
					if (meta && meta.length > 0) {
						setTimeout(function() {
							location.href = meta.content.split(/;/)[1];
						}, 300);
						return;
					}
				}
			},

			// #endif

			// #ifdef APP-PLUS
			submit: async function() {

				let appid = plus.runtime.appid;

				let res = await this.$api.payment({
					order_sn: this.order_sn,
					paytype: this.paytype,
					method: 'app',
					appid: appid
				});
				if (!res.code) {
					this.$u.toast(res.msg);
					return;
				}
				uni.requestPayment({
					provider: this.paytype == 'alipay' ? 'alipay' : 'wxpay',
					orderInfo: res.data, //微信、支付宝订单数据
					success: function(rest) {
						this.$u.toast('支付成功！');
						this.$u.route('/pages/order/list');
					},
					fail: function(err) {
						console.log('fail:' + JSON.stringify(err));
					}
				});
			},
			// #endif
		}
	};
</script>

<style lang="scss">
	page {
		background-color: #f4f6f8;
	}
</style>
<style lang="scss" scoped>
	.thumb {
		width: 200rpx;
		height: 150rpx;
		border-radius: 10rpx;
	}

	.order {
		height: 150rpx;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		width: 68vw;
	}

	.paytype {
		width: 100vw;
	}

	.payment {
		position: fixed;
		bottom: 0;
		left: 0;
		width: 100%;
		padding: 30rpx 80rpx;
		z-index: 1999;
	}

	.list {
		background-color: #ffffff;

		.item {
			border-bottom: 1px solid #f4f6f8;

			image {
				width: 200rpx;
				height: 180rpx;
				border-radius: 5rpx;
			}

			.right {
				padding: 0 15rpx;
				height: 180rpx;
				display: flex;
				flex-direction: column;
				justify-content: space-between;

				.attrs {
					padding-top: 10rpx;
					width: 480rpx;
				}
			}
		}
	}
</style>
