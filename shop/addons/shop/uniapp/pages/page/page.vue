<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar :title="info.title || '单页'" :border-bottom="false"></fa-navbar>
		<image class="page-imgae" v-if="info.image" :src="info.image" mode="aspectFill"></image>

		<view class="text-weight u-font-30 u-border-bottom u-p-30"><text v-text="info.title"></text></view>
		<!-- <view class="">
				<text v-text="info.views"></text>
			</view> -->
		<view class="u-p-30">
			<u-parse
				:html="info.content"
				:tag-style="vuex_parse_style"
				:domain="vuex_config && vuex_config.upload && vuex_config.upload.cdnurl ? vuex_config.upload.cdnurl : ''"
				@linkpress="diylinkpress"
			></u-parse>
		</view>
	</view>
</template>

<script>
export default {
	onLoad(e) {
		this.id = e.id || '';
		this.diyname = e.diyname || '';
		this.getPageIndex();
	},
	data() {
		return {
			id: '',
			diyname: '',
			info: {}
		};
	},
	methods: {
		getPageIndex() {
			this.$api
				.pageIndex({
					id: this.id,
					diyname: this.diyname
				})
				.then(res => {
					if (res.code) {
						this.info = res.data;
					} else {
						this.$u.toast(res.msg);
						setTimeout(() => {
								uni.$u.route({
									type:'back'
								})
						}, 1500);
					}
				});
		}		
	}
};
</script>

<style lang="scss" scoped>
.page-imgae {
	height: 400rpx;
	width: 100%;
}
</style>
