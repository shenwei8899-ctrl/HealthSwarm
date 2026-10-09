import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import uniModule from '@dcloudio/vite-plugin-uni'

const uni = uniModule.default || uniModule
const appRoot = fileURLToPath(new URL('.', import.meta.url))
const prototypeRoot = fileURLToPath(new URL('../../App/src', import.meta.url))
const prototypeComponents = ['AppNavBar.vue', 'AppIcon.vue'].map(name => ({
  importId: '@prototype/components/' + name,
  virtualPath: path.join(appRoot, 'src', '__prototype', name).replace(/\\/g, '/'),
  sourcePath: path.join(prototypeRoot, 'components', name),
}))

// uni-app 微信分块名必须相对自身输入目录。虚拟 ID 留在本工程，内容只读原型。
function prototypeComponentSource() {
  return {
    name: 'healthswarm-prototype-component-source',
    enforce: 'pre',
    resolveId(id) {
      const component = prototypeComponents.find(item => item.virtualPath === id.split('?')[0].replace(/\\/g, '/'))
      return component ? id : null
    },
    load(id) {
      if (id.includes('?')) return null
      const component = prototypeComponents.find(item => item.virtualPath === id.replace(/\\/g, '/'))
      return component ? fs.readFileSync(component.sourcePath, 'utf8') : null
    },
  }
}

function injectWechatAppId(appId) {
  return {
    name: 'healthswarm-wechat-appid',
    closeBundle() {
      if (process.env.UNI_PLATFORM !== 'mp-weixin' || !appId) return
      if (!/^wx[a-zA-Z0-9]{16}$/.test(appId)) {
        throw new Error('VITE_WECHAT_APPID 须为有效的微信小程序 AppID')
      }
      const output = process.env.UNI_OUTPUT_DIR
      if (!output || !path.resolve(output).startsWith(path.resolve(appRoot) + path.sep)) {
        throw new Error('小程序构建输出必须位于 agent/miniapp 内')
      }
      const target = path.join(output, 'project.config.json')
      const config = JSON.parse(fs.readFileSync(target, 'utf8'))
      config.appid = appId
      fs.writeFileSync(target, JSON.stringify(config, null, 2) + '\n')
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, appRoot, 'VITE_')
  const appId = process.env.VITE_WECHAT_APPID || env.VITE_WECHAT_APPID || ''
  // H5 的依赖预扫描直接读取物理路径；只有微信分块需要本工程内虚拟 ID。
  const componentAliases = process.env.UNI_PLATFORM === 'mp-weixin'
    ? prototypeComponents.map(component => ({ find: component.importId, replacement: component.virtualPath }))
    : []
  return {
    plugins: [prototypeComponentSource(), uni(), injectWechatAppId(appId)],
    resolve: {
      alias: [
        ...componentAliases,
        { find: '@prototype', replacement: prototypeRoot },
      ],
      dedupe: ['vue', '@dcloudio/uni-app'],
    },
    server: {
      host: '127.0.0.1',
      port: 5175,
      strictPort: true,
      fs: { allow: [appRoot, prototypeRoot] },
      proxy: {
        '/api': {
          target: process.env.VITE_HEALTH_API_PROXY || env.VITE_HEALTH_API_PROXY || 'http://127.0.0.1:15050',
          changeOrigin: true,
        },
      },
    },
  }
})
