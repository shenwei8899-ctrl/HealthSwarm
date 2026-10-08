<template>
	<view class="fa-poster">
		<view class="" v-if="showCanvas"><canvas canvas-id="poster" class="poster_canvas" :style="[{ width: width + 'px', height: height + 'px' }]"></canvas></view>
		<u-popup v-model="value" :popup="false" mode="center" @close="hide">
			<view class="">
				<!-- #ifdef H5 -->
				<view class="poster-img"><image class="" :src="posterImgs" mode="aspectFit"></image></view>
				<!-- #endif -->
				<!-- #ifndef H5 -->
				<view class="poster-img"><image class="" :src="posterImgs" mode="aspectFit" @longpress="save"></image></view>
				<!-- #endif -->
				<view class="u-flex u-row-between u-m-t-15">
					<view class="btn" @click="hide">取消</view>
					<view class="btn" @click="save">长按保存到本地</view>
				</view>
			</view>
		</u-popup>
	</view>
</template>

<script>
let settingWritePhotosAlbum = false;
export default {
	name: 'fa-poster',
	props: {
		value: {
			type: Boolean,
			default: false
		},
		goods: {
			type: Object,
			default() {
				return {};
			}
		}
	},
	watch: {
		value(newValue, oldValue) {
			if (newValue) {
				this.initCanvas();
			}
		}
	},
	data() {
		return {
			width: 750,
			height: 1334,
			imgWidth: 0,
			imgHeight: 0,
			multiple: 1, //倍数
			showCanvas: false,
			posterImgs: ''
		};
	},
	methods: {
		hide() {
			this.$emit('input', false);
		},
		//获取小程序码或二维码
		getWxCode() {
			return new Promise((resolve, reject) => {
				let version = 'release';
									
				// #ifdef MP-WEIXIN
				let info = uni.getAccountInfoSync();
				version = info.miniProgram.envVersion || 'release';
				// #endif
				
				this.$api.getWxCode({ goods_id: this.goods.id, version: version }).then(({ code, data: res, msg }) => {
					if (code) {
						resolve(res);
					} else {
						reject(msg);
					}
				});
			});
		},
		//下载图片
		downloadImg(path) {
			return new Promise((resolve, reject) => {
				uni.downloadFile({
					url: path,
					success: res => {
						if (res.statusCode === 200) {
							resolve(res.tempFilePath);
						} else {
							reject('图片下载失败');
						}
					},
					fail: err => {
						reject(err);
					}
				});
			});
		},
		//获取图片信息
		getImageInfo(path) {
			return new Promise((resolve, reject) => {
				uni.getImageInfo({
					src: path,
					success: function(res) {
						resolve(res);
					},
					fail(err) {
						reject(err);
					}
				});
			});
		},
		// 文字换行
		drawtext(text, maxWidth) {
			let textArr = text.split('');
			let len = textArr.length;
			// 上个节点
			let previousNode = 0;
			// 记录节点宽度
			let nodeWidth = 0;
			// 文本换行数组
			let rowText = [];
			// 如果是字母，侧保存长度
			let letterWidth = 0;
			// 汉字宽度
			let chineseWidth = 21 * this.multiple;
			// otherFont宽度
			let otherWidth = 10.5 * this.multiple;
			for (let i = 0; i < len; i++) {
				if (/[\u4e00-\u9fa5]|[\uFE30-\uFFA0]/g.test(textArr[i])) {
					if (letterWidth > 0) {
						if (nodeWidth + chineseWidth + letterWidth * otherWidth > maxWidth) {
							rowText.push({
								type: 'text',
								content: text.substring(previousNode, i)
							});
							previousNode = i;
							nodeWidth = chineseWidth;
							letterWidth = 0;
						} else {
							nodeWidth += chineseWidth + letterWidth * otherWidth;
							letterWidth = 0;
						}
					} else {
						if (nodeWidth + chineseWidth > maxWidth) {
							rowText.push({
								type: 'text',
								content: text.substring(previousNode, i)
							});
							previousNode = i;
							nodeWidth = chineseWidth;
						} else {
							nodeWidth += chineseWidth;
						}
					}
				} else {
					if (/\n/g.test(textArr[i])) {
						rowText.push({
							type: 'break',
							content: text.substring(previousNode, i)
						});
						previousNode = i + 1;
						nodeWidth = 0;
						letterWidth = 0;
					} else if (textArr[i] == '\\' && textArr[i + 1] == 'n') {
						rowText.push({
							type: 'break',
							content: text.substring(previousNode, i)
						});
						previousNode = i + 2;
						nodeWidth = 0;
						letterWidth = 0;
					} else if (/[a-zA-Z0-9]/g.test(textArr[i])) {
						letterWidth += 1;
						if (nodeWidth + letterWidth * otherWidth > maxWidth) {
							rowText.push({
								type: 'text',
								content: text.substring(previousNode, i + 1 - letterWidth)
							});
							previousNode = i + 1 - letterWidth;
							nodeWidth = letterWidth * otherWidth;
							letterWidth = 0;
						}
					} else {
						if (nodeWidth + otherWidth > maxWidth) {
							rowText.push({
								type: 'text',
								content: text.substring(previousNode, i)
							});
							previousNode = i;
							nodeWidth = otherWidth;
						} else {
							nodeWidth += otherWidth;
						}
					}
				}
			}
			if (previousNode < len) {
				rowText.push({
					type: 'text',
					content: text.substring(previousNode, len)
				});
			}
			return rowText;
		},
		//init
		async initCanvas() {
			//先取下载图片
			const goodsImgPath = await this.downloadImg(this.goods.image);
			//取图片信息
			const { width, height } = await this.getImageInfo(goodsImgPath);
			console.log(width, height);
			//最小375
			if (width > height && height > 375) {
				this.width = 2 * height;
				this.height = (2 * height * 1334) / 750;
				this.imgWidth = width;
			} else if (height > width && width > 375) {
				this.width = 2 * width;
				this.height = (2 * width * 1334) / 750;
				this.imgHeight = height;
			}
			//倍数
			this.multiple = (this.width / 750).toFixed(2);
			//加载画布
			this.showCanvas = true;
			this.$nextTick(() => {
				this.createPoster(goodsImgPath);
			});
		},
		// 创建海报
		async createPoster(goodsImgPath) {
			try {
				if (this.posterImgs) {
					return;
				}
				uni.showLoading({
					title: '海报生成中'
				});
				const ctx = uni.createCanvasContext('poster', this);
				ctx.fillRect(0, 0, this.width / 2, this.height / 2);
				ctx.setFillStyle('#FFF');
				ctx.fillRect(0, 0, this.width / 2, this.height / 2);
				this.drawImage(ctx, goodsImgPath);
				const codeUrl = await this.getWxCode();
				const left_gap = 17 * this.multiple;
				// 商品标题
				let drawtextList = this.drawtext(this.goods.title, this.width / 2 - 30 * this.multiple);
				let textTop = 0,
					len = drawtextList.length;
				if (len == 1) {
					ctx.setFontSize(22 * this.multiple);
				} else {
					ctx.setFontSize(21 * this.multiple);
				}
				ctx.setFillStyle('#333');
				for (let [index, item] of drawtextList.entries()) {
					if (len == 1) {
						textTop = this.width / 2 + (index + 1) * 50 * this.multiple;
						ctx.fillText(item.content, left_gap, textTop);
						textTop += 10;
					} else if (index < 2) {
						textTop = this.width / 2 + (index + 1) * 35 * this.multiple;
						ctx.fillText(item.content, left_gap, textTop);
					}
				}
				// 商品价格
				ctx.setFontSize(26 * this.multiple);
				ctx.setFillStyle('#f00');
				ctx.fillText('￥' + this.goods.price, left_gap, textTop + 47 * this.multiple);
				// 商品门市价
				ctx.setFontSize(18 * this.multiple);
				ctx.setFillStyle('#999');
				let textLeft = (60 + (this.goods.price + '').length * 13) * this.multiple;
				ctx.fillText('￥' + this.goods.marketprice, textLeft, textTop + 45 * this.multiple);
				// // 商品门市价横线
				ctx.beginPath();
				ctx.setLineWidth(1 * this.multiple);
				ctx.moveTo(textLeft - 1, textTop + 38 * this.multiple);
				ctx.lineTo(textLeft + 20 + (this.goods.marketprice + '').length * 9, textTop + 38 * this.multiple);
				ctx.setStrokeStyle('#999');
				ctx.stroke();
				// // 商品分割线
				ctx.beginPath();
				ctx.setLineWidth(1 * this.multiple);
				ctx.moveTo(left_gap, textTop + 70 * this.multiple);
				ctx.lineTo(this.width / 2 - 20, textTop + 70 * this.multiple);
				ctx.setStrokeStyle('#eee');
				ctx.stroke();
				// // 长按识别二维码访问
				ctx.setFontSize(19 * this.multiple);
				ctx.setFillStyle('#333');
				ctx.fillText('长按识别二维码访问', left_gap, textTop + 110 * this.multiple);
				// // 平台名称
				ctx.setFontSize(16 * this.multiple);
				ctx.setFillStyle('#999');
				ctx.fillText(this.vuex_config.sitename, left_gap, textTop + 150 * this.multiple);
				// // 二维码
				// #ifdef MP-WEIXIN
				let code_path = await this.writefile(codeUrl);			
				ctx.drawImage(code_path, this.width / 2 - 150 * this.multiple, textTop + 88 * this.multiple, 120 * this.multiple, 120 * this.multiple);
				// #endif
				// #ifndef MP-WEIXIN
				ctx.drawImage(codeUrl, this.width / 2 - 150 * this.multiple, textTop + 88 * this.multiple, 120 * this.multiple, 120 * this.multiple);
				// #endif
				ctx.draw(true, () => {
					// canvas画布转成图片并返回图片地址
					uni.canvasToTempFilePath(
						{
							canvasId: 'poster',
							width: this.width / 2,
							height: this.height / 2,
							success: res => {
								this.posterImgs = res.tempFilePath;
								console.log('海报制作成功！');
							},
							fail: err => {
								console.log(err);
							}
						},
						this
					);
					uni.hideLoading();
				});
			} catch (e) {
				this.hide();
				this.$u.toast(e);
			}
		},
		// #ifdef MP-WEIXIN
		writefile(base64data) {
			return new Promise((resolve, reject) => {
				const [, format, bodyData] = /data:image\/(\w+);base64,(.*)/.exec(base64data) || [];
				if (!format) {
					reject(new Error('ERROR_BASE64SRC_PARSE'));
				}
				const fsm = wx.getFileSystemManager();
				const FILE_BASE_NAME = 'tmp_base64src';
				const filePath = `${wx.env.USER_DATA_PATH}/${FILE_BASE_NAME}.${format}`;
				const buffer = wx.base64ToArrayBuffer(bodyData);
				fsm.writeFile({
					filePath,
					data: buffer,
					encoding: 'binary',
					success() {
						resolve(filePath);
					},
					fail() {
						reject(new Error('ERROR_BASE64SRC_WRITE'));
					}
				});
			});
		},
		// #endif
		//适配图片绘图
		drawImage(ctx, path) {
			if (this.imgWidth) {
				let w = (this.imgWidth - this.width / 2) / 2;
				ctx.drawImage(path, 0, 0, this.width / 2 + w, this.width / 2, -w, 0, this.width / 2 + w, this.width / 2);
			} else if (this.imgHeight) {
				let h = (this.imgHeight - this.width / 2) / 2 + 30;
				ctx.drawImage(path, 0, 0, this.width / 2, this.width / 2 + h, 0, -h, this.width / 2, this.width / 2 + h);
			} else {
				ctx.drawImage(path, 0, 0, this.width / 2, this.width / 2);
			}
		},
		//保存海报
		save() {
			// #ifdef H5
			this.$u.toast('长按保存到本地');
			// #endif
			// #ifdef MP-WEIXIN
			uni.showLoading({
				title: '海报下载中'
			});
			if (settingWritePhotosAlbum) {
				uni.getSetting({
					success: res => {
						if (res.authSetting['scope.writePhotosAlbum']) {
							uni.saveImageToPhotosAlbum({
								filePath: this.posterImgs,
								success: () => {
									uni.hideLoading();
									uni.showToast({
										title: '保存成功'
									});
								}
							});
						} else {
							uni.showModal({
								title: '提示',
								content: '请先在设置页面打开“保存相册”使用权限',
								confirmText: '去设置',
								cancelText: '算了',
								success: data => {
									if (data.confirm) {
										uni.hideLoading();
										uni.openSetting();
									}
								}
							});
						}
					}
				});
			} else {
				settingWritePhotosAlbum = true;
				uni.authorize({
					scope: 'scope.writePhotosAlbum',
					success: () => {
						uni.saveImageToPhotosAlbum({
							filePath: this.posterImgs,
							success: () => {
								uni.hideLoading();
								uni.showToast({
									title: '保存成功'
								});
							}
						});
					}
				});
			}
			// #endif
			// #ifdef APP-PLUS
			uni.showLoading({
				title: '海报下载中'
			});
			uni.saveImageToPhotosAlbum({
				filePath: this.posterImgs,
				success: () => {
					uni.hideLoading();
					uni.showToast({
						title: '保存成功'
					});
				}
			});
			// #endif
		}
	}
};
</script>

<style lang="scss" scoped>
.poster_canvas {
	position: fixed;
	top: -10000px;
	left: 0px;
}
.poster-img {
	width: calc(750rpx * 0.7);
	height: calc(1334rpx * 0.7);
	border-radius: 15rpx;
	overflow: hidden;
	image {
		width: 100%;
		height: 100%;
	}
}

.btn {
	background-color: #ffffff;
	padding: 15rpx 30rpx;
	border-radius: 10rpx;
	text-align: center;
	&:first-child {
		width: 30%;
	}
	&:last-child {
		margin-left: 15rpx;
		flex: 1;
	}
}
</style>
