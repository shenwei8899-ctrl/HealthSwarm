export const tools = {
	filters: {

	},
	computed: {

	},
	methods: {
		//富文本的回调
		navigate(e) {
			if (e.href && e.href.indexOf('http') == -1) { //不完整的链接					
				// #ifdef MP
				this.$util.uniCopy({
					content: this.vuex_config.upload.cdnurl + e.href,
					success: () => {
						this.$u.toast('链接已复制,请在浏览器中打开')
					}
				})
				// #endif
				// #ifndef MP				
				window.open(this.vuex_config.upload.cdnurl + e.href);
				// #endif
			}
		},
		//卡片跳转
		diylinkpress(e) {
			e.ignore();
			this.goPage(e.href);
			return false;
		},
		//预览图片
		lookImage(index) {
			uni.previewImage({
				current: index,
				urls: this.imagesList,
				longPressActions: {
					itemList: ['发送给朋友', '保存图片', '收藏'],
					success: function(data) {
						console.log(data)
					},
					fail: function(err) {
						console.log(err.errMsg);
					}
				}
			});
		},
		//复制url
		copyUrl(url = '') {
			this.$util.uniCopy({
				content: url || window.location.href,
				success: () => {
					this.$u.toast('复制成功，请去粘贴发送给好友吧');
				},
				error: () => {
					console.log('复制失败！')
				}
			})
		},
		//cdnurl
		cdnurl(url) {
			if (!/^((?:[a-z]+:)?\/\/|data:image\/)(.*)/.test(url)) {
				return this.vuex_config.upload.cdnurl + url;
			}
			return url;
		},
		//页面跳转
		goPage(path, auth) {
			if (path == 'out') {
				this.$u.vuex('vuex_token', '');
				this.$u.vuex('vuex_user', {});
				this.$u.vuex('vuex_openid', '');
				return;
			}
			if (auth && !this.vuex_token) {
				let pages = getCurrentPages();
				// 页面栈中的最后一个即为项为当前页面，route属性为页面路径
				let lastPageUrl = pages[pages.length - 1].$page.fullPath;
				this.$u.vuex('vuex_lasturl', lastPageUrl);
				this.$u.route('/pages/login/mobilelogin');
				return;
			}
			uni.$u.route({
				url: path,
				complete(e) {
					console.log(e, path)
				}
			})
		},
		logistics(res) {
			// #ifdef MP-WEIXIN
			if (this.vuex_config.logisticstype == 'kd100') {
				wx.navigateToMiniProgram({
					appId: 'wx6885acbedba59c14',
					path: `pages/result/result?nu=${res.expressno}&com=&querysource=third_xcx`, //备注：nu为快递单号，com为快递公司编码，com没有可不传
					extraData: {
						foo: 'bar'
					},
					success: (res) => {
						// 打开成功
					}
				});
			} else {
				this.goPage(`/pages/order/logistics?nu=${res.expressno}&coname=${res.expressname}&order_sn=${res.order_sn}`);
			}
			// #endif
			// #ifndef MP-WEIXIN
			this.goPage(`/pages/order/logistics?nu=${res.expressno}&coname=${res.expressname}&order_sn=${res.order_sn}`);
			// #endif
		}
	}
}
//修改头像的事件
export const avatar = {
	methods: {
		chooseAvatar() {
			uni.$on('uAvatarCropper', this.upload);
			this.$u.route({
				// 关于此路径，请见下方"注意事项"
				url: '/uview-ui/components/u-avatar-cropper/u-avatar-cropper',
				// 内部已设置以下默认参数值，可不传这些参数
				params: {
					// 输出图片宽度，高等于宽，单位px
					destWidth: 300,
					// 裁剪框宽度，高等于宽，单位px
					rectWidth: 300,
					// 输出的图片类型，如果'png'类型发现裁剪的图片太大，改成"jpg"即可
					fileType: 'jpg'
				}
			});
		},
		upload: async function(path) {
			uni.$off('uAvatarCropper', this.upload);
			// 可以在此上传到服务端
			try {
				let res = await this.$api.goUpload({
					filePath: path
				});
				if (!res.code) {
					this.$u.toast(res.msg);
				}
				this.form.avatar = res.data.url;
				this.url = res.data.fullurl;
				if (typeof this.editAvatar == 'function') {
					this.editAvatar();
				}
			} catch (e) {
				console.error(e);
				this.$u.toast('图片上传失败！');
			}
		}
	}
}

// 登录方法
export const loginfunc = {
	methods: {
		// 登录成功
		async success(delta) {
			//重置用户信息
			let apptype = '';
			let platform = '';
			let logincode = '';

			// #ifdef MP-WEIXIN
			platform = 'wechat';
			apptype = 'miniapp';
			logincode = await this.getMpCode();
			// #endif

			this.$api.getUserIndex({ apptype, platform, logincode }).then(res => {

				if (res.code) {
					this.$u.vuex('vuex_user', res.data.userInfo);
					if (res.data.openid) {
						this.$u.vuex('vuex_openid', res.data.openid);
					}
				}

				console.log(delta);
				var pages = getCurrentPages();
				if (!delta) {
					delta = 0;
					for (let i = pages.length; i > 0; i--) {
						console.log(pages[i - 1].route);
						if (pages[i - 1].route.indexOf("pages/login/") == -1) {
							break;
						} else {
							delta++;
						}
					}
					//根据pages自动计算出的delta
					console.log(delta);
				}

				let url = this.vuex_lasturl || '/pages/index/index';
				//清空最后页面
				this.$u.vuex('vuex_lasturl', '');

				//不在H5
				// #ifndef H5
				if (typeof pages[delta] !== 'undefined') {
					uni.navigateBack({
						delta: delta
					});
				} else {
					uni.reLaunch({
						url: url
					});
				}
				// #endif

				// 在H5 刷新导致路由丢失
				// #ifdef H5
				//有上次页面，关闭所有页面，到此页面,是从授权的，授权页面被刷新过
				if (pages.length <= 1 || pages[0].route.match(/pages\/login\//)) {
					uni.reLaunch({
						url: url
					});
				} else {
					uni.navigateBack({
						delta: delta
					});
				}
				// #endif

			});

		},
		// #ifdef MP-WEIXIN
		// 获取手机号回调
		async getPhoneNumber(e) {
			if (e.detail.errMsg === "privacy permission is not authorized") {
				this.$refs.uToast.show({
					title: '授权失败，失败原因：未同意隐私协议',
					type: 'error'
				});
				return;
			}
			if (e.detail.errMsg === "privacy permission is not authorized in gap") {
				this.$refs.uToast.show({
					title: '授权失败，原因：未同意隐私协议，请稍后重试',
					type: 'error'
				});
				return;
			}
			if (e.detail.errMsg === "getPhoneNumber:fail user deny") {
				this.$refs.uToast.show({
					title: '授权失败，原因：用户拒绝',
					type: 'error'
				});
				return;
			}
			if (e.detail.errMsg !== "getPhoneNumber:ok") {
				this.$refs.uToast.show({
					title: '授权失败，原因：' + e.detail.errMsg,
					type: 'error'
				});
				return;
			}
			if (typeof this.agreeChecked !== 'undefined' && !this.agreeChecked) {
				this.$refs.uToast.show({
					title: '请阅读并同意遵守《用户协议》',
					type: 'error'
				});
				return;
			}

			let logincode = await this.getMpCode();
			this.$api.goWechatMobileLogin({
				code: e.detail.code,
				logincode: logincode,
				bind: this.is_bind || ''
			}).then((res) => {
				if (res.code == 1) {
					this.$u.vuex('vuex_token', res.data.token);
					this.$u.vuex('vuex_openid', res.data.openid);
					this.success();
				} else {
					this.$u.toast(res.msg);
				}
			});

		},
		// 获取微信小程序用户openid
		async getWechatOpenid() {
			let logincode = await this.getMpCode();
			let res = await this.$api.getWechatOpenid({
				logincode: logincode,
			});
			if (res.code && res.data.openid) {
				this.$u.vuex('vuex_openid', res.data.openid);
				return res.data.openid;
			}
			return '';
		},
		// #endif

		// #ifdef H5
		// 公众号授权
		async goAuth(page, scope) {
			if (this.$util.isWeiXinBrowser()) {
				page = page ? page : '/pages/login/auth';

				let url = window.location.origin + (window.location.hash != '' ?
					window.location.pathname + '?hashpath=' + page :
					window.location.pathname.replace(/\/pages\/.*/, page));

				let res = await this.$api.getAuthUrl({
					platform: 'wechat',
					url: url,
					scope: scope || "",
				});
				if (!res.code) {
					this.$u.toast(res.msg);
					return;
				}
				var pages = getCurrentPages();
				let len = pages.length;
				if (len > 1) {
					let url = pages[len - 1].route;
					if (url.indexOf('/login/') != -1) {
						//找到上一个不是登录页面
						for (let i = len - 1; i >= 0; i--) {
							if (pages[i].route.indexOf('/login/') == -1) {
								this.$u.vuex('vuex_lasturl', '/' + pages[i].route + this.$u.queryParams(pages[i].options));
								break;
							}
						}
					} else {
						this.$u.vuex('vuex_lasturl', '/' + url + this.$u.queryParams(pages[pages.length - 1].options))
					}
				}
				window.location.href = res.data;
			}
		},
		// #endif
		// #ifdef MP-WEIXIN
		// 获取登录Code
		async getMpCode() {
			return new Promise((resolve, reject) => {
				uni.login({
					success: function(res) {
						if (res.code) {
							resolve(res.code);
						} else {
							//login成功，但是没有取到code
							reject('未取得code');
						}
					},
					fail: function(res) {
						reject('用户授权失败wx.login');
					}
				});
			});
		},
		// 微信授权登录
		async goMpLogin() {
			uni.showLoading({ title: '登录中...' });
			let that = this;
			try {
				let code = await that.getMpCode();
				let data = {
					code: code,
					__token__: that.vuex__token__
				};
				//有推荐码的话带上
				if (that.vuex_invitecode) {
					data.invitecode = that.vuex_invitecode;
				}
				let res = await this.$api.gowxLogin(data);
				uni.hideLoading();
				if (!res.code) {
					this.$u.toast(res.msg);
					return;
				}
				if (res.data.user) {
					this.$u.vuex('vuex_token', res.data.user.token);
					this.success();
					return;
				}
				this.$u.vuex('vuex_third', res.data.third);

				//授权成功到登录或绑定页面
				this.$u.route('/pages/login/register?bind=bind');
			} catch (e) {
				uni.hideLoading();
				that.$u.toast(e);
			}
		},
		// #endif
		// #ifdef APP-PLUS
		// App登录
		goAppLogin() {
			let that = this;
			var all, Service;
			// 1.发送请求获取code
			plus.oauth.getServices(
				function(Services) {
					all = Services;
					Object.keys(all).some(key => {
						if (all[key].id == 'weixin') {
							Service = all[key];
						}
					});
					Service.authorize(
						async function(e) {
								let res = await that.$api.goAppLogin({
									code: e.code,
									scope: e.scope
								});
								if (!res.code) {
									that.$u.toast(res.msg);
									return;
								}
								if (res.data.user) {
									that.$u.vuex('vuex_token', res.data.user.token);
									that.$u.vuex('vuex_user', res.data.user || {});
									that.success();
									return;
								}
								that.$u.vuex('vuex_third', res.data.third);
								that.$u.vuex('vuex_openid', res.data.openid);
								that.$u.route('/pages/login/register?bind=bind');
							},
							function(e) {
								that.$u.toast('授权失败！');
							}
					);
				},
				function(err) {
					console.log(err);
					that.$u.toast('授权失败！');
				}
			);
		},
		// #endif

		// 判断是否允许对应的登录方式
		checkLogintype(type) {
			return this.vuex_config.logintypearr && this.vuex_config.logintypearr.indexOf(type) > -1;
		}
	}
}