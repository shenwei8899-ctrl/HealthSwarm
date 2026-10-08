<template>
	<view>
		<!-- 顶部导航 -->
		<fa-navbar :title="title" :border-bottom="false"></fa-navbar>
		<view class="u-p-30 bg-white">
			<u-form :model="form" ref="uForm" label-width="180">
				<u-form-item label="收货人" prop="receiver"><u-input v-model="form.receiver" /></u-form-item>
				<u-form-item label="手机号码" prop="mobile"><u-input v-model="form.mobile" /></u-form-item>
				<u-form-item label="所在地区" prop="area_name">
					<u-input type="select" :select-open="cityShow" v-model="form.area_name" placeholder="请选择地区" @click="cityShow = true"></u-input>
				</u-form-item>
				<u-form-item label="详细地址" prop="address">
					<u-input type="textarea" v-model="form.address" />
					<u-button slot="right" type="primary" :custom-style="{ backgroundColor: theme.bgColor, color: theme.color }" size="mini" @click="chooseAddress">
						选择地址
					</u-button>
				</u-form-item>
				<u-form-item label="设为默认地址" :border-bottom="false">
					<u-switch slot="right" :active-color="theme.bgColor" v-model="isdefault" @change="change"></u-switch>
				</u-form-item>
			</u-form>
		</view>
		<!-- 城市 -->
		<view class="" v-if="is_render"><fa-citys v-model="cityShow" :areaCode="areaCode" @city-change="cityResult"></fa-citys></view>
		<view class="footer-bar u-flex u-col-center u-row-center u-border-top">
			<u-button type="primary" :custom-style="{ width: '80vw', backgroundColor: theme.bgColor, color: theme.color }" shape="circle" hover-class="none" @click="sumbit">
				提交
			</u-button>
		</view>
	</view>
</template>

<script>
export default {
	onLoad(e) {
		this.id = e.id || '';
		if (e.id) {
			this.title = '编辑地址';
			this.getAddressInfo();
		} else {
			this.title = '添加地址';
			this.is_render = true;
			this.isdefault = this.vuex_address.id ? false : true;
		}
		uni.setNavigationBarTitle({
			title: this.title
		});
	},
	onReady() {
		this.$refs.uForm.setRules(this.rules);
	},
	data() {
		return {
			title: '添加地址',
			form: {
				receiver: '',
				mobile: '',
				address: '',
				isdefault: 1,
				area_name: '',
				area_id: ''
			},
			rules: {
				receiver: [
					{
						required: true,
						message: '请输入姓名',
						// 可以单个或者同时写两个触发验证方式
						trigger: ['change', 'blur']
					}
				],
				mobile: [
					{
						validator: (rule, value, callback) => {
							return this.$u.test.mobile(value);
						},
						message: '手机号码不正确',
						// 可以单个或者同时写两个触发验证方式
						trigger: ['change', 'blur']
					}
				],
				address: [
					{
						required: true,
						message: '请输入详细地址',
						// 可以单个或者同时写两个触发验证方式
						trigger: ['change', 'blur']
					}
				],
				area_name: [
					{
						required: true,
						message: '请选择地区',
						// 可以单个或者同时写两个触发验证方式
						trigger: ['change', 'blur']
					}
				]
			},
			isdefault: false,
			cityShow: false,
			is_render: false,
			areaCode: []
		};
	},
	methods: {
		getAddressInfo() {
			this.$api.addressInfo({ id: this.id }).then(res => {
				if (res.code) {
					this.form = Object.assign(this.form, {
						id: this.id,
						receiver: res.data.receiver,
						mobile: res.data.mobile,
						address: res.data.address
					});
					this.isdefault = res.data.isdefault == 1;
					this.areaCode = [res.data.province_id, res.data.city_id, res.data.area_id];
					this.is_render = true;
				} else {
					this.$u.toast(res.msg);
					uni.$u.route({
						type:'back'
					});
				}
			});
		},
		change(value) {
			this.form.isdefault = value ? 1 : 0;
		},
		chooseAddress() {
			uni.chooseLocation({
				success: res => {
					Object.assign(this.form, {
						address: res.address
					});
				},
				fail: (e) => {
					console.log(e);
				}
			});
		},
		//城市选择
		cityResult(e) {
			this.form.area_name = e.province.label + '/' + e.city.label + '/' + e.area.label;
			this.form.area_id = e.area.value;
		},
		sumbit() {
			this.$refs.uForm.validate(valid => {
				if (valid) {
					this.$api.addressAdd(this.form).then(res => {
						this.$u.toast(res.msg);
						if (res.code) {
							setTimeout(() => {
								uni.$u.route({
									type:'back'
								})
							}, 1500);
						}
					});
				} else {
					console.log('验证失败');
				}
			});
		}
	}
};
</script>

<style lang="scss">
page {
	background-color: #f4f6f8;
}
</style>
