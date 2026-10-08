<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar title="地址管理" :border-bottom="false"></fa-navbar>
		<u-swipe-action :show="item.show" :index="index" v-for="(item, index) in list" :key="item.id" @click="click"
			@open="open" :options="options">
			<view class="item u-border-bottom u-p-30" @click="select(item)">
				<view class="text-weight u-flex">
					<text v-text="item.receiver"></text>
					<text class="u-m-l-30" v-text="item.mobile"></text>
					<view class="u-m-l-30" v-if="item.isdefault">
						<u-tag size="mini" text="默认" type="success" />
					</view>
				</view>
				<view class="u-tips-color u-p-t-20">{{ item.address }}</view>
			</view>
		</u-swipe-action>
		<!-- 空数据 -->
		<view class="u-flex u-row-center fa-empty top-15" v-if="!list.length">
			<view class="u-flex u-row-center loading" v-if="is_loading">
				<u-loading mode="flower" size="80"></u-loading>
			</view>
			<view class="" v-else>
				<image src="../../static/image/data.png" mode=""></image>
				<view class="u-tips-color">请先添加地址吧~</view>
			</view>
		</view>
		<u-gap height="120" bg-color="#ffffff"></u-gap>
		<view class="footer-bar u-flex u-col-center u-row-center u-border-top">
			<u-button :custom-style="{ width: '80vw', backgroundColor: theme.bgColor, color: theme.color }"
				shape="circle" type="primary" hover-class="none" @click="goPage('/pages/address/addedit')">
				添加地址
			</u-button>
		</view>
		<!-- 底部导航 -->
		<fa-tabbar></fa-tabbar>
	</view>
</template>

<script>
	export default {
		onLoad(e) {
			this.type = e.type || '';
		},
		onShow() {
			this.options = [{
					text: '编辑',
					style: {
						backgroundColor: this.theme.bgColor
					}
				},
				{
					text: '删除',
					style: {
						backgroundColor: '#dd524d'
					}
				}
			];
			if (this.isFirst && !this.vuex_token) {
				uni.$u.route({
					type: 'back',
					delta: 1
				})
				return;
			}
			this.isFirst = true;
			this.getAddressList();
		},
		data() {
			return {
				isFirst: false,
				list: [],
				disabled: false,
				btnWidth: 180,
				show: false,
				options: [],
				is_loading: true
			};
		},
		methods: {
			click(index, index1) {
				if (index1 == 1) {
					//删除
					this.$api.delAddress({
						id: this.list[index].id
					}).then(res => {
						this.$u.toast(res.msg);
						if (res.code) {
							if (this.vuex_address.id && this.vuex_address.id == this.list[index].id) {
								this.$u.vuex('vuex_address', {});
							}
							this.list.splice(index, 1);

						}
					});
				} else {
					//编辑
					this.goPage('/pages/address/addedit?id=' + this.list[index].id);
				}
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
			getAddressList() {
				this.$api.addressList({
					page: this.page
				}).then(res => {
					if (res.code) {
						this.list = res.data;
					}
					this.is_loading = false;
				});
			},
			//选择地址
			select(item) {
				if (this.type == 'select') {
					this.$u.vuex('vuex_address', item);
					uni.$u.route({
						type: 'back'
					});
				}
			}
		}
	};
</script>

<style lang="scss" scoped>
	.fa-empty {
		.loading {
			padding-top: 10vh;
		}
	}
</style>
