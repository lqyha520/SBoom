import assert from 'node:assert/strict'
import test from 'node:test'
import { reconcileRows } from '../src/services/catalog-rows'
import { categoryIcons, categoryIcon } from '../src/services/category-icons'
import { readFileSync } from 'node:fs'
import type { PaperSummary } from '../src/types'

test('详情返回只替换已变更行并保留列表对象引用', () => {
  const first = { id: 'a', favorite: false, tags: [] } as unknown as PaperSummary
  const second = { id: 'b', favorite: false, tags: [] } as unknown as PaperSummary
  const result = reconcileRows([first, second], [{ ...first }, { ...second, favorite: true }])
  assert.equal(result[0], first); assert.notEqual(result[1], second); assert.equal(result[1]!.favorite, true)
})

test('后台可选图标全部包含在离线字体子集中，未知名称回退', () => {
  const subset: string[] = JSON.parse(readFileSync(new URL('../src/static/icon-subset.json', import.meta.url), 'utf8'))
  for (const name of categoryIcons) assert.ok(subset.includes(name), name)
  assert.equal(categoryIcon('not-a-real-icon'), 'book')
})

test('window revalidation preserves only list activity dates, never stale access fields', () => {
  const old = { id: 'a', activity_at: 1791100000, can_view: true, can_download: true, thumbnail_url: '/old', favorite: true } as PaperSummary
  const fresh = { id: 'a', can_view: false, can_download: false, thumbnail_url: null, favorite: false } as PaperSummary
  const [result] = reconcileRows([old], [fresh])
  assert.equal(result.activity_at, old.activity_at)
  assert.equal(result.can_view, false)
  assert.equal(result.can_download, false)
  assert.equal(result.thumbnail_url, null)
  assert.equal(result.favorite, false)
  assert.equal(reconcileRows([old], [{ ...fresh, activity_at: 1791200000 }])[0].activity_at, 1791200000)
})
