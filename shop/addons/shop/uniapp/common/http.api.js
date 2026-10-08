const upload = async function(vm, {
		// #ifdef APP-PLUS || H5
		files,
		// #endif
		// #ifdef H5
		file,
		// #endif
		// #ifdef MP-ALIPAY
		fileType,
		// #endif
		filePath,
		name,
		formData
	}) {
	return new Promise((resolve, reject) => {
		uni.showLoading({
			mask: true,
			title: '上传中'
		});
		let data = {
			url: vm.vuex_config.upload.uploadurl,			
			header: {
				token: vm.vuex_token || '',
				uid: vm.vuex_user.id || 0
			},
			name: 'file',
			complete: function() {
				uni.hideLoading();
			},
			success: uploadFileRes => {
				try {
					var res = uploadFileRes.data;
					if (vm.$u.test.jsonString(res)) {						
						resolve(JSON.parse(res))						
					}
					if (vm.$u.test.object(res)) {
						resolve(res)
					}
				} catch (e) {
					reject(uploadFileRes.data);
				}
			},
			fail: (e) => {
				reject(e);
			}
		};
		// #ifdef H5
		//有文件对象，一般是H5
		if(file){
			data.file = file;
		}
		// #endif
		//文件路径
		if(filePath){
			data.filePath = filePath;
		}		
		let isObj = vm.$u.test.object(vm.vuex_config.upload.multipart);
		if (isObj && formData) {					
			data.formData = Object.assign(formData,vm.vuex_config.upload.multipart);			
		}else if(isObj){
			data.formData = vm.vuex_config.upload.multipart;
		}else if(formData){
			data.formData = formData;
		}
		uni.uploadFile(data);
	})

}

const install = (Vue, vm) => {

	vm.$api.getConfig 			= async (params = {}) => await vm.$u.get('/addons/shop/api.common/init', params);	
	vm.$api.area 				= async (params = {}) => await vm.$u.get('/addons/shop/api.common/area', params);	
	vm.$api.goUpload 	  		= async (params = {}) => await upload(vm, params);
	//用户
	vm.$api.getUserIndex 	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.user/index', params);
	vm.$api.getUserProfile 	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.user/profile', params);	
	vm.$api.goUserLogout 	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.user/logout', params);
	vm.$api.goUserAvatar 	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.user/avatar', params);
	vm.$api.getSigned 	  	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.user/getSigned',params);		
	// 登录	
	vm.$api.getEmsSend 		  	= async (params = {}) => await vm.$u.post('/addons/shop/api.ems/send', params);
	vm.$api.getSmsSend 		  	= async (params = {}) => await vm.$u.post('/addons/shop/api.sms/send', params);
	vm.$api.goLogin 		  	= async (params = {}) => await vm.$u.post('/addons/shop/api.login/login', params);
	vm.$api.mobilelogin 	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.login/mobilelogin', params);
	vm.$api.goRegister 		  	= async (params = {}) => await vm.$u.post('/addons/shop/api.login/register', params);
	vm.$api.goResetpwd 		  	= async (params = {}) => await vm.$u.post('/addons/shop/api.login/resetpwd', params);
	vm.$api.gowxLogin 		  	= async (params = {}) => await vm.$u.post('/addons/shop/api.login/wxLogin', params);
	vm.$api.goWechatMobileLogin = async (params = {}) => await vm.$u.post('/addons/shop/api.login/wechatMobileLogin', params);
	vm.$api.goAppLogin 		  	= async (params = {}) => await vm.$u.post('/addons/shop/api.login/appLogin', params);
	vm.$api.getWechatOpenid = async (params = {}) => await vm.$u.post('/addons/shop/api.login/getWechatOpenid', params);
	vm.$api.getWechatMobile  	= async (params = {}) => await vm.$u.post('/addons/shop/api.login/getWechatMobile', params);
	//第三方
	vm.$api.getAuthUrl 	  	  	= async (params = {}) => await vm.$u.get('/addons/third/api/getAuthUrl', params);
	vm.$api.goAuthCallback 	  	= async (params = {}) => await vm.$u.post('/addons/third/api/callback', params);
	vm.$api.goOpenidCallback 	= async (params = {}) => await vm.$u.post('/addons/third/api/getOpenidCallback', params);
	vm.$api.goThirdAccount 	  	= async (params = {}) => await vm.$u.post('/addons/third/api/account', params);
	// 签到	
	vm.$api.signinConfig 	  	= async (params = {}) => await vm.$u.get('/addons/signin/api.index/index',params);
	vm.$api.monthSign 	  	  	= async (params = {}) => await vm.$u.get('/addons/signin/api.index/monthSign',params);
	vm.$api.dosign 	 	      	= async (params = {}) => await vm.$u.post('/addons/signin/api.index/dosign',params);
	vm.$api.fillup 	  		  	= async (params = {}) => await vm.$u.get('/addons/signin/api.index/fillup',params);
	vm.$api.signRank 	 	  	= async (params = {}) => await vm.$u.get('/addons/signin/api.index/rank',params);
	vm.$api.signLog 	  	  	= async (params = {}) => await vm.$u.get('/addons/signin/api.index/signLog',params);
	//shop	
	vm.$api.getGoodsIndex 	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.goods/index',params);
	vm.$api.getGoodsInfo 	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.goods/detail',params);
	vm.$api.getGoodsList 	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.goods/lists',params);
	vm.$api.getWxCode 		 	= async (params = {}) => await vm.$u.post('/addons/shop/api.goods/getWxCode',params);
	
	vm.$api.getCategory 	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.category/index',params);
	vm.$api.allCategory  	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.category/alls',params);
	
	vm.$api.addCart		 	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.cart/add',params);
	vm.$api.getCartIndex 	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.cart/index',params);
	vm.$api.setCartNums 	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.cart/set_nums',params);
	vm.$api.delCart     	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.cart/del',params);
	vm.$api.cart_nums     	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.cart/cart_nums',params);
	
	vm.$api.orderList    	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.order/index',params);
	vm.$api.orderAdd    	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.order/add',params);
	vm.$api.orderDetail    	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.order/detail',params);
	vm.$api.orderCancel		  	= async (params = {}) => await vm.$u.post('/addons/shop/api.order/cancel',params);
	vm.$api.orderCarts			= async (params = {}) => await vm.$u.post('/addons/shop/api.order/carts',params);
	vm.$api.payment				= async (params = {}) => await vm.$u.post('/addons/shop/api.order/pay',params);
	vm.$api.takedelivery		= async (params = {}) => await vm.$u.post('/addons/shop/api.order/takedelivery',params);	
	vm.$api.logistics			= async (params = {}) => await vm.$u.get('/addons/shop/api.order/logistics',params);
	
	vm.$api.orderGoodsDetail    = async (params = {}) => await vm.$u.get('/addons/shop/api.order_goods/detail',params);
	vm.$api.ordeAfterSaleApply  = async (params = {}) => await vm.$u.post('/addons/shop/api.order_goods/apply',params);
	vm.$api.ordeAfterSale		= async (params = {}) => await vm.$u.get('/addons/shop/api.order_goods/aftersale',params);
	vm.$api.saveExpressInfo		= async (params = {}) => await vm.$u.post('/addons/shop/api.order_goods/saveExpressInfo',params);
	
	vm.$api.addressList    	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.address/index',params);
	vm.$api.addressAdd    	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.address/addedit',params);
	vm.$api.addressInfo    	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.address/detail',params);
	vm.$api.defAddress    	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.address/def_address',params);
	vm.$api.delAddress    	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.address/del',params);
	
	vm.$api.optionCollect    	= async (params = {}) => await vm.$u.post('/addons/shop/api.collect/optionCollect',params);
	vm.$api.collectList   	 	= async (params = {}) => await vm.$u.get('/addons/shop/api.collect/collectList',params);
	
	vm.$api.commentList    	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.comment/index',params);
	vm.$api.commentAdd    	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.comment/add',params);
	vm.$api.commentReply    	= async (params = {}) => await vm.$u.post('/addons/shop/api.comment/reply',params);
	
	vm.$api.scoreLogs 	  	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.score/logs',params);
	vm.$api.exchangeList 	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.score/exchangeList',params);
	vm.$api.exchange 	  	  	= async (params = {}) => await vm.$u.post('/addons/shop/api.score/exchange',params);
	vm.$api.myExchange 	  	  	= async (params = {}) => await vm.$u.get('/addons/shop/api.score/myExchange',params);
	
	vm.$api.couponList 			= async (params = {}) => await vm.$u.get('/addons/shop/api.coupon/couponList', params);
	vm.$api.couponDetail 		= async (params = {}) => await vm.$u.get('/addons/shop/api.coupon/couponDetail', params);
	vm.$api.drawCoupon 			= async (params = {}) => await vm.$u.post('/addons/shop/api.coupon/drawCoupon', params);
	vm.$api.myCouponList 		= async (params = {}) => await vm.$u.get('/addons/shop/api.coupon/myCouponList', params);
	vm.$api.commentMyList    	= async (params = {}) => await vm.$u.get('/addons/shop/api.comment/myList',params);
	
	vm.$api.pageIndex	    	= async (params = {}) => await vm.$u.get('/addons/shop/api.page/index',params);
	vm.$api.pageList	    	= async (params = {}) => await vm.$u.get('/addons/shop/api.page/lists',params);
		
	vm.$api.subscribe 		  = async (params = {}) => await vm.$u.post('/addons/shop/api.subscribe/index',params);
	
	vm.$api.attribute 		  = async (params = {}) => await vm.$u.get('/addons/shop/api.attribute/index',params);
}

export default {
	install
}
