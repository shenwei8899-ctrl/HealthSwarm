<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar title="帮助中心" :border-bottom="false"></fa-navbar>
		<u-cell-group>
			<u-cell-item
				v-for="(item, index) in list"
				:key="index"
				:title="index+1+'、'+item.title"
				:label="item.description"
				:border-bottom="false"
				:border-top="index>0"
				@click="goPage('/pages/page/page?id=' + item.id)"
			></u-cell-item>
		</u-cell-group>
		<!-- 空数据 -->
		<view class="u-flex u-row-center fa-empty top-15" v-if="!list.length">
			<image src="../../static/image/data.png" mode=""></image>
			<view class="u-tips-color">暂无更多的数据~</view>
		</view>
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
	onLoad() {
		this.getPageList();
	},
	data() {
		return {
			scrollTop: 0,
			has_more: false,
			status: 'loadmore',
			is_update: false,
			page: 1,
			list: []
		};
	},
	methods: {
		getPageList() {
			this.$api.pageList({ page: this.page, type: 'help' }).then(({ code, data: res, msg }) => {
				if (code) {
					this.list = [...this.list, ...res.data];
					this.has_more = res.current_page < res.last_page;
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
			this.getPageList();
		}
	}
};
</script>

<style></style>
