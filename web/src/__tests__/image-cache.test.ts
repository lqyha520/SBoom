import 'fake-indexeddb/auto'
import { Blob as NativeBlob } from 'node:buffer'
import { beforeEach, expect, it, vi } from 'vitest'
import { manageImageCache, openImageCache } from '../image-cache'
import type { WorksheetImage } from '../image-generation'

const image = (id: string, size = 4): WorksheetImage => ({ request_id: id, blob: new NativeBlob(['x'.repeat(size)], { type: 'image/png' }) as Blob, mime_type: 'image/png', width: 1, height: 1, prompt: '' })
beforeEach(async () => {
  vi.stubGlobal('Blob', NativeBlob)
  const db = await openImageCache(); await db.clear('images'); db.close()
})

it('容量满时先清理旧历史，保留当前批次和其他账号', async () => {
  await manageImageCache('lc_u2_image_request', [], { image: image('other'), limit: 10 })
  await manageImageCache('lc_u1_image_request', [], { image: image('old'), limit: 10 })
  await manageImageCache('lc_u1_image_request', ['current'], { image: image('current'), limit: 10 })
  const result = await manageImageCache('lc_u1_image_request', ['current', 'new'], { image: image('new'), limit: 10 })
  expect(result).toMatchObject({ stored: true, removed: 1, bytes: 8, count: 2 })
  const db = await openImageCache()
  expect(await db.get('images', 'lc_u1_image_request:old')).toBeUndefined()
  expect(await db.get('images', 'lc_u1_image_request:current')).toBeDefined()
  expect(await db.get('images', 'lc_u2_image_request:other')).toBeDefined()
  db.close()
})

it('当前批次超过预算时拒绝缓存新文件，并发写入不会越过预算', async () => {
  const writes = await Promise.all(['a', 'b', 'c'].map(id => manageImageCache('owner', ['a', 'b', 'c'], { image: image(id), limit: 10 })))
  expect(writes.filter(result => result.stored)).toHaveLength(2)
  expect(await manageImageCache('owner', [])).toMatchObject({ bytes: 8, count: 2 })
})

it('手动清理只删除历史缓存，兼容旧版本条目且不改变请求记录', async () => {
  localStorage.setItem('owner', 'request-record')
  const db = await openImageCache()
  await db.put('images', image('legacy'), 'owner:legacy')
  await db.put('images', image('current'), 'owner:current')
  db.close()
  expect(await manageImageCache('owner', ['current'], { clearHistory: true })).toMatchObject({ bytes: 4, count: 1, removed: 1 })
  expect(localStorage.getItem('owner')).toBe('request-record')
})

it('账号或页面已失效时不写入、也不清理历史缓存', async () => {
  await manageImageCache('owner', [], { image: image('old'), limit: 10 })
  expect(await manageImageCache('owner', [], { image: image('new', 8), limit: 10, active: () => false })).toMatchObject({ bytes: 4, stored: false, removed: 0 })
})

it('当前批次已经放不下新图片时，不白白删除仍能恢复的历史图片', async () => {
  await manageImageCache('owner', [], { image: image('old', 2), limit: 10 })
  await manageImageCache('owner', ['current'], { image: image('current', 7), limit: 10 })
  expect(await manageImageCache('owner', ['current', 'new'], { image: image('new', 4), limit: 10 }))
    .toMatchObject({ bytes: 9, count: 2, stored: false, removed: 0 })
})
