export function canvasExport(canvasId, component) {
  return new Promise((resolve, reject) => uni.canvasToTempFilePath({ canvasId, destWidth: 750, destHeight: 1000,
    fileType: 'png', success: result => resolve(result.tempFilePath), fail: () => reject(new Error('海报生成失败，请重试')) }, component))
}

export async function drawReferralPoster({ canvasId, component, cover, qrcode }) {
  const context = uni.createCanvasContext(canvasId, component)
  const info = src => new Promise((resolve, reject) => uni.getImageInfo({ src, success: resolve,
    fail: () => reject(new Error('海报图片读取失败，请重试')) }))
  const [hero, code] = await Promise.all([info(cover), info(qrcode)])
  context.setFillStyle('#faf6ff'); context.fillRect(0, 0, 375, 500)
  context.setFillStyle('#fff'); context.fillRect(15, 15, 345, 470)
  context.drawImage(hero.path, 15, 15, 345, 163)
  context.setTextAlign('center'); context.setFillStyle('#47255e'); context.setFontSize(18)
  context.fillText('分享给你一个家庭营养师', 187.5, 213)
  context.setFillStyle('#716779'); context.setFontSize(14)
  context.fillText('一起把每天吃什么安排好。', 187.5, 242)
  context.drawImage(code.path, 97.5, 262, 180, 180)
  context.setFillStyle('#63338b'); context.setFontSize(15)
  context.fillText('扫码开始使用', 187.5, 466)
  await new Promise(resolve => context.draw(false, resolve))
  return canvasExport(canvasId, component)
}

export function qrcodeFile(base64, code) {
  if (typeof base64 !== 'string' || !/^(iVBORw0KGgo|\/9j\/)/.test(base64) || base64.length > 1500000) throw new Error('小程序码返回无效，请重试')
  const jpeg=base64.startsWith('/9j/'),extension=jpeg?'jpg':'png'
  // #ifdef MP-WEIXIN
  return new Promise((resolve, reject) => {
    const filePath = uni.env.USER_DATA_PATH + '/friend-referral-' + code + '.' + extension
    uni.getFileSystemManager().writeFile({ filePath, data: base64, encoding: 'base64', success: () => resolve(filePath),
      fail: () => reject(new Error('小程序码保存失败，请重试')) })
  })
  // #endif
  // #ifndef MP-WEIXIN
  return Promise.resolve('data:image/'+(jpeg?'jpeg':'png')+';base64,' + base64)
  // #endif
}
