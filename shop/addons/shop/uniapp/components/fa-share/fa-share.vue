<template>
	<view>
		<u-popup v-model="value" :popup="false" mode="bottom" @close="hide" @open="open">
			<!-- #ifndef MP-WEIXIN -->
			<u-grid :col="3" :border="false">
				<u-grid-item v-for="(item, index) in list" :key="index" @click="share(index, item)">
					<u-icon :name="item.icon" :color="item.color" :size="item.size"></u-icon>
					<view class="grid-text u-m-t-10" v-text="item.name"></view>
				</u-grid-item>
			</u-grid>
			<!-- #endif -->
			<!-- #ifdef MP-WEIXIN -->
			<u-grid :col="3" :border="false">
				<u-grid-item v-for="(item, index) in list" :key="index" @click="share(index, item)">
					<button class="u-text-center share-btn" :open-type="index==1?'share':''">
						<u-icon :name="item.icon" :color="item.color" :size="item.size"></u-icon>
						<view class="grid-text u-m-t-10" v-text="item.name"></view>
					</button>
				</u-grid-item>
			</u-grid>
			<!-- #endif -->
			<u-gap height="3" bg-color="rgb(244, 246, 248)"></u-gap>
			<view class="u-text-center u-p-30" @click="hide">取消</view>
		</u-popup>
	</view>
</template>

<script>
	import {
		isWeiXinBrowser
	} from '@/common/util.js';
	export default {
		name: 'fa-app-share',
		props: {
			value: {
				type: Boolean,
				default: false
			},
			goodsId: {
				type: [Number, String],
				default: ''
			},
			title: {
				type: String,
				default: ''
			},
			summary: {
				type: String,
				default: ''
			},
			href: {
				type: String,
				default: ''
			},
			imageUrl: {
				type: String,
				default: ''
			}
		},
		data() {
			let list = [];

			// #ifdef H5
			list = list.concat([
				// {
				// 	name: '生成海报',
				// 	icon: 'photo',
				// 	size: 60,
				// 	color: '#2979ff',
				// 	type: 0, //图文
				// 	provider: 'poster'
				// },
				{
					name: '复制链接',
					icon: 'attach',
					size: 60,
					color: '#44b549',
					type: 0, //图文
					provider: 'copylink'
				}
			]);
			// #endif

			// #ifdef MP-WEIXIN
			list = [{
					name: '生成海报',
					icon: 'photo',
					size: 60,
					color: '#2979ff',
					type: 0, //图文
					provider: 'weixin'
				},
				{
					name: '分享好友',
					icon: 'weixin-circle-fill',
					size: 60,
					color: '#44b549',
					type: 0, //图文
					provider: 'weixin'
				}
			];
			// #endif

			// #ifdef APP-PLUS
			list = [{
					name: '微信好友',
					icon: 'weixin-circle-fill',
					size: 60,
					color: '#44b549',
					type: 0, //图文
					provider: 'weixin'
				},
				{
					name: '微信朋友圈',
					icon: 'moments-circel-fill',
					size: 60,
					color: '#44b549',
					type: 0, //图文
					provider: 'weixin'
				},
				{
					name: '微信收藏',
					icon: 'star-fill',
					size: 60,
					color: '#ff9100',
					type: 0, //图文
					provider: 'weixin'
				},
				{
					name: 'QQ好友',
					icon: 'qq-circle-fill',
					size: 60,
					color: '#388BFF',
					type: 2, //图
					provider: 'qq'
				},
				{
					name: '新浪微博',
					icon: 'weibo-circle-fill',
					size: 60,
					color: '#BE3E3F',
					type: 0, //图文
					provider: 'sinaweibo	'
				}
			];
			// #endif
			return {
				list: list
			};
		},
		methods: {
			open(){
				// #ifdef H5
				if(isWeiXinBrowser()){
					this.$u.toast('请点击右上角的•••进行分享');
				}
				// #endif
			},
			hide() {
				this.$emit('input', false);
			},
			// #ifdef H5
			share(index, item) {
				if (item.provider === 'poster') {
					this.$emit('shares')
					return;
				} else if (item.provider === 'copylink') {
					this.$util.uniCopy({
						content: window.location.href,
						success: () => {
							this.$u.toast('复制成功，请去粘贴发送给好友吧');
							this.hide()
						},
						error: () => {
							console.error('复制失败！');
						}
					});
				}
			},
			// #endif

			// #ifdef MP-WEIXIN
			share(index, item) {
				if (!index) {
					this.$emit('shares')
					return;
				}
			},
			// #endif

			// #ifdef APP-PLUS
			share(index, item) {
				let data = {
					provider: item.provider,
					type: item.type,
					href: this.href,
					title: this.title,
					summary: this.summary,
					imageUrl: this.imageUrl,
					success: res => {
						this.hide();
						this.$u.toast('分享成功！');
					},
					fail: err => {
						console.log(JSON.stringify(err));
						this.$u.toast('分享失败！');
					}
				};
				if (index == 0) {
					data.scene = 'WXSceneSession';
				}
				if (index == 1) {
					data.scene = 'WXSenceTimeline';
				}
				if (index == 2) {
					data.scene = 'WXSceneFavorite';
				}
				console.log(JSON.stringify(data));
				uni.share(data);
			}
			// #endif
		}
	};
</script>

<style lang="scss" scoped>

</style>