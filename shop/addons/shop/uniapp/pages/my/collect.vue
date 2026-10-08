<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar title="收藏列表" :border-bottom="false"></fa-navbar>

		<view class="bg-white u-m-b-30">
			<u-swipe-action :show="item.show" :index="index" v-for="(item, index) in list" :key="index" @click="click" @open="open" :options="options">
				<view class="thumb-box u-p-l-30 u-p-r-30" @click="goPage('/pages/goods/detail?id=' + item.goods_id)">
					<image class="item-menu-image" :src="item.goods.image" mode="aspectFill"></image>
					<view class="u-p-l-15 u-flex-1 right">
						<view class="item-menu-name u-line-2 u-font-28">{{ item.goods.title }}</view>
						<view class="u-tips-color intro u-line-1">{{ item.goods.description }}</view>
						<view class="u-flex u-row-between">
							<text class="market_price u-tips-color">￥{{ item.goods.marketprice }}</text>
							<text class="price">￥{{ item.goods.price }}</text>
						</view>
					</view>
				</view>
			</u-swipe-action>
		</view>
		<!-- 空数据 -->
		<view class="u-flex u-row-center fa-empty top-15" v-if="is_empty">
			<image src="../../static/image/collect.png" mode=""></image>
			<view class="u-tips-color">没有更多的收藏数据了~</view>
		</view>
		<!-- 加载更多 -->
		<view class="u-p-b-30" v-if="list.length"><u-loadmore bg-color="#f4f6f8" :status="has_more ? status : 'nomore'" /></view>
		<!-- 回到顶部 -->
		<u-back-top :scroll-top="scrollTop" :icon-style="{ color: theme.bgColor }" :custom-style="{ backgroundColor: theme.lightColor }"></u-back-top>
		<!-- 底部导航 -->
		<fa-tabbar></fa-tabbar>
	</view>
</template>

<script>
export default {
	onLoad() {
		this.collectList();
	},
	onShow() {
		if (this.isFirst && !this.vuex_token) {
			uni.$u.route({
				type:'back'
			});
			return;
		}
		this.isFirst = true;
	},
	data() {
		return {
			isFirst:false,
			status: 'loadmore',
			has_more: false,
			scrollTop: 0,
			is_update: false,
			is_empty: false,
			page: 1,
			show: false,
			list: [],
			options: [
				{
					text: '移除',
					style: {
						backgroundColor: '#dd524d'
					}
				}
			]
		};
	},
	methods: {
		collectList() {
			this.$api.collectList({ page: this.page }).then(result => {
				this.status = 'loadmore';
				let { code, data: res, msg } = result;
				if (code == 1) {
					if (this.is_update) {
						this.list = [];
						this.is_update = false;
					}
					res.data.map(item => {
						item.show = false;
					});
					this.list = [...this.list, ...res.data];
					this.has_more = res.current_page < res.last_page;
					this.is_empty = !this.list.length;
				}
			});
		},
		click(index) {
			this.collect(this.list[index].goods_id);
		},
		// 如果打开一个的时候，不需要关闭其他，则无需实现本方法
		open(index) {
			// 先将正在被操作的swipeAction标记为打开状态，否则由于props的特性限制，
			// 原本为'false'，再次设置为'false'会无效
			this.list[index].show = true;
			this.list.map((val, idx) => {
				if (index != idx) this.list[idx].show = false;
			});
		},
		collect(id) {
			this.$api.optionCollect({ goods_id: id }).then(res => {
				if (res.code) {
					this.$u.toast('取消收藏成功');
					this.is_update = true;
					this.page = 1;
					this.collectList();
				} else {
					this.$u.toast(res.msg);
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
			this.page = this.page + 1;
			this.collectList();
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
.hoter-list {
	border-radius: 10rpx;
	.item {
		position: relative;
		.collect {
			background: rgba($color: #000000, $alpha: 0.2);
			border-radius: 200rpx;
			position: absolute;
			right: 30rpx;
			top: 20rpx;
			padding: 10rpx;
			z-index: 9999;
		}
		.images {
			position: relative;
			.title {
				color: #ffffff;
				width: 100%;
				position: absolute;
				left: 0rpx;
				bottom: 0rpx;
				padding: 20rpx 10rpx;
				background: rgba($color: #000000, $alpha: 0.4);
			}
		}

		.price {
			font-weight: bold;
		}
		.market_price {
			text-decoration: line-through;
			margin-left: 10rpx;
		}
	}
}

.thumb-box {
	width: 100%;
	display: flex;
	align-items: center;
	padding: 30rpx 0;

	.item-menu-image {
		width: 200rpx;
		height: 150rpx;
		border-radius: 5rpx;
	}
	.right {
		width: 500rpx;
		height: 150rpx;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
	}
	.item-menu-name {
		font-weight: normal;
		color: $u-main-color;
	}
	.intro {
		font-size: 20rpx;
		padding: 10rpx 0;
	}
	.market_price {
		text-decoration: line-through;
	}
	&:not(:last-child) {
		border-bottom: 1px solid #f4f6f8;
	}
}
</style>
