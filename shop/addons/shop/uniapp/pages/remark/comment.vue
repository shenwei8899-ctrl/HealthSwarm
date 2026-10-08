<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar title="我发表的评论"></fa-navbar>
		<view class="comment" v-for="(res, index) in commentList" :key="res.id">
			<view class="left" @click="goPage('/pages/goods/detail?id=' + res.goods_id)"><image :src="res.goods && res.goods.image" mode="aspectFill"></image></view>
			<view class="right">
				<view class="content u-line-2" @click="goPage('/pages/goods/detail?id=' + res.goods_id)">{{ res.goods && res.goods.title }}</view>
				<view class="reply-box">
					<view class="u-tips-color">
						评分:
						<u-rate :disabled="true" :current="res.star"></u-rate>
					</view>
					<view class="item u-m-t-10" @click="goPage('/pages/goods/detail?id=' + res.goods_id)">
						<view class="u-tips-color"><rich-text :nodes="res.content"></rich-text></view>
					</view>
					<view class="images" v-if="res.images && res.images.length">
						<image v-for="(img, idx) in res.images" :key="idx" @click="preview(res.images, idx)" :src="img" mode="aspectFill"></image>
					</view>
				</view>
			</view>
		</view>
		<!-- 回到顶部 -->
		<u-back-top :scroll-top="scrollTop" :icon-style="{ color: theme.bgColor }" :custom-style="{ backgroundColor: theme.lightColor }"></u-back-top>
		<!-- 为空 -->
		<view class="u-m-t-60 u-p-t-60 u-p-b-60" v-if="is_empty"><u-empty text="您还没有评论哦.." mode="list"></u-empty></view>
		<!-- 更多 -->
		<view class="u-p-t-30 u-p-b-30"><u-loadmore :status="has_more ? status : 'nomore'" /></view>
		<!-- 底部导航 -->
		<fa-tabbar></fa-tabbar>
	</view>
</template>

<script>
export default {
	onLoad() {
		this.getComment();
	},
	data() {
		return {
			isFirst:false,
			commentList: [],
			page: 1,
			has_more: false,
			status: 'loadmore',
			scrollTop: 0,
			is_empty: false,
			is_first:false
		};
	},
	onShow() {
		if(this.isFirst && !this.vuex_token){
			uni.$u.route({
				type:'back'
			})
			return;
		}
		this.isFirst = true;
	},
	onShow() {
		if(!this.vuex_token && this.is_first){
				uni.$u.route({
					type:'back'
				})
		}
		this.is_first = true;
	},
	methods: {
		// 评论列表
		getComment: async function() {
			let { code, data: res, msg } = await this.$api.commentMyList({ page: this.page });
			this.status = 'loadmore';
			if (!code) {
				this.$u.toast(msg);
				return;
			}
			this.commentList = this.commentList.concat(res.data);
			this.has_more = res.last_page > res.current_page;
			this.is_empty = !this.commentList.length;
		},
		preview(images, index) {
			uni.previewImage({
				urls: images,
				current: index,
				longPressActions: {
					itemList: ['发送给朋友', '保存图片', '收藏'],
					success: function(data) {
						console.log('选中了第' + (data.tapIndex + 1) + '个按钮,第' + (data.index + 1) + '张图片');
					},
					fail: function(err) {
						console.log(err.errMsg);
					}
				}
			});
		}
	},
	onPageScroll(e) {
		this.scrollTop = e.scrollTop;
	},
	//底部加载更多
	onReachBottom() {
		if (this.has_more) {
			this.status = 'loading';
			this.page++;
			this.getComment();
		}
	}
};
</script>

<style>
page {
	background-color: #ffffff;
}
</style>
<style lang="scss" scoped>
.comment {
	display: flex;
	padding: 30rpx;
	border-bottom: 1px solid #eee;
	.left {
		image {
			width: 180rpx;
			height: 130rpx;
			background-color: #f2f2f2;
			border-radius: 10rpx;
		}
	}
	.right {
		flex: 1;
		padding-left: 20rpx;
		font-size: 28rpx;

		.content {
			margin-bottom: 10rpx;
		}
		.reply-box {
			background-color: rgb(242, 242, 242);
			border-radius: 12rpx;
			padding: 20rpx;
			.item {
				word-break: break-word;
			}
			.images {
				display: flex;
				flex-wrap: wrap;
				margin-top: 10rpx;
				image {
					margin: 10rpx 10rpx 0 0;
					width: calc(100% / 3 - 10rpx);
					height: 150rpx;
					border-radius: 5rpx;
				}
			}
		}
	}
}
</style>
