import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
export function normalizeTypes() {
  for (const name of ['components.d.ts', 'auto-imports.d.ts']) {
    const path = fileURLToPath(new URL('../' + name, import.meta.url))
    const source = readFileSync(path, 'utf8')
    const stable = source.replace(/(?:\.\/)?\.\.\/web\/node_modules\/\.pnpm\/[^'"\n]+?\/node_modules\/@nuxt\/ui\/dist\/runtime\//g, '@nuxt/ui/runtime/')
      .replace(/\.\/node_modules\/[^'"\n]*?@nuxt\/ui\/dist\/runtime\//g, '@nuxt/ui/runtime/')
    if (stable !== source) writeFileSync(path, stable)
  }
}
normalizeTypes()
