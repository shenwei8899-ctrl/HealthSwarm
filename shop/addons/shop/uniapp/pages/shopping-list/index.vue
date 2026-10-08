<template>
	<view class="shopping-list-page">
		<fa-navbar :title="listId ? '购物清单详情' : '营养购物清单'" :border-bottom="false"></fa-navbar>

		<view v-if="!listId" class="list-page">
			<view class="list-summary" v-if="lists.length">
				<text>共 {{ pagination.total || lists.length }} 份清单</text>
				<text class="summary-note">按菜单版本生成</text>
			</view>
			<view class="list-card" v-for="item in lists" :key="item.id" @click="openList(item.id)">
				<view class="u-flex u-row-between">
					<view class="list-name">菜单购物清单 V{{ item.list_version }}</view>
					<u-tag :text="statusText(item.status)" :type="statusType(item.status)" mode="plain" size="mini"></u-tag>
				</view>
				<view class="list-sn u-line-1">{{ item.list_sn }}</view>
				<view class="list-stats u-flex">
					<text>{{ item.item_count }} 种食材</text>
					<text>{{ item.platform_item_count }} 项平台购买</text>
					<text v-if="item.unmatched_item_count" class="warning">{{ item.unmatched_item_count }} 项待处理</text>
				</view>
				<view class="list-time">{{ item.updatetime | date('yyyy-mm-dd hh:MM') }}</view>
			</view>
			<view class="empty-state" v-if="!loading && !lists.length">
				<u-empty text="暂无购物清单" mode="list"></u-empty>
			</view>
		</view>

		<view v-else-if="detail.id" class="detail-page">
			<view class="detail-header">
				<view class="u-flex u-row-between">
					<view class="detail-title">菜单购物清单 V{{ detail.list_version }}</view>
					<u-tag :text="statusText(detail.status)" :type="statusType(detail.status)" mode="plain" size="mini"></u-tag>
				</view>
				<view class="detail-meta">{{ detail.items.length }} 种食材 · {{ platformItemCount }} 项平台购买</view>
			</view>

			<view class="ingredient-card" v-for="item in detail.items" :key="item.id">
				<view class="ingredient-top u-flex u-row-between">
					<view>
						<view class="ingredient-name">{{ item.ingredient_name }}</view>
						<view class="quantity-text">需要 {{ formatQuantity(item.required_quantity) }} {{ item.unit }}，净需 {{ formatQuantity(item.net_quantity) }} {{ item.unit }}</view>
					</view>
					<u-tag v-if="item.purchase_mode === 'PLATFORM' && item.selected_goods_id" text="已匹配" type="success" mode="plain" size="mini"></u-tag>
					<u-tag v-else-if="item.purchase_mode === 'PLATFORM' && Number(item.net_quantity) > 0" text="待处理" type="warning" mode="plain" size="mini"></u-tag>
				</view>

				<view class="home-quantity u-flex u-row-between">
					<view>
						<view class="field-label">家中已有</view>
						<view class="field-help">保存后自动重算购买量</view>
					</view>
					<view class="u-flex">
						<u-number-box
							v-model="item.edit_home_quantity"
							:min="0"
							:step="1"
							:disabled="detail.status !== 'DRAFT'"
							@blur="saveHomeQuantity(item)"
						></u-number-box>
						<text class="unit">{{ item.unit }}</text>
					</view>
				</view>

				<view class="purchase-mode">
					<view class="field-label">购买方式</view>
					<u-subsection
						v-if="detail.status === 'DRAFT'"
						:list="purchaseModes"
						:current="modeIndex(item.purchase_mode)"
						:active-color="theme.bgColor"
						@change="changeMode(item, $event)"
					></u-subsection>
					<view class="mode-readonly" v-else>{{ modeText(item.purchase_mode) }}</view>
				</view>

				<view class="matched-product u-flex" v-if="item.purchase_mode === 'PLATFORM' && item.selected_goods_id">
					<image :src="item.selected_goods_image" mode="aspectFill"></image>
					<view class="product-content u-flex-1">
						<view class="product-title u-line-2">{{ item.selected_goods_title }}</view>
						<view class="product-meta">{{ item.selected_supplier_name || '平台供应' }} · {{ item.purchase_quantity }} 件</view>
						<view class="coverage">覆盖 {{ formatQuantity(item.covered_quantity) }} {{ item.unit }}<text v-if="Number(item.excess_quantity) > 0">，多 {{ formatQuantity(item.excess_quantity) }} {{ item.unit }}</text></view>
					</view>
				</view>
				<view class="match-warning" v-else-if="item.purchase_mode === 'PLATFORM' && Number(item.net_quantity) > 0">
					当前没有符合库存、配送或健康约束的商品，请选择自行购买或稍后重试。
				</view>
			</view>

			<u-gap height="150" bg-color="#f4f6f8"></u-gap>
			<view class="action-bar u-border-top">
				<u-button
					type="primary"
					shape="circle"
					:loading="submitting"
					:custom-style="{ backgroundColor: theme.bgColor, color: theme.color }"
					@click="confirmAndAdd"
				>{{ detail.status === 'DRAFT' ? '确认并加入购物车' : '加入购物车' }}</u-button>
			</view>
		</view>

		<view class="page-loading u-flex u-row-center" v-if="loading"><u-loading mode="flower" size="70"></u-loading></view>
	</view>
</template>

<script>
export default {
	onLoad(query) {
		this.listId = Number(query.id || 0);
		this.load();
	},
	data() {
		return {
			listId: 0,
			lists: [],
			pagination: {},
			detail: {},
			loading: true,
			submitting: false,
			updatingItems: {},
			purchaseModes: [
				{ name: '平台购买', value: 'PLATFORM' },
				{ name: '自行购买', value: 'SELF_PURCHASE' },
				{ name: '不购买', value: 'SKIP' }
			]
		};
	},
	computed: {
		platformItemCount() {
			return (this.detail.items || []).filter(item => item.purchase_mode === 'PLATFORM' && Number(item.net_quantity) > 0).length;
		}
	},
	methods: {
		load() {
			this.loading = true;
			if (this.listId) {
				this.loadDetail();
			} else {
				this.loadLists();
			}
		},
		loadLists() {
			this.$api.shoppingListListV1({ page_size: 50 }).then(res => {
				if (res.code) {
					this.lists = res.data.items || [];
					this.pagination = res.data.pagination || {};
				} else {
					this.$u.toast(res.msg);
				}
				this.finishLoading();
			});
		},
		loadDetail() {
			this.$api.shoppingListDetailV1(this.listId).then(res => {
				if (res.code) {
					this.applyDetail(res.data);
				} else {
					this.$u.toast(res.msg);
				}
				this.finishLoading();
			});
		},
		applyDetail(detail) {
			(detail.items || []).forEach(item => {
				item.edit_home_quantity = Number(item.home_quantity || 0);
			});
			this.detail = detail;
		},
		finishLoading() {
			this.loading = false;
			uni.stopPullDownRefresh();
		},
		openList(id) {
			this.goPage('/pages/shopping-list/index?id=' + id);
		},
		modeIndex(mode) {
			const index = this.purchaseModes.findIndex(item => item.value === mode);
			return index < 0 ? 0 : index;
		},
		modeText(mode) {
			const item = this.purchaseModes.find(item => item.value === mode);
			return item ? item.name : mode;
		},
		changeMode(item, index) {
			if (this.detail.status !== 'DRAFT' || this.updatingItems[item.id]) return;
			const mode = this.purchaseModes[index].value;
			if (mode === item.purchase_mode) return;
			this.updateItem(item, { purchase_mode: mode });
		},
		saveHomeQuantity(item) {
			if (this.detail.status !== 'DRAFT' || this.updatingItems[item.id]) return;
			const value = Math.max(0, Number(item.edit_home_quantity || 0));
			if (value === Number(item.home_quantity)) return;
			this.updateItem(item, { home_quantity: value, unit: item.unit });
		},
		updateItem(item, changes) {
			this.$set(this.updatingItems, item.id, true);
			this.$api.shoppingListItemUpdateV1(this.detail.id, item.id, changes).then(res => {
				if (res.code) {
					this.applyDetail(res.data);
				} else {
					this.$u.toast(res.msg);
					this.loadDetail();
				}
				this.$set(this.updatingItems, item.id, false);
			});
		},
		confirmAndAdd() {
			if (this.submitting) return;
			this.submitting = true;
			const confirmRequest = this.detail.status === 'DRAFT'
				? this.$api.shoppingListConfirmV1(this.detail.id)
				: Promise.resolve({ code: 1, data: this.detail });
			confirmRequest.then(res => {
				if (!res.code) {
					this.$u.toast(res.msg);
					this.submitting = false;
					return;
				}
				this.applyDetail(res.data);
				this.$api.cartAddV1({
					shopping_list_id: this.detail.id,
					shopping_list_version: this.detail.list_version
				}).then(cartRes => {
					this.$u.toast(cartRes.msg);
					this.submitting = false;
					if (cartRes.code) {
						this.goPage('/pages/cart/cart');
					}
				});
			});
		},
		formatQuantity(value) {
			const number = Number(value || 0);
			return Number.isInteger(number) ? String(number) : number.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
		},
		statusText(status) {
			return { DRAFT: '待确认', CONFIRMED: '已确认', ORDERED: '已下单', EXPIRED: '已失效' }[status] || status;
		},
		statusType(status) {
			return { DRAFT: 'warning', CONFIRMED: 'success', ORDERED: 'primary', EXPIRED: 'info' }[status] || 'info';
		}
	},
	onPullDownRefresh() {
		this.load();
	}
};
</script>

<style lang="scss">
page {
	background-color: #f4f6f8;
}
</style>

<style lang="scss" scoped>
.shopping-list-page {
	min-height: 100vh;
}
.list-page,
.detail-page {
	padding: 24rpx 24rpx 0;
}
.list-summary {
	display: flex;
	justify-content: space-between;
	padding: 4rpx 6rpx 20rpx;
	font-size: 26rpx;
	color: #303133;
	.summary-note {
		font-size: 23rpx;
		color: #909399;
	}
}
.list-card,
.detail-header,
.ingredient-card {
	background-color: #ffffff;
	border-radius: 12rpx;
}
.list-card {
	margin-bottom: 20rpx;
	padding: 28rpx;
	.list-name {
		font-size: 30rpx;
		font-weight: 600;
		color: #303133;
	}
	.list-sn {
		margin-top: 12rpx;
		font-size: 22rpx;
		color: #909399;
	}
	.list-stats {
		margin-top: 26rpx;
		font-size: 24rpx;
		color: #606266;
		text {
			margin-right: 24rpx;
		}
		.warning {
			color: #e6a23c;
		}
	}
	.list-time {
		margin-top: 16rpx;
		font-size: 22rpx;
		color: #b0b3b8;
	}
}
.detail-header {
	padding: 30rpx;
	.detail-title {
		font-size: 32rpx;
		font-weight: 600;
		color: #303133;
	}
	.detail-meta {
		margin-top: 14rpx;
		font-size: 24rpx;
		color: #909399;
	}
}
.ingredient-card {
	margin-top: 20rpx;
	padding: 30rpx;
	.ingredient-top {
		min-height: 80rpx;
	}
	.ingredient-name {
		font-size: 30rpx;
		font-weight: 600;
		color: #303133;
	}
	.quantity-text {
		margin-top: 10rpx;
		font-size: 23rpx;
		color: #909399;
	}
	.home-quantity,
	.purchase-mode {
		padding-top: 26rpx;
		margin-top: 24rpx;
		border-top: 1px solid #f0f1f3;
	}
	.field-label {
		font-size: 26rpx;
		color: #303133;
	}
	.field-help {
		margin-top: 6rpx;
		font-size: 21rpx;
		color: #a0a4aa;
	}
	.unit {
		width: 58rpx;
		margin-left: 12rpx;
		font-size: 24rpx;
		color: #606266;
	}
	.purchase-mode .field-label {
		margin-bottom: 18rpx;
	}
	.mode-readonly {
		padding: 18rpx 22rpx;
		background-color: #f4f6f8;
		font-size: 25rpx;
		color: #606266;
	}
}
.matched-product {
	margin-top: 24rpx;
	padding: 20rpx;
	background-color: #f7f8fa;
	border-radius: 8rpx;
	image {
		width: 120rpx;
		height: 120rpx;
		border-radius: 8rpx;
		background-color: #eef0f3;
	}
	.product-content {
		padding-left: 20rpx;
	}
	.product-title {
		font-size: 26rpx;
		line-height: 36rpx;
		color: #303133;
	}
	.product-meta,
	.coverage {
		margin-top: 9rpx;
		font-size: 22rpx;
		color: #909399;
	}
}
.match-warning {
	margin-top: 24rpx;
	padding: 20rpx;
	border-left: 6rpx solid #e6a23c;
	background-color: #fdf6ec;
	font-size: 23rpx;
	line-height: 36rpx;
	color: #8a6d3b;
}
.action-bar {
	position: fixed;
	right: 0;
	bottom: 0;
	left: 0;
	z-index: 1000;
	padding: 22rpx 48rpx calc(22rpx + env(safe-area-inset-bottom));
	background-color: #ffffff;
}
.page-loading {
	padding-top: 30vh;
}
.empty-state {
	padding-top: 180rpx;
}
</style>
