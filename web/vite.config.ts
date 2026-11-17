import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import ui from '@nuxt/ui/vite'
import { fileURLToPath, URL } from 'node:url'
import { uiConfig } from '../ui/config.mts'

// 后端 FastAPI 默认端口
const BACKEND = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'
const gameIcons = ['store', 'bot', 'rocket', 'brain', 'pizza', 'scroll-text', 'book-marked', 'spell-check-2', 'shopping-basket', 'clock-3', 'grid-2x2', 'panels-top-left', 'star', 'layers-3', 'paintbrush', 'waypoints', 'puzzle', 'package', 'shapes', 'route', 'scale', 'flask-conical', 'flip-horizontal-2', 'scan-eye', 'music-2', 'sprout', 'trees', 'palette', 'apple', 'backpack', 'recycle', 'footprints', 'git-branch', 'map', 'mouse-pointer-2', 'notebook-text', 'search', 'shuffle', 'layout-grid', 'maximize-2', 'minimize-2', 'heart', 'arrow-down', 'x'].map(name => `lucide:${name}`)

export default defineConfig(({ command }) => ({
  cacheDir: 'node_modules/.vite-web',
  // Production builds consume tracked declarations without racing to rewrite them.
  // 游戏目录中的动态图标显式打包，避免首屏依赖外部图标服务。
  plugins: [vue(), ui({ dts: command === 'serve', router: false, colorMode: false, ui: uiConfig, experimental: { componentDetection: true }, icon: { clientBundle: { scan: true, icons: gameIcons } } })],
  resolve: {
    dedupe: ['vue'],
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
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: 'vendor-vue', test: /node_modules[\\/](?:@vue[\\/]|vue[\\/]|pinia[\\/])/, priority: 30 },
            { name: 'vendor-ui', test: /node_modules[\\/](?:tailwind-merge[\\/]|tailwind-variants[\\/]|@nuxt[\\/]ui[\\/]dist[\\/]runtime[\\/](?:utils|composables)[\\/])/, priority: 20 },
            { name: 'icons', test: /(?:virtual:nuxt-ui-icons|iconify-json)/, priority: 40 },
          ],
        },
      },
    },
    // 导出库已改动态 import，主包回归正常体积；不再调高告警阈值掩盖问题
  },
}))
