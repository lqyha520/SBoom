import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// 生成声明使用公共导出路径，避免依赖升级后仍绑定旧 pnpm 缓存目录。
for (const name of ['components.d.ts', 'auto-imports.d.ts']) {
  const path = fileURLToPath(new URL('../' + name, import.meta.url))
  const source = readFileSync(path, 'utf8')
  const stable = source.replace(/\.\/node_modules\/[^'"\n]*?@nuxt\/ui\/dist\/runtime\//g, '@nuxt/ui/runtime/')
  if (stable !== source) writeFileSync(path, stable)
}
