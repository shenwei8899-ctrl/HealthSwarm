<template>
	<view class="">
		<view class="orderby-select u-flex">
			<view class="u-flex-1 u-flex u-row-around u-p-r-10">
				<view class="u-tips-color order" v-for="(item, index) in orderList" :key="index" @click="orderBy(item, index)">
					<text :style="[{color:item.orderby == orderby?theme.bgColor:'#909399'}]">{{ item.name }}</text>
					<view class="arrow up" :class="item.orderby == orderby && item.orderway == 'desc' ? 'active-img' : 'arrow-img'"></view>
					<view class="arrow down" :class="item.orderby == orderby && item.orderway == 'asc' ? 'active-img' : 'arrow-img'"></view>
				</view>
			</view>
			<image @click="show = true" src="../../static/image/select.png" mode="aspectFit"></image>
		</view>
		<u-popup v-model="show" mode="right" width="88%" :customStyle="customStyle">
			<view class="fa-popup">
				<scroll-view class="fa-scroll-view" scroll-y="true">
					<view class="">
						<view class="u-p-20 u-flex bg-white u-row-between u-m-b-15">
							<view class="text-weight">分类</view>
							<view class="u-tips-color" @click="showCategory = true">
								{{ categoryText }}
								<u-icon name="arrow-right"></u-icon>
							</view>
						</view>

						<view class="u-flex bg-white u-row-between u-m-b-15">
							<view class="u-p-20 text-weight">筛选</view>
							<view class="" v-if="multiple">
								<u-checkbox v-model="checked" name="1" :active-color="theme.bgColor"><text>多选模式</text></u-checkbox>
							</view>
						</view>

						<view class="fa-select-list u-m-b-15 u-border-top">
							<view class="u-p-20 u-border-bottom u-flex u-row-between">
								<text class="text-weight">品牌</text>
								<text class="u-tips-color u-font-20">{{ itemText(0) }}</text>
							</view>
							<view class="u-flex u-flex-wrap list u-p-20">
								<view class="item u-m-b-15" :style="[itemStyle(0, item.id)]" v-for="(item, index) in vuex_config.brands" :key="index">
									<text class="u-m-r-5" @click="choose(0, item)">{{ item.name }}</text>
								</view>
							</view>
						</view>

						<view class="fa-select-list u-m-b-15 u-border-top" v-for="(item, index) in attrList" :key="index">
							<view class="u-p-20 u-border-bottom u-flex u-row-between">
								<text class="text-weight">{{ item.name }}</text>
								<text class="u-tips-color u-font-20">{{ itemText(item.id) }}</text>
							</view>
							<view class="u-flex u-flex-wrap list u-p-20">
								<view class="item u-m-b-15" :style="[itemStyle(item.id, res.id)]" v-for="(res, idx) in item.attribute_value" :key="idx">
									<text class="u-m-r-5" @click="choose(item.id, res)">{{ res.name }}</text>
								</view>
							</view>
						</view>

						<view class="fa-select-list u-m-b-15 u-border-top">
							<view class="u-p-20 u-border-bottom text-weight"><text>价格区间</text></view>
							<view class="u-flex u-row-between u-p-20">
								<u-input type="number" input-align="center" v-model="low_price" placeholder="最低价格"></u-input>
								<view class="u-p-l-15 u-m-p-r-15"><u-icon name="minus"></u-icon></view>
								<u-input type="number" input-align="center" v-model="high_price" placeholder="最高价格"></u-input>
							</view>
						</view>
					</view>
				</scroll-view>
				<view class="footer u-flex u-border-top">
					<view class="u-flex-6" @click="close">取消</view>
					<view class="u-flex-6" :style="{ backgroundColor: theme.bgColor, color: theme.color }" @click="toGo">确定</view>
				</view>
			</view>
		</u-popup>
		<u-popup v-model="showCategory" mode="right" width="88%" :customStyle="customStyle" z-index="10077">
			<view class="fa-popup">
				<scroll-view class="fa-scroll-view" scroll-y="true">
					<view class="bg-white">
						<u-radio-group v-model="category_id" :wrap="true">
							<u-cell-item @click="category_id = -1">
								<u-radio :active-color="theme.bgColor" slot="icon" :name="-1"></u-radio>
								<rich-text slot="title" nodes="全部分类"></rich-text>
							</u-cell-item>
							<u-cell-item v-for="(item, index) in categoryList" :key="index" @click="category_id = item.id">
								<u-radio :active-color="theme.bgColor" slot="icon" :name="item.id"></u-radio>
								<rich-text slot="title" :nodes="item.name"></rich-text>
							</u-cell-item>
						</u-radio-group>
					</view>
				</scroll-view>
				<view class="footer u-flex u-border-top">
					<view class="u-flex-6" @click="showCategory = false">取消</view>
					<view class="u-flex-6" :style="{ backgroundColor: theme.bgColor, color: theme.color }" @click="showCategory = false">确定</view>
				</view>
			</view>
		</u-popup>
	</view>
</template>

<script>
// 获取系统状态栏的高度
let systemInfo = uni.getSystemInfoSync();
function getParentCategory(list, pid, names) {
	for (let item of list) {
		if (item.id == pid) {
			names.unshift(item.name.replace(item.spacer, '').trim());
			getParentCategory(list, item.pid, names);
		}
	}
}
export default {
	name: 'fa-orderby-select',
	props: {
		multiple: {
			type: Boolean,
			default: true
		},
		separator: {
			type: String,
			default: ','
		},
		categoryId: {
			type: [String, Number],
			default: ''
		}
	},
	filters: {},
	computed: {
		// 转换字符数值为真正的数值
		navbarHeight() {
			// #ifdef H5
			return 44;
			// #endif
			// #ifdef APP-PLUS
			return 44 + systemInfo.statusBarHeight;
			// #endif
			// #ifdef MP
			// 小程序特别处理，让导航栏高度 = 胶囊高度 + 两倍胶囊顶部与状态栏底部的距离之差(相当于同时获得了导航栏底部与胶囊底部的距离)
			let height = systemInfo.platform == 'ios' ? 44 : 48;
			return height + systemInfo.statusBarHeight;
			// #endif
		},
		customStyle() {
			return {
				height: 'calc(100% - ' + this.navbarHeight + 'px)',
				top: this.navbarHeight + 'px'
			};
		},
		//排序样式
		activate() {
			return item => {
				if (item.orderby == this.orderby) {
					console.log(item.orderway);
					return item.orderway == 'asc';
				}
				return false;
			};
		},
		//选中样式
		itemStyle() {
			return (attribute_id, id) => {
				let style = {
					backgroundColor: this.theme.bgColor,
					color: this.theme.color
				};
				if (!this.checked && this.singleList[attribute_id] && this.singleList[attribute_id].id == id) {
					return style;
				} else if (this.checked && this.manyList[attribute_id] && this.manyList[attribute_id].some(item => item.id == id)) {
					return style;
				}
				return {};
			};
		},
		//选中文本
		itemText() {
			return attribute_id => {
				if (!this.checked && this.singleList[attribute_id]) {
					return this.singleList[attribute_id].name;
				} else if (this.checked && this.manyList[attribute_id]) {
					let result = this.manyList[attribute_id].map(item => item.name);
					return result.join(',');
				}
				return '';
			};
		},
		categoryText() {
			let row = this.categoryList.find(item => {
				if (!this.category_id) {
					return item.id == this.categoryId;
				} else {
					return item.id == this.category_id;
				}
			});
			if (row) {
				this.category_id = row.id;
				let names = [];
				names.unshift(row.name.replace(row.spacer, '').trim());
				getParentCategory(this.categoryList, row.pid, names);
				return names.join('>');
			}
			return '全部分类';
		}
	},
	watch: {
		category_id(newValue, oldValue) {
			this.singleList = [];
			this.manyList = [];
			this.getAttrs(newValue>0?newValue:0);
			this.showCategory = false;
		}
	},
	mounted() {
		this.init();
	},
	data() {
		return {
			show: false,
			showCategory: false,
			checked: false,
			orderList: [
				{ name: '默认', orderby: 'weigh', orderway: 'desc' },
				{ name: '销量', orderby: 'sales', orderway: 'desc' },
				{ name: '价格', orderby: 'price', orderway: 'desc' },
				{ name: '浏览', orderby: 'views', orderway: 'desc' },
				{ name: '评价数', orderby: 'comments', orderway: 'desc' },
				// { name: '发布时间', orderby: 'createtime', orderway: 'desc' }
			],
			filterList: [],
			low_price: '',
			high_price: '',
			singleList: [],
			manyList: [],
			orderby: 'weigh',
			orderway: 'desc',
			attrList: [],
			categoryList: [],
			category_id: ''
		};
	},
	methods: {
		init() {
			this.$api.allCategory().then(res => {
				const { code, data, msg } = res;
				if (code) {
					this.categoryList = data;
				}
			});
		},
		getAttrs(categoryId) {
			this.$api.attribute({ category_id: categoryId }).then(res => {
				const { code, data, msg } = res;
				if (code) {
					this.attrList = data;
				}
			});
		},
		close() {
			this.show = false;
		},
		orderBy(item, index) {
			if (this.orderway == item.orderway && item.orderway == 'desc' && this.orderby == item.orderby) {
				this.$set(this.orderList[index], 'orderway', 'asc');
				this.orderway = 'asc';
			} else if (this.orderway == item.orderway && item.orderway == 'asc' && this.orderby == item.orderby) {
				this.$set(this.orderList[index], 'orderway', 'desc');
				this.orderway = 'desc';
			} else {
				this.orderway = item.orderway;
			}
			this.orderby = item.orderby;
			console.log(this.orderby, this.orderway);
			this.toGo();
		},
		//选中
		choose(attribute_id, info) {
			if (!this.checked) {
				if (this.singleList[attribute_id] && this.singleList[attribute_id].id == info.id) {
					this.$set(this.singleList, attribute_id, null);
				} else {
					this.$set(this.singleList, attribute_id, info);
				}
			} else {
				if (this.manyList[attribute_id]) {
					let index = this.manyList[attribute_id].findIndex(item => item.id == info.id);
					if (index < 0) {
						this.manyList[attribute_id].push(info);
					} else {
						this.manyList[attribute_id].splice(index, 1);
					}
				} else {
					this.$set(this.manyList, attribute_id, []);
					this.manyList[attribute_id].push(info);
				}
				console.dir(this.manyList);
			}
		},
		//取筛选条件
		toGo() {
			let query = {};
			//单选
			let attributes = [];
			if (!this.checked) {
				this.singleList.forEach((item, index) => {
					if (!index && item) {
						query.brand_id = item.id;
					} else if (item) {
						attributes.push({
							attribute_id: index,
							value_id: item.id
						});
					}
				});
			} else {
				//多选
				query.multiple = 1;
				this.manyList.forEach((item, index) => {
					let arr = [];
					item.forEach(res => {
						arr.push(res.id);
					});
					if (!index) {
						query.brand_id = arr.join(',');
					} else if (arr.length) {
						attributes.push({
							attribute_id: index,
							value_id: arr
						});
					}
				});
			}
			query.attributes = attributes;
			//价格
			if (!this.$u.test.empty(this.low_price) && this.low_price >= 0 && this.high_price >= this.low_price) {
				query.price = this.low_price + '-' + this.high_price;
			}
			query.orderby = this.orderby;
			query.orderway = this.orderway;
			if (this.category_id>0) {
				query.category_id = this.category_id;
			}
			this.show = false;
			this.$emit('change', query);
		}
	}
};
</script>

<style lang="scss" scoped>
.orderby-select {
	image {
		width: 35rpx;
		height: 35rpx;
	}
	.order {
		position: relative;
		padding-right: 20rpx;
		.arrow {
			position: absolute;
			right: 0;
			width: 0;
			height: 0;
			border-left: 8rpx solid transparent;
			border-right: 8rpx solid transparent;			
		}
		.arrow-img {
			border-bottom: 10rpx solid #b1b1b1;
		}
		.up {
			transform: scaleY(-1);
			bottom: 8rpx;
		}
		.down {
			transform: scaleY(1);
			top: 8rpx;
		}
		.active-img {
			border-bottom: 12rpx solid #374486;
		}
	}
}
.fa-select-list {
	background-color: #ffffff;
	.title {
	}
	.list {
		.item {
			background-color: #eeeeee;
			padding: 10rpx 30rpx;
			border-radius: 100rpx;
			margin-right: 15rpx;
			color: $u-tips-color;
		}
	}
}
.fa-popup {
	height: 100%;
	background-color: #f7f7f7;
	.fa-scroll-view {
		height: calc(100% - 100rpx);
	}
	.footer {
		background-color: #ffffff;
		height: 100rpx;
		line-height: 100rpx;
		display: flex;
		width: 100%;
		text-align: center;
	}
}
</style>
