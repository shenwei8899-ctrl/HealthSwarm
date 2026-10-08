<template>
	<view class="u-skeleton">
		<!-- 顶部导航 -->
		<fa-navbar title="订单详情" :border-bottom="false"></fa-navbar>
		<view class="order u-skeleton-rect">
			<view class="item" v-for="(item, index) in info.order_goods" :key="index">
				<view class="left" @click="goPage('/pages/goods/detail?id=' + item.goods_id)"><image :src="item.image" mode="aspectFill"></image></view>
				<view class="content">
					<view class="title u-line-2" @click="goPage('/pages/goods/detail?id=' + item.goods_id)" v-text="item.title"></view>
					<view class="type u-line-2" @click="goPage('/pages/goods/detail?id=' + item.goods_id)" v-text="item.attrdata || ''"></view>
					<view class="u-flex">
						<!-- 申请售后：已发货,订单正常 -->
						<view
							class="u-m-r-10"
							v-if="info.paystate && !info.shippingstate && [0, 6].includes(item.salestate)"
							@click="(order_goods_id = item.id), (is_refund = true)"
						>
							<u-tag text="退款" mode="plain" shape="circle" size="mini" type="error"></u-tag>
						</view>
						<view class="u-m-r-10" v-if="item.salestate == 2"><u-tag text="退款中" mode="plain" shape="circle" size="mini" type="warning" /></view>
						<view class="u-m-r-10" v-if="item.salestate == 3"><u-tag text="退货中" mode="plain" shape="circle" size="mini" type="warning" /></view>
						<view class="u-m-r-10" v-if="item.salestate == 4"><u-tag text="已退款" mode="plain" shape="circle" size="mini" type="success" /></view>
						<view class="u-m-r-10" v-if="item.salestate == 5"><u-tag text="已退货退款" mode="plain" shape="circle" size="mini" type="success" /></view>
						<view
							class="u-m-r-10"
							v-if="info.shippingstate && [0, 3,4].includes(info.orderstate) && !item.salestate"
							@click="goPage('/pages/order/apply?id=' + item.id)"
						>
							<u-tag text="申请售后" mode="plain" shape="circle" size="mini" type="error"></u-tag>
						</view>
						<view
							class="u-m-r-10"
							v-if="info.shippingstate && [0, 3,4].includes(info.orderstate) && item.salestate == 6"
							@click="goPage('/pages/order/apply?id=' + item.id)"
						>
							<u-tag text="继续申请" mode="plain" shape="circle" size="mini" type="error"></u-tag>
						</view>
						<!-- 申请售后：退货中,已退货,已退款 -->
						<view class="" v-if="[1, 2, 3, 6].includes(item.salestate)" @click="goPage('/pages/order/aftersale?id=' + item.id)">
							<u-tag text="查看售后" mode="plain" shape="circle" size="mini"></u-tag>
						</view>
					</view>
				</view>
				<view class="right" @click="goPage('/pages/goods/detail?id=' + item.goods_id)">
					<view class="price">
						￥{{ priceInt(item.price) }}
						<text class="decimal">.{{ priceDecimal(item.price) }}</text>
					</view>
					<view class="number">×{{ item.nums }}</view>
				</view>
			</view>
		</view>
		<view class="u-m-t-30 u-m-b-30 u-skeleton-rect">
			<u-cell-group>
				<u-cell-item :arrow="false" title="订单编号" :value="info.order_sn" @click="copy"></u-cell-item>
				<u-cell-item :arrow="false" title="下单时间" :value="info.createtime | date('yyyy-mm-dd hh:MM:ss')"></u-cell-item>
				<u-cell-item :arrow="false" title="支付时间" :value="info.paytime ? $u.timeFormat(info.paytime, 'yyyy-mm-dd hh:MM:ss') : ''"></u-cell-item>
				<u-cell-item :arrow="false" title="配送时间" :value="info.shippingtime ? $u.timeFormat(info.shippingtime, 'yyyy-mm-dd hh:MM:ss') : ''"></u-cell-item>
				<u-cell-item :arrow="false" title="商品金额" :value="'￥' + info.amount"></u-cell-item>
				<u-cell-item :arrow="false" title="优惠金额" :value="'￥' + info.discount"></u-cell-item>
				<u-cell-item :arrow="false" title="运费" :value="'￥' +info.shippingfee"></u-cell-item>
				<u-cell-item :arrow="false" title="订单金额" :value="'￥' + info.saleamount"></u-cell-item>
				<u-cell-item :arrow="false" title="收货信息">
          <view class="u-line-2">{{ info.receiver + ' ' + info.mobile }}</view>
          <view class="u-line-2">{{ info.address }}</view>
        </u-cell-item>
				<u-cell-item :arrow="false" title="订单备注" :value="info.memo"></u-cell-item>
			</u-cell-group>
		</view>
		<u-gap height="120" bg-color="#f4f6f9" v-if="!['canceled', 'expired', 'finished', 'refunding'].includes(info.status)"></u-gap>
		<!-- 底部导航条 -->
		<view class="footer-bar u-flex u-border-top">
			<view>
				<text class="u-tips-color">状态:</text>
				<text class="u-m-l-10" style="color: #f29100;">{{ info.status_text }}</text>
			</view>
			<view class="u-flex u-flex-1 u-row-right u-m-l-10">
				<!-- 取消订单 -->
				<view class="u-m-l-15" v-if="!info.paystate && !info.orderstate">
					<u-button hover-class="none" size="mini" :custom-style="{ width: '150rpx' }" shape="circle" @click="show = true">取消订单</u-button>
				</view>
				<!-- 查看物流：已发货,已收货,订单正常，订单完成 -->
				<view class="u-m-l-15" v-if="info.shippingstate && [0, 3,4].includes(info.orderstate)">
					<u-button hover-class="none" size="mini" type="primary" :plain="true" shape="circle" @click="logistics(info)">查看物流</u-button>
				</view>
				<!-- 确认收货 -->
				<view class="u-m-l-15" v-if="info.shippingstate == 1 && !info.orderstate">
					<u-button hover-class="none" size="mini" type="success" @click="shipped" :custom-style="{ width: '150rpx' }" :plain="true" shape="circle">
						确认收货
					</u-button>
				</view>
				<!-- 立即评价 -->
				<view class="u-m-l-15" v-if="info.shippingstate == 2 && !info.orderstate && info.paystate == 1">
					<u-button
						size="mini"
						hover-class="none"
						@click="goPage('/pages/remark/remark?order_sn=' + info.order_sn)"
						:custom-style="{ width: '150rpx' }"
						type="warning"
						:plain="true"
						shape="circle"
					>
						立即评价
					</u-button>
				</view>
				<!-- 立即支付 -->
				<view class="u-m-l-15" v-if="!info.paystate && !info.orderstate">
					<u-button
						size="mini"
						hover-class="none"
						:custom-style="{ width: '150rpx', backgroundColor: theme.bgColor, color: theme.color }"
						shape="circle"
						:plain="true"
						@click="goPage('/pages/order/payment?order_sn=' + info.order_sn)"
					>
						立即支付
					</u-button>
				</view>
			</view>
		</view>
		<u-skeleton :loading="loading" :animation="true" bgColor="#FFF"></u-skeleton>
		<u-modal v-model="show" content="确认取消订单吗？" @confirm="cancel" :show-cancel-button="true"></u-modal>
		<u-modal v-model="is_refund" content="确认退款吗？" @confirm="refund" :show-cancel-button="true"></u-modal>
	</view>
</template>

<script>
export default {
	onLoad(e) {
		this.order_sn = e.order_sn || '';
	},
	onShow() {
		this.getOrderDetail();
	},
	computed: {
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
	data() {
		return {
			id: '',
			info: {},
			show: false,
			loading: true,
			is_refund: false,
			order_goods_id: ''
		};
	},
	methods: {
		getOrderDetail() {
			this.$api.orderDetail({ order_sn: this.order_sn }).then(res => {
				if (res.code == 1) {
					this.info = res.data;
					this.loading = false;
				}else{
					this.$u.toast(res.msg);
					setTimeout(()=>{
						uni.$u.route({
							type:'back'
						})
					},1500)
				}
				uni.stopPullDownRefresh();
			});
		},
		shipped() {
			this.$api.takedelivery({ order_sn: this.order_sn }).then(res => {
				this.$u.toast(res.msg);
				if (res.code) {
					this.getOrderDetail();
				}
			});
		},
		refund() {
			this.$api
				.ordeAfterSaleApply({
					id: this.order_goods_id,
					type: 1
				})
				.then(res => {
					this.$u.toast(res.msg);
					if (res.code) {
						this.getOrderDetail();
					}
			});
		},		
		cancel() {
			this.$api.orderCancel({ order_sn: this.order_sn }).then(res => {
				this.$u.toast(res.msg);
				if (res.code == 1) {
					this.getOrderDetail();
				}
			});
		},
		//复制订单编号
		copy(){
			this.$util.uniCopy({
				content:this.info.order_sn,
				success:()=>{
					this.$u.toast('订单编号已复制')
				}
			})
		}
	},
	onPullDownRefresh() {
		this.getOrderDetail();
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
	padding: 0 30rpx;
	font-size: 28rpx;
	.item {
		display: flex;
		justify-content: space-between;
		padding: 30rpx 0;
		border-bottom: 1px solid #f4f6f8;
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
				margin: 10rpx 0;
				font-size: 24rpx;
				color: $u-tips-color;
			}
			.delivery-time {
				color: #e5d001;
				font-size: 24rpx;
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
}
</style>
