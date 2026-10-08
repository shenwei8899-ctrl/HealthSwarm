<template>
	<view>
		<u-popup v-model="value" :popup="false" mode="bottom" @close="close" border-radius="20" :closeable="true">
			<view class="u-p-30">
				<view class="u-text-center u-tips-color">
					回复评论
				</view>
				<view class="u-m-t-30"><u-input height="200" v-model="content" type="textarea" /></view>
				<view class="u-p-t-30 u-flex u-row-center">
					<u-button
						size="medium"
						type="primary"
						hover-class="none"
						:custom-style="{ width: '80vw', backgroundColor: theme.bgColor, color: theme.color }"
						shape="circle"
						@click="submit"
					>
						提交
					</u-button>
				</view>
			</view>
		</u-popup>
	</view>
</template>

<script>
export default {
	name: 'fa-replys',
	props: {
		value: {
			type: Boolean,
			default: false
		},
		pid:{
			type:[Number,String],
			default:''
		}
	},
	data() {
		return {
			content: ''
		};
	},
	methods: {
		close() {
			this.$emit('input', false);
		},
		submit(){
			if(!this.content.trim()){
				this.$u.toast('请输入回复内容');
				return;
			}
			this.$api.commentReply({
				pid:this.pid,
				content:this.content
			}).then(res=>{
				this.content = '';
				this.$u.toast(res.msg);
				this.close();
				this.$emit('success')
			})
		}
	}
};
</script>

<style lang="scss"></style>
