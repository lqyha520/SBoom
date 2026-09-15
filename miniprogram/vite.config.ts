import { defineConfig, loadEnv } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'
import { fileURLToPath, URL } from 'node:url'

const uniPlugin = (uni as unknown as { default?: typeof uni }).default || uni

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [uniPlugin()],
    optimizeDeps: { exclude: ['@wot-ui/ui'] },
    css: { preprocessorOptions: { scss: { silenceDeprecations: ['legacy-js-api', 'import', 'global-builtin'] } } },
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    server: {
      host: '127.0.0.1',
      port: 5180,
      strictPort: true,
      proxy: { '/api': { target: env.VITE_BACKEND_URL || 'http://127.0.0.1:8000', changeOrigin: true } },
    },
  }
})
