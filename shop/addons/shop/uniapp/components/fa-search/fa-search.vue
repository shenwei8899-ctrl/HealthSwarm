<template>
	
		<view class="search u-flex u-col-center" :style="[{height:height+'rpx'}]">
			<view class="content u-flex-1" :style="{ 'border-radius': radius + 'px' }">
				<view class="content-box" :class="{ center: mode === 2 }" @click.self="getFocus">
					<u-icon name="search" color="#808080" size="30"></u-icon>
					<input
						class="input u-m-l-10"
						:class="{ center: !active && mode === 2 }"
						:style="[{lineHeight:height+'rpx',height:height+'rpx',fontSize:fontSize+'rpx'}]"
						:focus="isFocus"
						:placeholder="placeholder"
						v-model="inputVal"
						@focus="focus"
						@blur="blur"
						@confirm="search"
					/>
					<u-icon v-if="isDelShow" @click="clear" name="close-circle-fill" color="#b4b4b4" size="35"></u-icon>
				</view>
			</view>			
		</view>		

</template>

<script>
export default {
	name: 'fa-search',
	props: {
		mode: {
			type: Number,
			default: 1
		},
		radius: {
			type: String,
			default: '60'
		},
		placeholder: {
			type: String,
			default: '请输入关键词搜索'
		},
		show:{
			type:Boolean,
			default:false
		},
		height:{
			type:[Number,String],
			default:60
		},
		noFocus:{
			type:Boolean,
			default:false
		},
		fontSize:{
			type:[Number,String],
			default:28
		}
	},
	data() {
		return {
			active: false,
			inputVal: '',
			isDelShow: false,
			isFocus: false,					
		};
	},
	watch: {
		inputVal(newVal) {
			if (newVal) {
				this.isDelShow = true;
			} else {
				this.isDelShow = false;
				this.$emit('search', '');
			}
		}
	},
	methods: {
		focus() {
			if(this.noFocus){
				this.$emit('focus');
				return;
			}
			this.active = true;			
		},
		blur() {
			this.isFocus = false;
			if (!this.inputVal) {
				this.active = false;
			}
		},
		clear() {
			this.inputVal = '';
			this.active = false;
		},
		getFocus() {
			this.isFocus = true;
		},
		search(e) {			
			this.$emit('search', e.detail.value);
		}		
	}
};
</script>

<style lang="scss" scoped>
.search {
	display: flex;
	width: 100%;
	box-sizing: border-box;
	font-size: 28rpx;	
	.content {
		display: flex;
		align-items: center;
		width: 100%;		
		background-color: #f2f2f2;
		overflow: hidden;
		transition: all 0.2s linear;
		border-radius: 30px;
		padding: 0 30rpx;
		.content-box {
			width: 100%;
			display: flex;
			align-items: center;
			&.center {
				justify-content: center;
			}
			.input {
				width: 100%;
				max-width: 100%;				
				background-color: #f2f2f2;
				transition: all 0.2s linear;
				&.center {
					width: 250rpx;
				}
				&.sub {
					width: auto;
					color: grey;
				}
			}
		}
	}
}
</style>
