import { defineConfig } from 'vite'
import uniModule from '@dcloudio/vite-plugin-uni'

// The current DCloud compiler publishes a CommonJS interop wrapper under ESM.
const uni = uniModule.default || uniModule

export default defineConfig({
  plugins: [uni()],
})
