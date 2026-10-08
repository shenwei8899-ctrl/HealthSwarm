<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar title="商品列表" :border-bottom="false"></fa-navbar>
		<view class="u-p-20 bg-white">
			<fa-orderby-select :category-id="category_id" @change="change"></fa-orderby-select>				
		</view>
		<view class="goods-list">
			<view class="item" v-for="(item, index) in goods" :key="index" @click="goPage('/pages/goods/detail?id=' + item.id)">
				<view class="images"><image :src="item.image || vuex_config.default_goods_img" mode="aspectFill"></image></view>
				<view class="u-p-15 name">
					<text class="u-line-2">{{ item.title }}</text>
				</view>
				<view class="foot u-flex u-row-between u-tips-color">
					<view class="">
						<text class="u-m-r-10">销量</text>
						<text>{{ item.sales }}</text>
					</view>
					<view class="">
						<text class="u-m-r-10">浏览</text>
						<text>{{ item.views || 0 }}</text>
					</view>
				</view>
				<view class="u-flex u-row-between u-p-15">
					<view class="price">
						<text>￥{{ item.price }}</text>
					</view>
					<text class="market_price u-tips-color">￥{{ item.marketprice }}</text>
					<!-- <u-button size="mini" shape="circle">立即购买</u-button> -->
				</view>
			</view>
			<!-- 空数据 -->
			<view class="u-flex u-row-center fa-empty top-15" v-if="!goods.length">
				<image src="../../static/image/data.png" mode=""></image>
				<view class="u-tips-color">暂无更多的商品数据~</view>
			</view>
		</view>
		<!-- 加载更多 -->
		<view class="u-p-b-30" v-if="goods.length"><u-loadmore bg-color="#f4f6f8" :status="has_more ? status : 'nomore'" /></view>
		<!-- 回到顶部 -->
		<u-back-top :scroll-top="scrollTop" :icon-style="{ color: theme.bgColor }" :custom-style="{ backgroundColor: theme.lightColor }"></u-back-top>
		<!-- 底部导航 -->
		<fa-tabbar></fa-tabbar>
	</view>
</template>

<script>
export default {
	onLoad(e) {
		this.category_id = e.category_id || '';
		this.keyword = e.keyword || '';
		this.getGoods();
	},
	data() {
		return {
			category_id: '',
			goods: [],
			scrollTop: 0,
			status: 'loadmore',
			is_update: false,
			has_more: false,
			page: 1,
			keyword: '',
			query:{}
		};
	},
	methods: {
		search(e) {
			this.page = 1;
			this.is_update = true;
			this.keyword = e;
			this.getGoods();
		},
		change(query){					
			this.query = query;
			this.page = 1;
			this.is_update = true;
			this.getGoods();
		},
		getGoods() {
			this.$api.getGoodsList({ category_id: this.category_id, page: this.page, keyword: this.keyword,...this.query }).then(res => {
				if (res.code == 1) {
					if (this.is_update) {
						this.goods = [];
						this.is_update = false;
					}
					this.goods = [...this.goods, ...res.data.data];
					this.has_more = res.data.current_page < res.data.last_page;
				}
			});
		}
	},
	onPageScroll(e) {
		this.scrollTop = e.scrollTop;
	},
	onReachBottom() {
		if (this.has_more) {
			this.status = 'loading';
			this.page++;
			this.getGoods();
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
.goods-list {
	display: flex;
	flex-wrap: wrap;
	justify-content: space-between;
	padding: 30rpx;
	.item {
		width: calc((100vw - 90rpx) / 2);
		background-color: #ffffff;
		box-shadow: 0px 0px 5px rgb(233, 235, 243);
		margin-bottom: 30rpx;
		border-radius: 10rpx;
		overflow: hidden;
		.name {
			min-height: 110rpx;
		}
		.foot {
			padding: 0 15rpx;
		}
		.images {
			width: 100%;
			height: 350rpx;
			image {
				width: 100%;
				height: 100%;
			}
		}
		.market_price {
			text-decoration: line-through;
			margin-left: 10rpx;
		}
	}
}
</style>
