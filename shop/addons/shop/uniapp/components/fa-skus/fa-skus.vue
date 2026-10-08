<template>
	<view>
		<u-popup v-model="value" :popup="false" mode="bottom" :height="height(800, 430)" @close="close" :closeable="true" border-radius="20">
			<view class="add-carts">
				<view class="header u-flex">
					<image :src="goods.image || goodsInfo.image" mode="aspectFill"></image>
					<view class="u-p-l-30 right">
						<view class="">
							<text class="price u-font-36">￥{{ goods.price || goodsInfo.price }}</text>
							<text class="u-m-l-30 u-tips-color">销量 {{ goods.sales == undefined ? goodsInfo.sales:goods.sales }}</text>
						</view>
						<view class="u-flex u-flex-wrap">
							<text class="u-m-r-15 u-tips-color">已选:</text>
							<text>{{ skuArrtext }}</text>
							<text>{{ nums }}件</text>
						</view>
					</view>
				</view>
				<view class="u-p-t-20 u-p-b-10">
					<scroll-view scroll-y="true" class="scroll-Y" :style="{ height: height(500, 130) + 'rpx' }">
						<view class="content">
							<block v-for="(item, index) in skuSpec" :key="index">
								<view class="u-p-t-20 u-p-b-30 text-weight">{{ item.title }}</view>
								<view class="u-flex u-flex-wrap">
									<view class="item u-m-b-20" v-for="(res, key) in item.sku_value" :key="key">
										<u-button size="mini" shape="circle" hover-class="none" :type="res.id == goods_sku_ids[index] ? 'error' : 'default'" :plain="!(res.id == goods_sku_ids[index])" throttle-time="0" :custom-style="customStyle(res.id == goods_sku_ids[index])" @click="cutSku(res, index)" :disabled="res.is_disabled">
											{{ res.title }}
										</u-button>
									</view>
								</view>
							</block>
							<view class="u-p-t-20 u-p-b-30 u-flex u-row-between">
								<text class="text-weight">数量</text>
								<u-number-box v-model="nums" :min="1" @blur="setCartNum" @minus="setCartNum" @plus="setCartNum"></u-number-box>
							</view>
						</view>
					</scroll-view>
				</view>
				<view class="u-flex u-row-center u-flex-1" v-if="sceneval>0">
					<view class="">
						<u-button size="medium" hover-class="none" :custom-style="{ width: '85vw', backgroundColor: theme.bgColor, color: theme.color }" shape="circle" @click="addCart(false)" throttle-time="0">
							确定
						</u-button>
					</view>
				</view>
				<view class="u-flex u-row-between u-flex-1" v-else>
					<view class="">
						<u-button size="medium" hover-class="none" :custom-style="{ width: '45vw', backgroundColor: '#ffba0d', color: theme.color }" shape="circle" @click="addCart(1)">
							加入购物车
						</u-button>
					</view>
					<view class="">
						<u-button size="medium" hover-class="none" :custom-style="{ width: '45vw', backgroundColor: theme.bgColor, color: theme.color }" shape="circle" @click="addCart(2)">
							立即购买
						</u-button>
					</view>
				</view>
			</view>
		</u-popup>
	</view>
</template>

<script>
	export default {
		name: 'fa-carts',
		props: {
			value: {
				type: Boolean,
				default: false
			},
			goodsInfo: {
				type: Object,
				default () {
					return {};
				}
			},
			sceneval: {
				type: Number,
				default: 1
			}
		},
		computed: {
			skuArrtext() {
				let newArr = this.goods_sku_text.filter(i => i && i.trim());
				if (newArr.length > 0) {
					return newArr.join(',') + ',';
				}
				return '';
			},
			customStyle() {
				return status => {
					let style = { padding: '28rpx 40rpx' };
					if (status) {
						style.backgroundColor = this.theme.bgColor;
						style.color = this.theme.color;
					}
					return style;
				};
			},
			height() {
				return (a, b) => {
					return (this.skuSpec.length > 0 ? a : b) + '';
				};
			}
		},
		watch: {
			goods_sku_ids: {
				handler(val) {
					//都选择了
					if (val.length == this.skuSpec.length) {
						this.goods = this.sku[JSON.parse(JSON.stringify(val)).sort()] || {};
					}
				},
				deep: true
			}
		},
		data() {
			return {
				show: true,
				skuSpec: [],
				sku: [],
				goods_sku_ids: [],
				goods_sku_text: [],
				goods: {},
				nums: 1
			};
		},
		created() {
			this.skuSpec = this.goodsInfo.sku_spec;
			let skus = [];
			this.goodsInfo.sku.forEach(item => {
				let ids = item.sku_id.split(',').sort();
				skus[ids] = item;
			});
			this.sku = skus;
			this.changeItems();
		},
		methods: {
			close() {
				this.$emit('input', false);
			},
			cutSku(item, index) {
				if (this.goods_sku_ids[index] != undefined && this.goods_sku_ids[index] == item.id) {
					this.$set(this.goods_sku_ids, index, ''); //储存id
					this.$set(this.goods_sku_text, index, '');
				} else {
					this.$set(this.goods_sku_ids, index, item.id); //储存id
					this.$set(this.goods_sku_text, index, item.title); //储存名称
				}
				this.changeItems();
			},
			changeItems() {
				let result = []; //定义数组存储被选中的值
				this.skuSpec.forEach((item, index) => {
					result[index] = this.goods_sku_ids[index] ? this.goods_sku_ids[index] : '';
				});
				for (let [index, item] of this.skuSpec.entries()) {
					let last = result[index];
					for (let i in item.sku_value) {
						result[index] = item.sku_value[i].id;
						this.$set(this.skuSpec[index].sku_value[i], 'is_disabled', !this.isDisabled(result));
					}
					result[index] = last;
				}
			},
			//判断禁用
			isDisabled(result) {
				for (let i in result) {
					if (result[i] == '') {
						return true; //如果数组里有为空的值，那直接返回true
					}
				}
				//避免结果被修改
				let res = JSON.parse(JSON.stringify(result));
				return this.sku[res.sort()] && this.sku[res.sort()].stocks > 0;
			},
			setCartNum() {},
			//加入购物车
			addCart(sceneval) {
				if (!sceneval && this.goods_sku_text.length < this.skuSpec.length) {
					this.$u.toast('请选择商品规格')
					return;
				}
				//立即购买，加入购物车，即提交订单
				sceneval = sceneval || this.sceneval;
				this.$api
					.addCart({
						goods_id: this.goodsInfo.id,
						nums: this.nums,
						goods_sku_id: this.goods.id || '',
						sceneval: sceneval
					})
					.then(res => {
						this.$u.toast(res.msg);
						this.$emit('input', false);
						if (res.code == 1 && sceneval == 2) {
							//立即购买，
							this.goPage('/pages/goods/order?id=' + res.data + '&sceneval=' + sceneval);
						} else {
							this.$emit('success');
						}
					});
			}
		}
	};
</script>

<style lang="scss" scoped>
	.add-carts {
		padding: 30rpx 30rpx 0;

		.content {
			display: flex;
			flex-direction: column;

			.item {
				margin-right: 15rpx;
			}
		}
	}

	.header {
		image {
			width: 200rpx;
			height: 150rpx;
			border-radius: 10rpx;
		}

		.right {
			height: 120rpx;
			display: flex;
			flex-direction: column;
			justify-content: space-between;
		}
	}
</style>