<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar title="首页" :border-bottom="false"></fa-navbar>
		<view class="u-p-l-20 u-p-r-20 u-p-b-20" :style="[{backgroundColor:theme.bgColor}]">
			<fa-search :mode="2" :no-focus="true" @focus="goPage('/pages/search/search')"></fa-search>
		</view>
		
		<view class="u-p-t-30 u-p-b-30">
			<u-swiper :effect3d="true" :list="vuex_config.swiper" border-radius="15" :title="true" :height="350" @click="openPage"></u-swiper>
		</view>

		<view class="notice bg-white" v-if="notice.length">
			<u-notice-bar mode="horizontal" type="warning" :duration="5000" :is-circular="false" :autoplay="true" :list="notice" @click="click"></u-notice-bar>
		</view>

		<view v-if="navigates">
			<swiper class="swiper" @change="change" :style="{ height: (vuex_config.navigate && vuex_config.navigate.length > 6 ? 580 : 360) + 'rpx' }">
				<swiper-item v-for="(res, key) in navigateList" :key="key">
					<u-grid :col="3" hover-class="hover-class">
						<u-grid-item v-for="(item, index) in res" :custom-style="{ padding: '35rpx 0' }" @click="grids(item)" :key="index">
							<u-icon :name="item.image" color="#909399" :size="item.size"></u-icon>
							<view class="u-m-t-20">{{ item.name }}</view>
						</u-grid-item>
					</u-grid>
				</swiper-item>
			</swiper>
			<view class="indicator-dots" v-if="navigateList.length > 1">
				<view class="indicator-dots-item" v-for="(res, key) in navigateList" :key="key" :class="[current == key ? 'indicator-dots-active' : '']"></view>
			</view>
		</view>
		<view class="index-content">
			<view class="u-font-30 title">
				<text class="stroke"></text>
				热门商品
			</view>
			<view class="hots-list">
				<view class="item" v-for="(item, index) in hots" :key="index" @click="goPage('/pages/goods/detail?id=' + item.id)">
					<view class="images"><image :src="item.image" mode="aspectFill"></image></view>
					<view class="content">
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
						</view>
					</view>
				</view>
				<!-- 空数据 -->
				<view class="u-flex u-row-center fa-empty u-p-b-60" v-if="!hots.length">
					<image src="../../static/image/data.png" mode=""></image>
					<view class="u-tips-color">暂无更多的热门商品~</view>
				</view>
			</view>			
		</view>
		<view class="index-content">
			<view class="u-font-30 title">
				<text class="stroke"></text>
				推荐商品
			</view>
			<view class="goods-list">
				<view class="item" v-for="(item, index) in recommends" :key="index" @click="goPage('/pages/goods/detail?id=' + item.id)">
					<view class="images"><image :src="item.image" mode="aspectFill"></image></view>
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
					</view>
				</view>
				<!-- 空数据 -->
				<view class="u-flex u-row-center fa-empty u-p-b-60" v-if="!recommends.length">
					<image src="../../static/image/data.png" mode=""></image>
					<view class="u-tips-color">暂无更多的推荐商品~</view>
				</view>
			</view>
			<!-- 加载更多 -->
			<view class="u-p-b-30" v-if="recommends.length"><u-loadmore :status="has_more ? status : 'nomore'" /></view>
		</view>
		<!-- 回到顶部 -->
		<u-back-top :scroll-top="scrollTop" :icon-style="{ color: theme.bgColor }" :custom-style="{ backgroundColor: theme.lightColor }"></u-back-top>
		<!-- 底部导航 -->
		<fa-tabbar></fa-tabbar>
	</view>
</template>

<script>
export default {
	data() {
		return {
			loading: true,
			status: 'loadmore',
			is_update: false,
			has_more: false,
			current: 0,
			scrollTop: 0,
			navigateList: [],
			hots: [],
			recommends: []
		};
	},
	onShow() {
		this.getGoodsIndex();
	},
	computed: {
		notice() {
			let arr = [];
			if (this.vuex_config.notice) {
				this.vuex_config.notice.map(item => {
					arr.push(item.title);
				});
			}
			return arr;
		},
		navigates() {
			if (this.vuex_config.navigate) {
				let arr1 = [],
					arr2 = [];
				this.vuex_config.navigate.forEach((item, index) => {
					if (((index + 1) % 9 == 0 && index != 0) || index + 1 == this.vuex_config.navigate.length) {
						arr2.push(item);
						arr1.push(arr2);
						arr2 = [];
					} else {
						arr2.push(item);
					}
				});
				
				this.navigateList = arr1;
			}
			return 1;
		}
	},
	methods: {
		change(e) {
			this.current = e.detail.current;
		},
		grids(e) {
			let path = e.path;
			if (path == '/' || !path) {
				return;
			}
			if (path.substr(0, 1) == 'p') {
				path = '/' + path;
			}
			if (path.includes('http')) {
				this.$u.vuex('vuex_webs', {
					path: e.path,
					title: e.name
				});
				this.$u.route('/pages/webview/webview');
				return;
			}
			this.$u.route(path);
		},
		openPage(index) {
			this.grids({
				path: this.vuex_config.swiper[index].url,
				name: this.vuex_config.swiper[index].title
			});
		},
		click(index) {
			if (this.vuex_config.notice) {
				let url = this.vuex_config.notice[index].path;
				if (url) {
					this.grids({
						path: url,
						name: this.vuex_config.notice[index].title
					});
				}
			}
		},
		getGoodsIndex() {
			this.$api.getGoodsIndex().then(({code,data:res,msg}) => {
				if (code) {
					this.hots = res.hots;
					this.recommends = res.recommends;
				}
			});
		}
	},
	onPageScroll(e) {
		this.scrollTop = e.scrollTop;
	},
	//下拉刷新
	onPullDownRefresh() {},
	onReachBottom() {}
};
</script>

<style lang="scss">
page {
	background-color: #f4f6f8;
}
</style>
<style lang="scss" scoped>
.indicator-dots {
	display: flex;
	justify-content: center;
	align-items: center;
}

.indicator-dots-item {
	background-color: $u-tips-color;
	height: 6px;
	width: 6px;
	border-radius: 10px;
	margin: 0 3px;
}

.indicator-dots-active {
	background-color: $u-type-primary;
}
.notice {
	margin-bottom: 30rpx;
}
.index-content {
	margin-top: 30rpx;
	background-color: #ffffff;
	.title {
		position: relative;
		padding: 30rpx 50rpx;
		border-bottom: 1px solid #f4f6f8;
		.stroke {
			&::before {
				content: '';
				width: 8rpx;
				height: 30rpx;
				background-color: #374486;
				position: absolute;
				top: 36%;
				left: 30rpx;
				border-radius: 20rpx;
			}
		}
	}
}

.goods-list {
	display: flex;
	flex-wrap: wrap;
	justify-content: space-between;
	margin-top: 30rpx;
	padding: 0 30rpx;
	.item {
		width: calc((100vw - 90rpx) / 2);
		background-color: #ffffff;
		box-shadow: 0px 0px 5px rgb(233, 235, 243);
		margin-bottom: 30rpx;
		border-radius: 10rpx;
		overflow: hidden;
		border: 1px solid #e9ebf3;
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
.hots-list{	
	margin-top: 30rpx;
	padding: 0 30rpx 30rpx;
	.item {
		width: 100%;
		background-color: #ffffff;
		box-shadow: 0px 0px 5px rgb(233, 235, 243);
		margin-bottom: 30rpx;
		border-radius: 10rpx;
		overflow: hidden;
		border: 1px solid #e9ebf3;
		display: flex;
		justify-content: space-between;
		align-items: center;
		.images {
			width: 250rpx;
			height: 220rpx;
			image {
				width: 100%;
				height: 100%;
			}
		}
		.content{
			flex: 1;
			.name {
				min-height: 110rpx;
			}
			.foot {
				padding: 0 15rpx;
			}
			.market_price {
				text-decoration: line-through;
				margin-left: 10rpx;
			}
		}
	}
}
</style>
