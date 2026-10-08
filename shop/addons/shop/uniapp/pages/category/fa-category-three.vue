<template>
	<view class="u-wrap" :style="[height]">
		<view class="u-menu-wrap">
			<scroll-view scroll-y scroll-with-animation class="u-tab-view menu-scroll-view" :scroll-top="scrollTop" :scroll-into-view="itemId">
				<view
					v-for="(item, index) in category"
					:key="index"
					class="u-tab-item"
					:class="[current == index ? 'u-tab-item-active' : '']"
					@tap.stop="swichMenu(index)"
				>
					<text class="u-line-1">{{ item.name }}</text>
				</view>
			</scroll-view>
			<scroll-view :scroll-top="scrollRightTop" scroll-y scroll-with-animation class="right-box" @scroll="rightScroll">
				<view class="page-view">
					<view class="class-item" :id="'item' + index" v-for="(item, index) in row.childlist" :key="index">
						<view class="item-title">
							<text>{{ item.name }}</text>
						</view>
						<view class="item-container">
							<view
								class="thumb-box"
								v-for="(item1, index1) in item.childlist"
								:key="index1"
								@click="goPage('/pages/goods/goods?category_id=' + item1.id)"
							>
								<image class="item-menu-image" :src="item1.image || vuex_config.default_category_img" mode="aspectFill"></image>
								<view class="item-menu-name">{{ item1.name }}</view>
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
	name: 'fa-category-three',
	props: {
		height: {
			type: Object,
			default() {
				return {};
			}
		}
	},
	data() {
		return {
			scrollTop: 0, //tab标题的滚动条位置
			current: 0, // 预设当前项的值
			itemId: '', // 栏目右边scroll-view用于滚动的id
			category: [],
			row: {},
			scrollRightTop: 0 // 右边栏目scroll-view的滚动条高度
		};
	},
	mounted() {
		this.getCategory();
	},
	methods: {
		// 点击左边的栏目切换
		async swichMenu(index) {
			if (index == this.current) return;
			this.row = this.category[index];
			this.current = index;
		},
		getCategory() {
			this.$api.getCategory().then(res => {
				if (res.code == 1) {
					this.category = res.data;
					if (res.data.length) {
						this.row = res.data[0];
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
	background: #f6f6f6;
	width: 200rpx;
	height: 100%;
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
}

.page-view {
	padding: 16rpx;
}

.class-item {
	margin-bottom: 30rpx;
	background-color: #fff;
	padding: 16rpx;
	border-radius: 8rpx;
}

.class-item:last-child {
	min-height: 30vh;
}

.item-title {
	font-size: 26rpx;
	color: $u-main-color;
	font-weight: bold;
}

.item-menu-name {
	margin-top: 15rpx;
	font-weight: normal;
	font-size: 24rpx;
	color: $u-main-color;
}

.item-container {
	display: flex;
	flex-wrap: wrap;
}

.thumb-box {
	width: 33.333333%;
	display: flex;
	align-items: center;
	justify-content: center;
	flex-direction: column;
	margin-top: 20rpx;
}

.item-menu-image {
	width: 120rpx;
	height: 120rpx;
	border-radius: 5rpx;
}
</style>
