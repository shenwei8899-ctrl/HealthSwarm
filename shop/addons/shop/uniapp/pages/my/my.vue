<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar title="个人中心" :border-bottom="false"></fa-navbar>
		<!-- 会员中心 -->
		<view class="u-p-t-30 u-p-b-50 home" :style="[{ backgroundColor: theme.bgColor || '#374486' }]">
			<view class="userinfo">
				<block v-if="vuex_token">
					<u-avatar
						size="120"
						:show-sex="true"
						:sex-icon="vuex_user.gender == 1 ? 'man' : 'woman'"
						:src="url || vuex_user.avatar"
						@click="goPage('/pages/my/profile', true)"
					></u-avatar>
					<view class="u-skeleton-fillet u-m-t-10 u-p-l-80 u-p-r-80 u-line-1" @click="goPage('/pages/my/profile', true)">{{ vuex_user.nickname || '' }}</view>
					<view class="u-skeleton-fillet u-m-t-10 u-p-l-80 u-p-r-80 u-line-2" @click="goPage('/pages/my/profile', true)">{{ vuex_user.bio || '这家伙很懒，什么也没写！' }}</view>
				</block>
				<block v-else>
					<u-avatar size="120"></u-avatar>
					<view class="u-m-t-30"><u-button hover-class="none" size="mini" @click="goPage('/pages/login/mobilelogin')">立即登录</u-button></view>
				</block>
			</view>
			<view class="corrugated">
				<view class="wave-top wave-item" v-if="wavetop" :style="[{ backgroundImage: 'url(' + wavetop + ')' }]"></view>
				<view class="wave-middle wave-item" v-if="wavemiddle" :style="[{ backgroundImage: 'url(' + wavemiddle + ')' }]"></view>
				<view class="wave-bottom wave-item" v-if="wavebottom" :style="[{ backgroundImage: 'url(' + wavebottom + ')' }]"></view>
			</view>
		</view>
		<!-- 统计 -->
		<view class="u-flex u-text-center u-p-l-30 u-p-r-30 u-p-t-50 u-p-b-50 bg-white">
			<view class="u-flex-4" @click="goPage('/pages/order/list?status=1', true)">
				<view class="u-text-weight u-font-28"><text v-text="(vuex_user.order && vuex_user.order.created) || 0"></text></view>
				<view class="u-m-t-20">待付款</view>
			</view>
			<view class="u-flex-4 u-border-left u-border-right" @click="goPage('/pages/order/list?status=2', true)">
				<view class="u-text-weight u-font-28"><text v-text="(vuex_user.order && vuex_user.order.paid) || 0"></text></view>
				<view class="u-m-t-20">待发货</view>
			</view>
			<view class="u-flex-4" @click="goPage('/pages/order/list?status=4', true)">
				<view class="u-text-weight u-font-28"><text v-text="(vuex_user.order && vuex_user.order.evaluate) || 0"></text></view>
				<view class="u-m-t-20">待评论</view>
			</view>
		</view>
		<!-- 导航 -->
		<view class="u-m-t-30 u-m-b-15">
			<u-cell-group>
				<u-cell-item icon="list" title="我的订单" @click="goPage('/pages/order/list', true)"></u-cell-item>
				<u-cell-item icon="pushpin-fill" title="每日一签" @click="toSignin"></u-cell-item>
				<u-cell-item icon="heart-fill" title="我的收藏" @click="goPage('/pages/my/collect', true)"></u-cell-item>
				<u-cell-item icon="map-fill" title="我的地址" @click="goPage('/pages/address/address', true)"></u-cell-item>
				<u-cell-item icon="coupon-fill" title="我的优惠券" @click="goPage('/pages/coupon/user',true)"></u-cell-item>
				<u-cell-item icon="integral-fill" title="我的积分兑换" @click="goPage('/pages/score/order',true)"></u-cell-item>
				<view class="u-border-bottom u-p-30">
					<!-- #ifdef MP-WEIXIN -->
						<button class="share-btn u-flex u-row-between" open-type="contact">
							<view class="fa-cell">
								<u-icon size="34" name="server-man"></u-icon>
								<text class="u-m-l-10">联系客服</text>
							</view>
							<view class="">
								<u-icon name="arrow-right" color="#969799"></u-icon>
							</view>
						</button>		
					<!-- #endif -->
					<!-- #ifndef MP-WEIXIN -->
						<button class="share-btn u-flex u-row-between" @click="callphone">
							<view class="fa-cell">
								<u-icon size="34" name="server-man"></u-icon>
								<text class="u-m-l-10">联系客服</text>
							</view>
							<view class="">
								<u-icon name="arrow-right" color="#969799"></u-icon>
							</view>
						</button>		
					<!-- #endif -->
				</view>
				<u-cell-item icon="account-fill" title="个人资料" @click="goPage('/pages/my/profile', true)"></u-cell-item>
				<u-cell-item icon="question-circle" title="帮助中心" @click="goPage('/pages/help/index')"></u-cell-item>
				<u-cell-item icon="info-circle-fill" title="关于我们" @click="goPage('/pages/page/page?diyname=aboutus')"></u-cell-item>
				<u-cell-item icon="backspace" v-if="vuex_token" title="退出登录" @click="goPage('out')"></u-cell-item>
			</u-cell-group>
		</view>
		<u-top-tips ref="uTips" :navbar-height="statusBarHeight + navbarHeight"></u-top-tips>
		<!-- 底部导航 -->
		<fa-tabbar></fa-tabbar>
	</view>
</template>

<script>
import { avatar } from '@/common/fa.mixin.js';
export default {
	mixins: [avatar],
	computed: {
		wavetop() {
			return this.$u.http.config.baseUrl + '/assets/addons/shop/img/wave-top.png';
		},
		wavemiddle() {
			return this.$u.http.config.baseUrl + '/assets/addons/shop/img/wave-mid.png';
		},
		wavebottom() {
			return this.$u.http.config.baseUrl + '/assets/addons/shop/img/wave-bot.png';
		},
		isBind() {
			return false;
		}
	},
	onShow() {
		if (this.vuex_token) {
			this.getUserIndex();
		} else {
			this.$u.vuex('vuex_user', {});
		}
		//移除事件监听
		uni.$off('uAvatarCropper', this.upload);
	},
	data() {
		return {
			// 状态栏高度，H5中，此值为0，因为H5不可操作状态栏
			statusBarHeight: uni.getSystemInfoSync().statusBarHeight,
			// 导航栏内容区域高度，不包括状态栏高度在内
			navbarHeight: 44,
			url: '',
			form: {
				avatar: ''
			}
		};
	},
	methods: {
		getUserIndex: async function() {
			let res = await this.$api.getUserIndex();
			uni.stopPullDownRefresh();
			if (res.code == 1) {
				this.$u.vuex('vuex_user', res.data.userInfo || {});
				if (res.data.showProfilePrompt && !this.vuex_setting.prompted) {
					// 弹窗每次登录状态只提示一次
					this.$u.vuex('vuex_setting.prompted', true);
					uni.showModal({
						title: '温馨提示',
						confirmText: '去设置',
						cancelText: '取消',
						showCancel: true,
						content: '当前未设置昵称，请设置昵称后再继续操作',
						success: (res) => {
				
							if (res.confirm) {
								this.$u.route("/pages/my/profile");
							} else if (res.cancel) {
				
							}
						}
					});
				}
			} else {
				this.$u.toast(res.msg);
				return;
			}
		},
		toSignin() {
			if (!this.vuex_user.is_install_signin) {
				this.$refs.uTips.show({
					title: '请先安装会员签到插件插件或启用该插件',
					type: 'error',
					duration: '3000'
				});

				return;
			}
			this.goPage('/pages/signin/signin', true);
		},
		editAvatar: async function() {
			let res = await this.$api.goUserAvatar({
				avatar: this.form.avatar
			});
		},
		// #ifndef MP-WEIXIN
		callphone(){
			uni.makePhoneCall({
			    phoneNumber: this.vuex_config.phone //仅为示例
			});
		}
		// #endif
	},
	//下拉刷新
	onPullDownRefresh() {
		if (this.vuex_token) {
			this.getUserIndex();
		} else {
			uni.stopPullDownRefresh();
			this.$u.toast('请先登录');
			this.$u.vuex('vuex_user', {});
		}
	}
};
</script>

<style lang="scss">
page {
	background-color: #f4f6f8;
}
.fa-cell{
	color: #606266;
}
.home {
	position: relative;
	.userinfo {
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 30rpx 0;
		z-index: 100;
		height: 310rpx;
		.u-skeleton-fillet {
			color: #ffffff;
			z-index: 101;
		}
	}
	.corrugated {
		bottom: -2rpx;
		left: 0;
		position: absolute;
		width: 100%;
		height: 50%;
		overflow: hidden;
		z-index: 0;
		.wave-item {
			position: absolute;
			width: 200%;
			left: 0;
			height: 200rpx;
			background-repeat: repeat no-repeat;
			background-position: 0 bottom;
			transform-origin: center bottom;
		}
		.wave-top {
			opacity: 0.5;
			animation: wave-animation 3s;
			animation-delay: 1s;
			background-size: 50% 60rpx;
			z-index: 15;
		}
		.wave-middle {
			opacity: 0.75;
			animation: wavemove 10s linear infinite;
			background-size: 50% 80rpx;
			z-index: 10;
		}
		.wave-bottom {
			animation: wavemove 15s linear infinite;
			background-size: 50% 45rpx;
			z-index: 5;
		}
	}
}

@keyframes wavemove {
	0% {
		transform: translateX(0) translateZ(0) scaleY(1);
	}
	50% {
		transform: translateX(-25%) translateZ(0) scaleY(0.55);
	}
	100% {
		transform: translateX(-50%) translateZ(0) scaleY(1);
	}
}
</style>
