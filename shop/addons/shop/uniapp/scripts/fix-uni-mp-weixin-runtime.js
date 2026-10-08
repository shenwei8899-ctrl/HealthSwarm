const fs = require('fs')
const path = require('path')

const runtimePath = path.resolve(
  __dirname,
  '../node_modules/@dcloudio/uni-mp-weixin/dist/index.js'
)

const unsafeStatement = 'this.$vm.$mp.query = query; // 兼容 mpvue'
const safeStatement = [
  '// 微信基础库 3.x 中页面 onLoad 可能早于 uni-app 初始化 $mp。',
  '    // 先补齐兼容对象，避免 Cannot set property query of undefined。',
  '    if (!this.$vm.$mp) {',
  '      this.$vm.$mp = { data: {}, page: this };',
  '    }',
  '    this.$vm.$mp.query = query; // 兼容 mpvue'
].join('\n    ')

if (!fs.existsSync(runtimePath)) {
  throw new Error(`未找到微信小程序运行时：${runtimePath}`)
}

const source = fs.readFileSync(runtimePath, 'utf8')
if (source.includes(safeStatement)) {
  process.exit(0)
}
if (!source.includes(unsafeStatement)) {
  throw new Error('微信小程序运行时代码结构已变化，请更新兼容补丁')
}

fs.writeFileSync(runtimePath, source.replace(unsafeStatement, safeStatement))
console.log('已应用 uni-app 微信基础库 3.x 页面生命周期兼容补丁')
