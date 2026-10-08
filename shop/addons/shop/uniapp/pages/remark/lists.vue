<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar title="评价列表" :border-bottom="false"></fa-navbar>
		<view class="comment u-border-bottom" v-for="(res, index) in list" :key="res.id">
			<view class="left"><image :src="res.user && res.user.avatar" mode="aspectFill"></image></view>
			<view class="right">
				<view class="top" :style="[{ color: theme.bgColor }]">
					<view class="name">{{ res.user && res.user.nickname }}</view>
					<view class="like highlight">
						<view class="num"><u-rate :count="5" :disabled="true" v-model="res.star"></u-rate></view>
					</view>
				</view>
				<view class="content">{{ res.content }}</view>
				<view class="images">
					<image class="thumb" @click="preview(res.images, key)" v-for="(img, key) in res.images" :key="key" :src="img" mode="aspectFill"></image>
				</view>

				<view class="reply-box">
					<view class="item" v-for="(item, index) in res.reply" :key="index">
						<view class="username">{{ item.manage && item.manage.nickname }}</view>
						<view class="text">{{ item.content }}</view>
					</view>
				</view>

				<view class="bottom u-flex u-row-between">
					<text>{{ res.createtime | timeFrom('yyyy-mm-dd') }}</text>
					<!-- <view class="" :style="[{ color: theme.bgColor }]" @click="(showReplay = true), (replyId = res.id)">
						<u-icon name="chat" :color="theme.bgColor"></u-icon>
						<text class="u-m-l-10">回复</text>
					</view> -->
				</view>
			</view>
		</view>
		<!-- 空数据 -->
		<view class="u-flex u-row-center fa-empty top-15" v-if="is_empty">
			<image src="../../static/image/data.png" mode=""></image>
			<view class="u-tips-color">暂无更多的评价数据~</view>
		</view>
		<!-- <fa-replys v-model="showReplay" :pid="replyId"></fa-replys> -->
		<!-- 加载更多 -->
		<view class="u-p-30" v-if="list.length"><u-loadmore bg-color="#ffffff" :status="has_more ? status : 'nomore'" /></view>
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
			list: [],
			status: 'loadmore',
			has_more: false,
			scrollTop: 0,
			page: 1,
			is_update: false,
			goods_id: 0,
			is_empty: false,
			showReplay: false,
			replyId: ''
		};
	},
	onLoad(e) {
		this.goods_id = e.goods_id || '';
		this.getCommentList();
	},
	methods: {
		// 跳转到全部回复
		toAllReply() {
			uni.$u.route({
				type:'to',
				url: '/pages/template/comment/reply'
			});
		},
		//评论列表
		getCommentList() {
			this.$api.commentList({ goods_id: this.goods_id, page: this.page }).then(res => {
				this.status = 'loadmore';
				if (res.code == 1) {
					this.list = [...this.list, ...res.data.data];
					this.has_more = res.data.current_page < res.data.last_page;
					this.is_empty = !this.list.length;
				}
			});
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
	//下拉刷新
	onPullDownRefresh() {},
	onReachBottom() {
		if (this.has_more) {
			this.status = 'loading';
			this.page++;
			this.getCommentList();
		}
	}
};
</script>

<style lang="scss" scoped>
.comment {
	display: flex;
	padding: 30rpx;
	.left {
		image {
			width: 64rpx;
			height: 64rpx;
			border-radius: 50%;
			background-color: #f2f2f2;
		}
	}
	.right {
		flex: 1;
		padding-left: 20rpx;
		font-size: 30rpx;
		.top {
			display: flex;
			justify-content: space-between;
			align-items: center;
			margin-bottom: 10rpx;
			.like {
				display: flex;
				align-items: center;
				font-size: 26rpx;
				.num {
					margin-right: 4rpx;
				}
			}
		}
		.content {
			margin-bottom: 10rpx;
		}
		.reply-box {
			background-color: rgb(242, 242, 242);
			border-radius: 12rpx;
			margin-top: 15rpx;
			.item {
				padding: 20rpx;
				font-size: 24rpx;
				&:not(:last-child){
					border-bottom: solid 2rpx $u-border-color;
				}
			}
			.all-reply {
				padding: 20rpx;
				display: flex;
				align-items: center;
				.more {
					margin-left: 6rpx;
				}
			}
		}
		.bottom {
			margin-top: 20rpx;
			display: flex;
			font-size: 24rpx;
			color: #9a9a9a;
		}
		.images {
			display: flex;
			flex-wrap: wrap;
			.thumb {
				width: 130rpx;
				height: 130rpx;
				margin: 15rpx 15rpx 0 0;
			}
		}
	}
}
</style>
