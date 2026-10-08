<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar title="申请售后" :border-bottom="false"></fa-navbar>
		<view class="order u-skeleton-rect">
			<view class="aftersale">
				<view class="item">
					<view class="left" @click="goPage('/pages/goods/detail?id=' + info.goods_id)"><image :src="info.image" mode="aspectFill"></image></view>
					<view class="content" @click="goPage('/pages/goods/detail?id=' + info.goods_id)">
						<view class="title u-line-2" v-text="info.title"></view>
						<view class="type u-line-2" v-text="info.attrdata || ''"></view>
						<view class="right u-flex">
							<view class="price">￥{{ info.price }}</view>
							<view class="number">×{{ info.nums }}</view>
						</view>
					</view>
				</view>
			</view>
		</view>
		<view class="u-p-30 u-m-t-30 bg-white">
			<view class="text-weight u-p-b-30">选择售后类型</view>
			<u-radio-group v-model="type">
				<u-radio :active-color="theme.bgColor" v-for="(item, index) in list" :key="index" :name="item.value">{{ item.name }}</u-radio>
			</u-radio-group>
		</view>
		<view class="u-p-30 u-m-t-30 bg-white">
			<view class="text-weight u-p-b-30">输入售后原因</view>
			<u-input v-model="reason" type="textarea" />
		</view>
		<view class="u-p-30 u-m-t-30 bg-white">
			<view class="text-weight u-p-b-30">上传图片</view>
			<u-upload
				width="150"
				height="150"
				ref="uUpload"
				@on-uploaded="onUploaded"
				@on-remove="onRemove"
				:action="uploadurl"
				:header="header"
				:form-data="formdata"
			></u-upload>
		</view>
		<u-gap height="150" bg-color="#f4f6f9"></u-gap>
		<view class="footer-bar u-flex u-row-center u-border-top">
			<u-button
				size="medium"
				type="primary"
				hover-class="none"
				:custom-style="{ width: '80vw', backgroundColor: theme.bgColor, color: theme.color }"
				shape="circle"
				@click="apply"
			>
				立即申请
			</u-button>
		</view>
	</view>
</template>

<script>
export default {
	onLoad(e) {
		this.id = e.id || '';
	},
	onShow() {
		this.getOrderGoodsDetail();
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
			id: '',
			info: {},
			list: [
				{
					name: '仅退款',
					value: 1
				},
				{
					name: '退货退款',
					value: 2
				}
			],
			type: 2,
			loading: true,
			reason: '',
			expressno: '',
			images: ''
		};
	},
	methods: {
		getOrderGoodsDetail() {
			this.$api.orderGoodsDetail({ id: this.id }).then(res => {
				if (res.code == 1) {
					this.info = res.data;
					this.loading = false;
				}else{
					this.$u.toast(res.msg);
					setTimeout(()=>{
						uni.$u.route({
							type:'back'
						})
					},1000)
				}
			});
		},
		onUploaded(e, name) {
			console.log(e, name);
			this.images = e
				.map(item => {
					return item.response.data.url;
				})
				.join(',');
		},
		onRemove(index, lists, name) {
			this.images = lists
				.map(item => {
					return item.response.data.url;
				})
				.join(',');
		},
		apply() {
			if (!this.reason) {
				this.$u.toast('请输入售后原因');
				return;
			}
			this.$api
				.ordeAfterSaleApply({
					id: this.id,
					reason: this.reason,
					images: this.images,
					expressno: this.expressno,
					type:this.type
				})
				.then(res => {
					this.$u.toast(res.msg);
					if (res.code) {
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

<style lang="scss">
page {
	background-color: #f4f6f8;
}
</style>
<style lang="scss" scoped>
.order {
	background-color: #ffffff;
	box-sizing: border-box;
	font-size: 28rpx;
	.item {
		display: flex;
		justify-content: space-between;
		padding: 30rpx 0;
		border-top: 1px solid #f4f6f8;
		.left {
			margin-right: 20rpx;
			image {
				width: 200rpx;
				height: 150rpx;
				border-radius: 10rpx;
			}
		}
		.content {
			display: flex;
			flex-direction: column;
			justify-content: space-between;
			flex: 1;
			.title {
				font-size: 28rpx;
				line-height: 40rpx;
			}
			.type {
				margin: 10rpx 0;
				font-size: 24rpx;
				color: $u-tips-color;
			}
			.delivery-time {
				color: #e5d001;
				font-size: 24rpx;
			}
			.right {
				.number {
					padding-left: 30rpx;
					color: $u-tips-color;
					font-size: 24rpx;
				}
			}
		}
	}
	.aftersale {
		width: 100vw;
		padding: 0 30rpx;
	}
}
</style>
