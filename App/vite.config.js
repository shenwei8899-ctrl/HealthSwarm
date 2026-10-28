import { defineConfig, loadEnv } from 'vite'
import uniModule from '@dcloudio/vite-plugin-uni'

// The current DCloud compiler publishes a CommonJS interop wrapper under ESM.
const uni = uniModule.default || uniModule

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const appid = process.env.VITE_WECHAT_APPID || env.VITE_WECHAT_APPID || ''
  if (appid && !/^wx[0-9a-f]{16}$/i.test(appid)) throw new Error('VITE_WECHAT_APPID 必须是有效的小程序 AppID')
  return {
    // Keep minification bounded on development machines with little free memory.
    build: { terserOptions: { maxWorkers: 1 } },
    server: {
      proxy: {
        '/api': { target: process.env.VITE_HEALTH_API_PROXY || env.VITE_HEALTH_API_PROXY || 'http://127.0.0.1:15050', changeOrigin: true },
        '/commerce-api': {
          target: env.COMMERCE_PROXY_TARGET || 'http://127.0.0.1:18081',
          changeOrigin: true,
          rewrite: path => path.replace(/^\/commerce-api/, ''),
        },
      },
    },
    plugins: [uni(), {
      name: 'wechat-appid',
      generateBundle(_options, bundle) {
        if (process.env.UNI_PLATFORM !== 'mp-weixin' || !appid) return
        const asset = bundle['project.config.json']
        if (!asset || asset.type !== 'asset') return
        const project = JSON.parse(String(asset.source))
        project.appid = appid
        project.setting = { ...project.setting, urlCheck: true }
        asset.source = JSON.stringify(project, null, 2) + '\n'
      },
    }],
  }
})
