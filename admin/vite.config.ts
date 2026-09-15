import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import ui from '@nuxt/ui/vite'
import { uiConfig } from '../ui/config.mts'

// 后端 FastAPI 默认端口（生产：同源；开发：Vite 代理）
const BACKEND = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  cacheDir: 'node_modules/.vite-admin',
  plugins: [vue(), ui({ router: false, colorMode: false, ui: uiConfig, icon: { clientBundle: { scan: true } } })],
  base: '/admin/', // 部署在 FastAPI 的 /admin 路径下
  server: {
    port: 5174,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
  },
})
