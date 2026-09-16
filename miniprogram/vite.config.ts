import { defineConfig, loadEnv, type Plugin } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'
import { fileURLToPath, URL } from 'node:url'

const uniPlugin = (uni as unknown as { default?: typeof uni }).default || uni

const weixinPageStyles: Plugin = {
  name: 'weixin-page-styles',
  apply: 'build',
  enforce: 'post',
  generateBundle: {
    order: 'post',
    handler(_options, bundle) {
      if (process.env.UNI_PLATFORM !== 'mp-weixin') return
      const manifest = bundle['app.json']
      if (manifest?.type !== 'asset') this.error('Missing WeChat app.json when generating page styles')
      const app = JSON.parse(typeof manifest.source === 'string' ? manifest.source : Buffer.from(manifest.source).toString('utf8')) as {
        pages?: string[]
        subPackages?: { root: string; pages: string[] }[]
      }
      const pages = [...(app.pages || []), ...(app.subPackages || []).flatMap(pkg => pkg.pages.map(page => `${pkg.root}/${page}`))]
      for (const page of pages) {
        const fileName = `${page}.wxss`
        // uni-app omits CSS for pages styled by shared components. DevTools can
        // still request those files during hot reload, so keep each page complete.
        if (!bundle[fileName]) this.emitFile({ type: 'asset', fileName, source: '/* Page styles are provided by shared components. */\n' })
      }
    },
  },
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [uniPlugin(), weixinPageStyles],
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
