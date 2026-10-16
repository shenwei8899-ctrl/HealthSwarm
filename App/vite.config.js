import { defineConfig, loadEnv } from 'vite'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import uniModule from '@dcloudio/vite-plugin-uni'

// The current DCloud compiler publishes a CommonJS interop wrapper under ESM.
const uni = uniModule.default || uniModule

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const appid = process.env.VITE_WECHAT_APPID || env.VITE_WECHAT_APPID || ''
  if (appid && !/^wx[0-9a-f]{16}$/i.test(appid)) throw new Error('VITE_WECHAT_APPID 必须是有效的小程序 AppID')
  return {
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
      closeBundle() {
        if (process.env.UNI_PLATFORM !== 'mp-weixin' || !appid) return
        const path = resolve(process.env.UNI_OUTPUT_DIR || 'dist/build/mp-weixin', 'project.config.json')
        const project = JSON.parse(readFileSync(path, 'utf8'))
        project.appid = appid
        project.setting = { ...project.setting, urlCheck: true }
        writeFileSync(path, JSON.stringify(project, null, 2) + '\n')
      },
    }],
  }
})
