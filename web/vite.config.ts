import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import ui from '@nuxt/ui/vite'
import { fileURLToPath, URL } from 'node:url'
import { uiConfig } from '../ui/config.mts'

// 后端 FastAPI 默认端口
const BACKEND = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  cacheDir: 'node_modules/.vite-web',
  plugins: [vue(), ui({ router: false, colorMode: false, ui: uiConfig, icon: { clientBundle: { scan: true } } })],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/admin': { target: process.env.VITE_ADMIN_URL || 'http://127.0.0.1:5174', changeOrigin: true, ws: true },
      '/api': { target: BACKEND, changeOrigin: true },
      '/health': { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    // 导出库已改动态 import，主包回归正常体积；不再调高告警阈值掩盖问题
  },
})
