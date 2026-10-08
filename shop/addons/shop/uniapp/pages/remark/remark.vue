<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar title="评价" :border-bottom="false"></fa-navbar>
		<view class="u-p-30">
			<view class="" v-if="showForm">
				<u-form :model="form" ref="uForm">
					<view class="item" v-for="(item, index) in order_goods" :key="index">
						<view class="goods">
							<view class="left"><image :src="item.image" mode="aspectFill"></image></view>
							<view class="content">
								<view class="title u-line-2">{{ item.title }}</view>
								<view class="type u-line-2">{{ item.attrdata || '' }}</view>
								<u-form-item :border-bottom="false" style="padding: 0;" :prop="'star__' + index">
									<u-rate :count="count" v-model="form['star__' + index]"></u-rate>
								</u-form-item>
							</view>
						</view>
						<view class="">
							<u-form-item style="padding: 0;" label-position="top" :border-bottom="false" :prop="'content__' + index">
								<u-input type="textarea" height="150" maxlength="150" :fixed="true" v-model="form['content__' + index]" />
							</u-form-item>
						</view>
						<view class="u-m-b-30">
							<u-upload
								width="150"
								height="150"
								ref="uUpload"
								@on-uploaded="onUploaded"
								@on-remove="onRemove"
								:action="uploadurl"
								:header="header"
								:form-data="formdata"
								:index="index"
							></u-upload>
						</view>
					</view>
				</u-form>
			</view>
		</view>
		<view class="u-p-60">
			<u-button type="primary" hover-class="none" :custom-style="{ backgroundColor: theme.bgColor, color: theme.color }" shape="circle" @click="submit">
				立即提交
			</u-button>
		</view>
	</view>
</template>

<script>
export default {
	onLoad(e) {
		this.order_sn = e.order_sn || '';
		this.getDetail();
	},
	computed: {
		header() {
			return {
				token: this.vuex_token || '',
				uid: this.vuex_user.id || 0
			};
		},
		formdata() {
			let multipart = (this.vuex_config.config && this.vuex_config.config.upload.multipart) || '';
			let isObj = this.$u.test.object(multipart);
			if (isObj) {
				return this.vuex_config.config.upload.multipart;
			}
			return {};
		},
		uploadurl() {
			if (!this.vuex_config.upload) {
				return '';
			}
			return this.vuex_config.upload.uploadurl;
		}
	},
	data() {
		return {
			showForm: false,
			form: {},
			rules: {},
			count: 5,
			order_sn: '',
			info: {},
			order_goods:[]
		};
	},
	methods: {
		getDetail() {
			this.$api.orderDetail({ order_sn: this.order_sn }).then(res => {
				if (res.code) {
					this.info = res.data;
					this.order_goods = res.data.order_goods.filter(item=>[0,6].includes(item.salestate));
					let form = {},
						rules = {};
					this.order_goods.forEach((item, index) => {						
							form['star__' + index] = 5;
							form['content__' + index] = '';
							form['images__' + index] = '';
							form['goods_id__' + index] = item.goods_id;
							rules['content__' + index] = [
								{
									required: true,
									message: '请输入评论内容',
									trigger: ['change', 'blur']
								},
								{
									min: 5,
									message: '评论不能少于5个字',
									trigger: 'change'
								}
							];						
					});
					this.form = form;
					this.rules = rules;
					this.showForm = true;
					this.$nextTick(() => {
						this.$refs.uForm.setRules(this.rules);
					});
				}
			});
		},
		onUploaded(e, name) {
			console.log(e, name);
			this.form['images__' + name] = e
				.map(item => {
					return item.response.data.url;
				})
				.join(',');
		},
		onRemove(index, lists, name) {
			this.form['images__' + name] = lists
				.map(item => {
					return item.response.data.url;
				})
				.join(',');
		},
		submit() {
			this.$refs.uForm.validate(valid => {
				if (valid) {
					if (!this.order_sn) {
						this.$u.toast('参数缺失！');
						return;
					}
					let form = { order_sn: this.order_sn };
					let arr = [];
					for (let [key, item] of Object.entries(this.form)) {
						let k = key.split('__');
						if (arr[k[1]] == undefined) {
							arr.push({
								content: '',
								goods_id: '',
								star: 5,
								images: ''
							});
						}
						arr[k[1]][k[0]] = item;
					}
					form.remark = arr;
					this.$api.commentAdd(form).then(res => {
						this.$u.toast(res.msg);
						if (res.code == 1) {
							setTimeout(() => {
									uni.$u.route({
										type:'back'
									})
							}, 1000);
						}
					});
				} else {
					console.log('验证失败');
				}
			});
		}
	}
};
</script>

<style lang="scss" scoped>
.item {
	border-bottom: 1px solid #f4f4f6;
	.goods {
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
			}
			.type {
				margin-top: 10rpx;
				font-size: 24rpx;
				color: $u-tips-color;
			}
		}
	}
}
</style>
