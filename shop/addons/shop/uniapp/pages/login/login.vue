<template>
	<view class="">
		<!-- 顶部导航 -->
		<fa-navbar title="登录"></fa-navbar>
		<view class="login">
			<view v-if="checkLogintype('account')">
				<view class="u-m-t-50">
					<u-form :model="form" :rules="rules" ref="uForm" :errorType="errorType">
						<u-form-item :label-position="labelPosition" label="账号:" prop="account" left-icon="account" label-width="120">
							<u-input :border="border" placeholder="邮箱/手机/用户名" v-model="form.account" />
						</u-form-item>
						<u-form-item :label-position="labelPosition" label="密码:" prop="password" left-icon="lock" label-width="120" v-if="!border">
							<u-input :password-icon="true" :border="border" type="password" v-model="form.password" placeholder="请输入密码"></u-input>
						</u-form-item>
					</u-form>
				</view>
			</view>

			<view class="u-m-t-80">
				<u-button type="primary" hover-class="none" :custom-style="{ backgroundColor: theme.bgColor, color: theme.color }" shape="circle" @click="goLogin">
					登录
				</u-button>
			</view>

			<view class="u-m-t-40" v-if="checkLogintype('mobile') || checkLogintype('wechatmobile')">
				<u-button type="success" shape="circle" @click="goPage('/pages/login/mobilelogin')">
					使用手机验证码登录
				</u-button>
			</view>

			<view class="u-flex u-row-between u-tips-color u-m-t-10 u-p-20" v-if="checkLogintype('account')">
				<view @click="goPage('/pages/login/forgetpwd')">忘记密码</view>
				<view @click="goPage('/pages/login/register')">注册账号</view>
			</view>

			<view class="u-text-center other" v-if="isThreeLogin && checkLogintype('wechat')">
				<u-grid :col="1" :border="false">
					<u-grid-item @click="goThreeLogin">
						<u-icon name="weixin-fill" color="#53c240" :size="50"></u-icon>
						<view class="grid-text">微信登录</view>
					</u-grid-item>
				</u-grid>
			</view>

		</view>
	</view>
</template>

<script>
	import { loginfunc } from '@/common/fa.mixin.js';
	export default {
		mixins: [loginfunc],
		onLoad() {
			// #ifdef MP-WEIXIN || APP-PLUS
			this.isThreeLogin = true;
			// #endif

			// #ifdef H5
			if (this.$util.isWeiXinBrowser()) {
				this.isThreeLogin = true;
			}
			// #endif
		},
		// 必须要在onReady生命周期，因为onLoad生命周期组件可能尚未创建完毕
		onReady() {
			if (this.checkLogintype('account')) {
				this.$refs.uForm.setRules(this.rules);
			}
		},
		data() {
			return {
				labelPosition: 'top',
				border: false,
				errorType: ['message'],
				form: {
					account: '',
					password: ''
				},
				rules: {
					account: [{
						required: true,
						message: '请输入账号',
						// 可以单个或者同时写两个触发验证方式
						trigger: ['change', 'blur']
					}],
					password: [{
						required: true,
						message: '请输入密码',
						trigger: 'change'
					}]
				},
				isThreeLogin: false
			};
		},
		methods: {
			goThreeLogin: async function() {
				// #ifdef MP-WEIXIN
				this.goMpLogin();
				// #endif

				// #ifdef H5
				this.goAuth();
				// #endif

				// #ifdef APP-PLUS
				this.goAppLogin();
				// #endif
			},
			goLogin: function() {
				this.$refs.uForm.validate(async valid => {
					if (valid) {
						if (this.vuex_wx_uid) {
							this.form.wx_user_id = this.vuex_wx_uid;
						}
						let res = await this.$api.goLogin(this.form);
						if (!res.code) {
							this.$u.toast(res.msg);
							return;
						}
						this.$u.vuex('vuex_token', res.data.token);
						this.success();
					} else {
						this.$u.toast('验证失败');
					}
				});
			}
		}
	};
</script>

<style>
	page {
		background-color: #ffffff;
	}

	.login {
		padding: 80rpx 100rpx 0 100rpx;
	}

	.other {
		position: absolute;
		width: 100%;
		left: 0;
		bottom: 40rpx;
	}
</style>