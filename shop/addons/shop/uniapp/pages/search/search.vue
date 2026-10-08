<template>
	<view>
		<fa-navbar title="搜索" :border-bottom="false"></fa-navbar>
		<view class="u-p-20">
			<fa-search ref="search" :mode="2" @search="doSearch"></fa-search>
		</view>
		<view class="search-keyword">
			<scroll-view class="keyword-box" scroll-y>
				<view class="keyword-block" v-if="vuex_history_keyword.length > 0">
					<view class="u-flex u-row-between u-p-t-30 u-p-b-30 u-tips-color">
						<view>历史搜索</view>
						<view @tap="oldDelete">
							<u-icon size="35" name="trash-fill"></u-icon>
						</view>
					</view>
					<view class="u-flex u-flex-wrap">
						<view class="u-m-r-15 u-m-b-15" v-for="(keyword, index) in vuex_history_keyword" @tap="doSearch(keyword)" :key="index">
							<u-tag :text="keyword" type="info" shape="circle"/>
						</view>
					</view>
				</view>
				<view class="keyword-block">
					<view class="u-flex u-row-between u-p-t-30 u-p-b-30 u-tips-color">
						<view>热门搜索</view>
						<view @tap="forbid=!forbid">
							<u-icon size="40" :name="forbid?'eye-fill':'eye-off'"></u-icon>
						</view>
					</view>
					<view class="u-flex u-flex-wrap" v-if="forbid">
						<view class="u-m-r-15 u-m-b-15" v-for="(keyword, index) in vuex_config.hot_keyword" @tap="doSearch(keyword)" :key="index">
							<u-tag :text="keyword" type="info" shape="circle"/>
						</view>
					</view>
					<view class="u-text-center u-tips-color" v-else><view>当前搜热门搜索已隐藏</view></view>
				</view>
			</scroll-view>
		</view>
	</view>
</template>

<script>
	export default {
		onReady() {
			this.$refs.search.getFocus();
		},
		data() {
			return {
				forbid:true,	
			}
		},
		methods: {
			doSearch(value) {
				if(!value.trim()){
					this.$u.toast('请输入关键词')
					return;
				}
				this.active = true;
				this.inputVal = value;
				this.setHistory(value);
				this.goPage('/pages/goods/goods?keyword='+value)
			},		
			setHistory(val){
				let array = JSON.parse(JSON.stringify(this.vuex_history_keyword));
				const index = array.findIndex(item=>item==val);
				if(index>-1){
					array.splice(index,1);
				}
				this.$u.vuex('vuex_history_keyword',[val,...array]);			
			},
			oldDelete(){
				this.$u.vuex('vuex_history_keyword',[]);
			}
		}
	}
</script>

<style lang="scss" scoped>
.search-keyword{
	padding:0 30rpx 30rpx;
	.keyword-block{
		padding-bottom: 30rpx;
		border-top: 1px solid #F4F6F8;
	}
}
</style>
