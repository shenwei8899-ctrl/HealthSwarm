<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar title="查看售后" :border-bottom="false"></fa-navbar>
		<view class="order u-skeleton-rect">
			<view class="item">
				<view class="left" @click="goPage('/pages/goods/detail?id=' + goods.goods_id)"><image :src="goods.image" mode="aspectFill"></image></view>
				<view class="content" @click="goPage('/pages/goods/detail?id=' + goods.goods_id)">
					<view class="title u-line-2" v-text="goods.title"></view>
					<view class="type u-line-2" v-text="goods.attrdata || ''"></view>
					<view class="right u-flex">
						<view class="price">￥{{ goods.price }}</view>
						<view class="number">×{{ goods.nums }}</view>
					</view>
				</view>
			</view>
		</view>
		<view class="u-p-30 u-m-t-30 bg-white">
			<view class="text-weight u-p-b-30">售后状态</view>
			<text :class="info.status == 2 ? 'u-type-success' : 'u-type-error'">{{ info.status_text || '' }}{{ goods.salestate == 3 ? ',等待退货!' : '' }}</text>
		</view>
		<view class="u-p-30 u-m-t-30 bg-white">
			<view class="text-weight u-p-b-30">售后类型</view>
			<text >{{info.type_text}}</text>
		</view>
		<view class="u-p-30 u-m-t-30 bg-white" v-if="info.refund > 0">
			<view class="text-weight u-p-b-30">退款金额</view>
			<text class="u-type-error" v-text="'￥' + info.refund "></text>
			<text class="u-type-info" v-text="'（商品实付:￥' + info.realprice+ ' + 运费:￥' + info.shippingfee + '）' "></text>
		</view>
		<view class="u-p-30 u-m-t-30 bg-white">
			<view class="text-weight u-p-b-30">售后原因</view>
			<text class="u-tips-color" v-text="info.reason"></text>
		</view>
		<view class="u-p-30 u-m-t-30 bg-white" v-if="info.images && info.images.length">
			<view class="text-weight u-p-b-30">售后图片</view>
			<u-grid :col="4" :border="false" @click="preview">
				<u-grid-item v-for="(item, index) in info.images" :index="index" :key="index">
					<u-image width="120rpx" height="120rpx" :src="item"></u-image>
				</u-grid-item>
			</u-grid>
		</view>
		<view class="u-p-30 u-m-t-30 u-m-b-30 bg-white" v-if="info.mark">
			<view class="text-weight u-p-b-30">卖家回复</view>
			<text class="u-tips-color" v-text="info.mark"></text>
		</view>
		<!-- goods.salestate==3 退货录入快递单号 -->
		<view class="u-p-30 u-m-t-30 bg-white" v-if="info.type==2 && [3,5].includes(goods.salestate)">
			<view class="u-m-t-10 u-m-b-30 u-flex">
				<text class="u-m-r-15">快递名称:</text>
				<u-input v-model="expressname" :disabled="info.expressname!=''" placeholder="请输入快递名称" />
			</view>
			<view class="u-p-t-30 u-m-b-30 u-border-top u-flex">
				<text class="u-m-r-15">快递单号:</text>
				<u-input v-model="expressno" :disabled="info.expressno!=''" placeholder="请输入快递单号" />
			</view>
			<view class="u-p-t-30 u-flex u-row-center u-border-top">
				<u-button
					size="medium"
					type="default"
					hover-class="none"
					:custom-style="btnStyle"
					shape="circle"
					:disabled="is_disabld"
					@click="show=true"
				>
					保存快递信息
				</u-button>
			</view>
		</view>
		<u-modal v-model="show" content="请确定快递名称和快递单号是否正确？" :show-cancel-button="true" @confirm="submit"></u-modal>
	</view>
</template>

<script>
export default {
	onLoad(e) {
		this.id = e.id || '';
	},
	onShow() {
		this.getOrdeAfterSale();
	},
	computed:{
		is_disabld(){
			return this.info.expressno!='' && this.info.expressname!='';
		},
		btnStyle(){
			let style = { width: '80vw' };
			if(!this.is_disabld){
				style.backgroundColor = this.theme.bgColor;
				style.color = this.theme.color
			}
			return style;
		}
	},
	data() {
		return {
			show:false,
			info: {},
			goods: {},
			expressname: '',
			expressno: ''
		};
	},
	methods: {
		getOrdeAfterSale() {
			this.$api.ordeAfterSale({ id: this.id }).then(res => {
				if (res.code) {
					this.info = res.data;
					this.goods = res.data.order_goods;
					this.expressname = res.data.expressname;
					this.expressno = res.data.expressno;
				}
				uni.stopPullDownRefresh();
			});
		},
		preview(index) {
			uni.previewImage({
				current: index,
				urls: this.info.images,
				longPressActions: {
					itemList: ['发送给朋友', '保存图片', '收藏'],
					success: function(data) {
						console.log(data);
					},
					fail: function(err) {
						console.log(err.errMsg);
					}
				}
			});
		},
		submit() {
			this.$api
				.saveExpressInfo({
					expressname: this.expressname,
					expressno: this.expressno,
					id: this.id
				})
				.then(res => {
					this.$u.toast(res.msg);
					if(res.code){
						setTimeout(()=>{
							this.getOrdeAfterSale();
						},1000)
					}
				});
		}
	},
	onPullDownRefresh() {
		this.getOrdeAfterSale();
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
	padding: 0 30rpx;
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
					padding-left: 10rpx;
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
