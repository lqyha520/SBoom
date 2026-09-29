import { normalizeTypes } from './scripts/normalize-types.mjs'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import ui from '@nuxt/ui/vite'
import { uiConfig } from '../ui/config.mts'

// 后端 FastAPI 默认端口（生产：同源；开发：Vite 代理）
const BACKEND = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  cacheDir: 'node_modules/.vite-admin',
  plugins: [{ name: 'stable-ui-types', closeBundle: normalizeTypes }, vue(), ui({ router: false, colorMode: false, experimental: { componentDetection: true }, ui: uiConfig, icon: { clientBundle: { scan: true } } })],
  resolve: { dedupe: ['vue'] },
  base: '/admin/', // 部署在 FastAPI 的 /admin 路径下
  server: {
    port: 5174,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rolldownOptions: { output: { codeSplitting: { groups: [
      { name: 'vendor-vue', test: /node_modules[\/](?:@vue[\/]|vue[\/])/, priority: 30 },
      { name: 'vendor-ui', test: /node_modules[\/](?:tailwind-merge[\/]|tailwind-variants[\/]|@nuxt[\/]ui[\/]dist[\/]runtime[\/](?:utils|composables)[\/])/, priority: 20 },
      { name: 'icons', test: /(?:virtual:nuxt-ui-icons|iconify-json)/, priority: 40 },
    ] } } },
  },
})
