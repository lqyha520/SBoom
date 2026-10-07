import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const workspace = await readFile(new URL('../pnpm-workspace.yaml', import.meta.url), 'utf8')
const lock = await readFile(new URL('../pnpm-lock.yaml', import.meta.url), 'utf8')
const entries = [...workspace.matchAll(/^[ ]{2}"([^"]+)": "([^"]+)"$/gm)]
assert.ok(entries.length, '缺少有来源说明的依赖覆盖')
for (const [, selector, version] of entries) {
  const name = selector.slice(0, selector.lastIndexOf('@'))
  assert.ok(lock.includes(`${name}@${version}:`) || lock.includes(`${name}@${version}':`), `${selector} 覆盖目标已不在 lockfile 中，请重新审查并删除过期规则`)
  const index = workspace.indexOf(`  "${selector}"`)
  assert.match(workspace.slice(0, index).split('\n').at(-2) || '', /https:\/\//, `${selector} 必须注明来源`)
}
console.log(`已核验 ${entries.length} 个依赖覆盖目标及来源`)
