import assert from 'node:assert/strict'
import test from 'node:test'
import { createBannerImages } from '../src/services/banner-images'
import { createFilePool } from '../src/services/file-pool'

const settle = () => new Promise<void>(resolve => setImmediate(resolve))

test('十张轮播只加载当前和下一张，翻到末尾预取首张，离开释放', async () => {
  const { images, downloads } = fixture()
  const banners = Array.from({ length: 10 }, (_, id) => ({ id: String(id), image_url: '/' + id }))
  images.sync(banners, 0); await settle()
  assert.deepEqual(downloads.map(item => item.url), ['/0', '/1'])
  images.sync(banners, 1); await settle()
  assert.deepEqual(downloads.map(item => item.url), ['/0', '/1', '/2'])
  images.sync(banners, 9); await settle()
  assert.deepEqual(downloads.map(item => item.url), ['/0', '/1', '/2', '/9', '/0'])
  images.clear()
  for (const entry of downloads) entry.resolve(entry.url)
  await settle()
})
function fixture() {
  const downloads: { url: string; resolve: (path: string) => void; reject: (error: Error) => void }[] = []
  const disposed: string[] = []
  const displayed: Record<string, string> = {}
  const pool = createFilePool(url => new Promise((resolve, reject) => downloads.push({ url, resolve, reject })), path => disposed.push(path))
  const images = createBannerImages(pool.acquire, (id, path) => { displayed[id] = path })
  return { images, downloads, disposed, displayed, pool }
}

test('a home refresh preserves an in-flight image and shares the same download', async () => {
  const { images, downloads, displayed } = fixture()
  images.sync([{ id: 'banner', image_url: '/image?v=1' }])
  await settle()
  images.sync([{ id: 'banner', image_url: '/image?v=1' }, { id: 'text-only', image_url: null }])
  downloads[0]!.resolve('first.png')
  await settle()
  assert.equal(downloads.length, 1)
  assert.equal(displayed.banner, 'first.png')
  images.clear()
})

test('replacing a banner image updates the same id and ignores an older late download', async () => {
  const { images, downloads, displayed, disposed, pool } = fixture()
  images.sync([{ id: 'banner', image_url: '/image?v=1' }])
  await settle()
  images.sync([{ id: 'banner', image_url: '/image?v=2' }])
  await settle()
  downloads[1]!.resolve('replacement.png')
  await settle()
  downloads[0]!.resolve('old.png')
  await settle()
  assert.equal(displayed.banner, 'replacement.png')
  assert.ok(disposed.includes('old.png'))
  images.clear()
  assert.ok(!disposed.includes('replacement.png')); pool.trim()
  assert.ok(disposed.includes('replacement.png'))
})

test('removing a photo or hiding a banner clears the displayed file and releases it', async () => {
  const { images, downloads, displayed, disposed, pool } = fixture()
  images.sync([{ id: 'a', image_url: '/a' }, { id: 'b', image_url: '/b' }])
  await settle()
  downloads[0]!.resolve('a.png'); downloads[1]!.resolve('b.png')
  await settle()
  images.sync([{ id: 'a', image_url: null }])
  assert.equal(displayed.a, '')
  assert.equal(displayed.b, '')
  assert.deepEqual(disposed, []); pool.trim()
  assert.deepEqual(disposed.sort(), ['a.png', 'b.png'])
})

test('failed downloads and invalid decoded images can be retried on the next refresh', async () => {
  const { images, downloads, displayed, disposed, pool } = fixture()
  const banners = [{ id: 'a', image_url: '/a' }]
  images.sync(banners); await settle()
  downloads[0]!.reject(new Error('offline')); await settle()
  assert.equal(displayed.a, '')
  images.sync(banners); await settle()
  downloads[1]!.resolve('broken.png'); await settle()
  images.fail('a', 'broken.png')
  assert.equal(displayed.a, '')
  assert.ok(disposed.includes('broken.png'))
  images.sync(banners); await settle()
  downloads[2]!.resolve('good.png'); await settle()
  images.fail('a', 'broken.png')
  assert.equal(displayed.a, 'good.png')
  images.clear()
})

test('leaving before a download completes never restores the old banner', async () => {
  const { images, downloads, displayed, disposed, pool } = fixture()
  images.sync([{ id: 'a', image_url: '/a' }]); await settle()
  images.clear()
  downloads[0]!.resolve('late.png'); await settle()
  assert.equal(displayed.a, '')
  assert.deepEqual(disposed, ['late.png'])
})
