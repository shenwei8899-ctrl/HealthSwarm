<template>
	<view class="u-wrap" :style="[height]">
		<view class="u-menu-wrap">
			<scroll-view scroll-y scroll-with-animation class="u-tab-view menu-scroll-view" :scroll-top="scrollTop">
				<view
					v-for="(item, index) in category"
					:key="index"
					class="u-tab-item"
					:class="[current == index ? 'u-tab-item-active' : '']"
					:data-current="index"
					@tap.stop="swichMenu(item, index)"
				>
					<text class="u-line-1">{{ item.name }}</text>
				</view>
			</scroll-view>

			<scroll-view scroll-y class="right-box" v-if="row.id">
				<view class="page-view">
					<view class="class-item">
						<view class="item-title u-flex u-row-between">
							<text>{{ row.name }}</text>
							<view class="" @click="goPage('/pages/goods/goods?category_id=' + row.id)">
								<text class="u-tips-color">更多</text>
								<u-icon name="arrow-right-double" color="#999" size="28"></u-icon>
							</view>
						</view>
						<view class="item-container">
							<view class="thumb-box" v-for="(item1, index1) in row.goods" :key="index1" @click="goPage('/pages/goods/detail?id=' + item1.id)">
								<image class="item-menu-image" :src="item1.image" mode="aspectFill"></image>
								<view class="u-p-l-15 u-flex-1 goods">
									<view class="item-menu-name u-line-2 u-font-28" v-text="item1.title"></view>
									<view class="u-tips-color intro u-line-1">{{ item1.description || '' }}</view>
									<view class="u-flex u-row-between">
										<text class="market_price u-tips-color">￥{{ item1.marketprice || 0 }}</text>
										<text class="price">￥{{ item1.price || 0 }}</text>
									</view>
								</view>
							</view>
							<view class="u-flex fa-empty top-15" v-if="!row.goods.length">
								<image src="../../static/image/data.png" mode=""></image>
								<view class="u-tips-color">暂无更多的商品数据~</view>
							</view>
						</view>
					</view>
				</view>
			</scroll-view>
		</view>
	</view>
</template>

<script>
export default {
	name: 'fa-category',
	props: {
		height: {
			type: Object,
			default() {
				return {};
			}
		}
	},
	mounted() {
		this.current = this.vuex_current;
		this.getCategory();
	},
	data() {
		return {
			category: [],
			row: {}, //当前选择的分类
			scrollTop: 0, //tab标题的滚动条位置
			current: 0, // 预设当前项的值
			menuHeight: 0, // 左边菜单的高度
			menuItemHeight: 0, // 左边菜单item的高度
		};
	},
	methods: {
		// 点击左边的栏目切换
		async swichMenu(item, index) {
			if (index == this.current) return;
			this.row = item;
			this.current = index;
			this.$u.vuex('vuex_current',index);
			// 如果为0，意味着尚未初始化
			if (this.menuHeight == 0 || this.menuItemHeight == 0) {
				await this.getElRect('menu-scroll-view', 'menuHeight');
				await this.getElRect('u-tab-item', 'menuItemHeight');
			}
			// 将菜单菜单活动item垂直居中
			this.scrollTop = index * this.menuItemHeight + this.menuItemHeight / 2 - this.menuHeight / 2;
		},
		// 获取一个目标元素的高度
		getElRect(elClass, dataVal) {
			new Promise((resolve, reject) => {
				const query = uni.createSelectorQuery().in(this);
				query
					.select('.' + elClass)
					.fields({ size: true }, res => {
						// 如果节点尚未生成，res值为null，循环调用执行
						if (!res) {
							setTimeout(() => {
								this.getElRect(elClass);
							}, 10);
							return;
						}
						this[dataVal] = res.height;
					})
					.exec();
			});
		},
		getCategory() {
			this.$api.getCategory({ category_mode: 1 }).then(res => {
				if (res.code == 1) {
					this.category = res.data;
					if (res.data.length > 0) {
						this.row = res.data[this.current]==undefined?res.data[0]:res.data[this.current]; //默认取第一个
					}
				}
			});
		}
	}
};
</script>

<style lang="scss" scoped>
.u-wrap {
	display: flex;
	flex-direction: column;
}

.u-menu-wrap {
	flex: 1;
	display: flex;
	overflow: hidden;
}

.u-tab-view {
	width: 200rpx;
	height: 100%;
	background-color: #f6f6f6;
}

.u-tab-item {
	height: 110rpx;
	box-sizing: border-box;
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 26rpx;
	color: #444;
	font-weight: 400;
	line-height: 1;
}

.u-tab-item-active {
	position: relative;
	color: #000;
	font-size: 30rpx;
	font-weight: 600;
	background: #fff;
}

.u-tab-item-active::before {
	content: '';
	position: absolute;
	border-left: 4px solid #374486;
	height: 32rpx;
	left: 0;
	top: 39rpx;
}

.u-tab-view {
	height: 100%;
}

.right-box {
	background-color: rgb(250, 250, 250);
	width: 100%;
}

.page-view {
	background-color: #fff;
	padding: 16rpx;
	height: 100%;
	position: relative;
}

.class-item {
	padding: 16rpx;
	border-radius: 8rpx;
	height: 100%;
}

.item-title {
	font-size: 26rpx;
	color: $u-main-color;
	font-weight: bold;
}

.item-container {
	display: flex;
	flex-wrap: wrap;
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
		.item-menu-name {
			font-weight: normal;
			color: $u-main-color;
			width: 320rpx;
		}
		.intro {
			width: 320rpx;
			font-size: 20rpx;
			padding: 10rpx 0;
		}
		.market_price {
			text-decoration: line-through;
		}
		&:not(:last-child) {
			border-bottom: 1px solid #f4f6f8;
		}
		.goods {
			display: flex;
			flex-direction: column;
			justify-content: space-between;
			height: 150rpx;
		}
	}
}
</style>
