import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'
import { parse } from 'vue/compiler-sfc'
import { createLatestRequest } from '../src/services/latest-request'
import { createFilePool } from '../src/services/file-pool'

function fixture(file: string, modules: Record<string, unknown>, expose: string, globals: Record<string, unknown>) {
  const source = parse(readFileSync(new URL('../src/' + file, import.meta.url), 'utf8')).descriptor.scriptSetup!.content
  const exports: Record<string, any> = {}
  vm.runInNewContext(ts.transpileModule(source + '\n' + expose, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, {
    exports, require: (id: string) => id === 'vue' ? { ...vue, onMounted() {}, onBeforeUnmount() {} } : modules[id] || {},
    setTimeout, clearTimeout, defineExpose() {}, defineProps: () => ({}), withDefaults: (_props: unknown, defaults: unknown) => defaults, ...globals,
  })
  return exports
}
async function settle() { for (let index = 0; index < 25; index++) await Promise.resolve() }

test('首页隐藏后关闭图片并响应内存警告，重新进入恢复加载并清理事件订阅', async () => {
  const hooks: Record<string, (...args: any[]) => any> = {}, events: Record<string, () => void> = {}
  const scope = vue.effectScope()
  const page = scope.run(() => fixture('pages/home/index.vue', {
    '@dcloudio/uni-app': Object.fromEntries(['onShow', 'onHide', 'onUnload', 'onPullDownRefresh', 'onShareAppMessage'].map(name => [name, (fn: (...args: any[]) => any) => { hooks[name] = fn }])),
    '../../services/session': { session: vue.reactive({ user: null }), ensureSession: async () => false },
    '../../services/latest-request': { createLatestRequest },
    '../../services/api': { fetchCatalog: async () => ({ items: [{ id: 'paper' }], total: 1 }), fetchCatalogSummary: async () => ({}), fetchSiteHome: async () => ({ banners: [{ id: 'banner' }] }) },
    '../../services/experience': { fetchTopics: async () => ({ items: [{ id: 'topic' }] }) },
    '../../presentation': { homeSelection: () => [], subjectTone: () => '' },
  }, 'exports.page = { site, items, imagesActive, collections }', { uni: { stopPullDownRefresh() {}, $on: (name: string, fn: () => void) => { events[name] = fn }, $off: (name: string) => { delete events[name] } } }))!.page
  try {
    await hooks.onShow(); await settle()
    assert.equal(page.imagesActive.value, true); assert.equal(page.items.value.length, 1)
    events['lc-memory-warning'](); assert.equal(page.items.value.length, 1)
    hooks.onHide(); assert.equal(page.imagesActive.value, false)
    events['lc-memory-warning'](); assert.equal(page.items.value.length, 0); assert.equal(page.site.value, null)
    await hooks.onShow(); await settle(); assert.equal(page.items.value.length, 1); assert.equal(page.imagesActive.value, true)
    hooks.onUnload(); assert.equal(Object.keys(events).length, 0)
  } finally { scope.stop() }
})

function boundedCatalog(duplicates = false) {
  const scope = vue.effectScope(), offsets: number[] = [], windows: number[] = [], scroll: number[] = []
  const session = vue.reactive({ user: { id: 'reader' } })
  let count = 1400
  const row = (id: number) => ({ id: String(id), revision: 1, favorite: false })
  const page = scope.run(() => fixture('components/CatalogList.vue', {
    '../services/api': { errorMessage: String,
      fetchCatalog: async ({ offset, limit }: { offset: number; limit: number }) => {
        offsets.push(offset)
        const items = Array.from({ length: Math.min(limit, Math.max(0, count - offset)) }, (_, index) => row(offset + index))
        if (duplicates && offset === 20) items[0] = row(19)
        return { items, total: count, has_more: offset + limit < count }
      },
      fetchCatalogWindow: async (ids: string[]) => { windows.push(ids.length); return { items: ids.map(id => row(Number(id))) } },
      fetchCatalogSummary: async () => ({ subjects: [], categories: [] }) },
    '../services/session': { session, ensureSession: async () => true, requireLogin: () => true },
    '../services/preferences': { readPreferences: () => ({ grade: '', subject: '', history: [] }), writePreferences() {} },
    '../services/latest-request': { createLatestRequest },
    '../services/navigation': { catalogSelection: vue.reactive({ revision: 0 }) },
    '../services/experience': { fetchTopics: async () => ({ items: [] }) },
    '../services/growth': { emptyTags: () => ({}), tagKinds: [], fetchTags: async () => ({ items: [] }) },
  }, 'exports.page = { activate, deactivate, refresh, turnWindow, items, nextOffset, windowStart, windowFull, q, memoryWarning, imagesActive, setScroll: value => { scrollTop = value } }', {
    uni: { stopPullDownRefresh() {}, pageScrollTo: (value: { scrollTop: number }) => scroll.push(value.scrollTop) },
  }))!.page
  return { page, session, offsets, windows, scroll, setTotal: (value: number) => { count = value }, close: () => { page.deactivate(); scope.stop() } }
}

test('超过千条的浏览保持每组最多 200 条，返回保留当前组和位置，隐藏页可释放内存', async () => {
  const fixture = boundedCatalog(), { page } = fixture
  try {
    await page.activate(); await settle()
    for (let group = 0; group < 6; group++) {
      for (let batch = 1; batch < 10; batch++) await page.refresh(false)
      assert.equal(page.items.value.length, 200)
      const requests = fixture.offsets.length
      await page.refresh(false)
      assert.equal(fixture.offsets.length, requests)
      if (group < 5) await page.turnWindow(1)
    }
    assert.equal(page.windowStart.value, 1000)
    assert.equal(page.nextOffset.value, 1200)
    page.setScroll(2500); page.deactivate()
    assert.equal(page.imagesActive.value, false)
    await page.activate(); await settle()
    assert.equal(page.imagesActive.value, true)
    assert.equal(page.items.value[0].id, '1000')
    assert.equal(page.items.value.length, 200)
    assert.equal(page.nextOffset.value, 1200)
    assert.deepEqual(fixture.windows, [200])
    assert.equal(fixture.scroll.at(-1), 2500)
    page.memoryWarning(); assert.equal(page.items.value.length, 200)
    page.deactivate(); page.memoryWarning(); assert.equal(page.items.value.length, 0)
    await page.activate(); await settle()
    assert.equal(page.items.value[0].id, '1000')
    assert.equal(page.items.value.length, 20)
    await page.turnWindow(-1)
    assert.equal(page.items.value[0].id, '800')
    page.q.value = '新筛选'; await settle()
    assert.equal(page.windowStart.value, 0)
    assert.equal(fixture.offsets.at(-1), 0)
    fixture.session.user = { id: 'other' }; await settle()
    assert.equal(page.windowStart.value, 0)
    assert.ok(page.items.value.length <= 20)
  } finally { fixture.close() }
})

test('翻页偏移按服务端行数推进，重复行不导致重复请求，删除最后一组后回到有效组', async () => {
  const fixture = boundedCatalog(true), { page } = fixture
  try {
    await page.activate(); await settle()
    await page.refresh(false); await page.refresh(false)
    assert.equal(page.items.value.length, 59)
    assert.deepEqual(fixture.offsets, [0, 20, 40])
    for (let i = 3; i < 10; i++) await page.refresh(false)
    assert.equal(page.windowFull.value, true)
    await page.turnWindow(1)
    assert.equal(page.items.value[0].id, '200')
    fixture.setTotal(180)
    await page.refresh()
    assert.equal(page.windowStart.value, 0)
    assert.equal(page.items.value[0].id, '0')
  } finally { fixture.close() }
})

test('detail return retains metadata, cancels old reads, and withholds private content until rights refresh', async () => {
  const callbacks: Record<string, Function> = {}
  let cancelled = 0, calls = 0, finish!: (value: unknown) => void
  const detail = { id: 'paper', title: '保留标题', can_view: true, can_download: true, thumbnail_url: '/thumb',
    snapshot: { private: true }, assets: [{ kind: 'page', url: '/original' }, { kind: 'pdf', url: '/pdf' }] }
  const scope = vue.effectScope()
  const page = scope.run(() => fixture('pages/paper/index.vue', {
    '@dcloudio/uni-app': Object.fromEntries(['onLoad', 'onShow', 'onHide', 'onUnload', 'onPullDownRefresh', 'onShareAppMessage', 'onPageScroll'].map(name => [name, (fn: Function) => { callbacks[name] = fn }])),
    '../../services/api': { ApiError: Error, errorMessage: String, fetchCatalogPaper: async (_id: string, options: any) => {
      options.scope.onCancel(() => { cancelled++ })
      if (++calls === 1) return detail
      return new Promise(resolve => { finish = resolve })
    } },
    '../../services/session': { session: vue.reactive({ user: null }), ensureSession: async () => false, requireLogin: () => false },
    '../../services/latest-request': { createLatestRequest },
    '../../services/assets': { cancelPdfDownload() {}, clearAssetCache() {} },
  }, 'exports.page = { load, paper, pages, cover, verified }', { uni: { stopPullDownRefresh() {}, pageScrollTo() {} } }))!.page
  try {
    callbacks.onLoad!({ id: 'paper' }); await page.load()
    assert.equal(page.cover.value, '/thumb')
    callbacks.onPageScroll!({ scrollTop: 600 }); callbacks.onHide!()
    assert.equal(page.paper.value.title, detail.title)
    assert.equal(page.paper.value.snapshot, null)
    assert.equal(page.pages.value.length, 0)
    await callbacks.onShow!(); await settle()
    assert.equal(page.verified.value, false)
    assert.equal(page.cover.value, null)
    callbacks.onHide!(); assert.ok(cancelled >= 2)
    finish(detail); await settle()
    assert.equal(page.verified.value, false)
    await callbacks.onShow!(); await settle()
    finish({ ...detail, can_view: false, can_download: false, assets: [], snapshot: null, thumbnail_url: null })
    await settle()
    assert.equal(page.verified.value, true)
    assert.equal(page.paper.value.can_view, false)
    assert.equal(page.pages.value.length, 0)
    callbacks.onUnload!(); assert.equal(page.paper.value, null)
  } finally { scope.stop() }
})

test('favorite updates a loaded row without replacing pages; returning restores the loaded window and scroll', async () => {
  const calls: number[] = [], scroll: number[] = []
  const scope = vue.effectScope()
  const modules = {
    '../services/api': { errorMessage: String, favoriteCatalogPaper: async () => ({ favorite: true }),
      fetchCatalog: async ({ offset }: { offset: number }) => { calls.push(offset); return { items: Array.from({ length: 20 }, (_, index) => ({ id: String(offset + index), favorite: false })), total: 60, has_more: offset < 40 } },
      fetchCatalogWindow: async (ids: string[]) => ({ items: ids.map(id => ({ id, favorite: id === '25' })) }),
      fetchCatalogSummary: async () => ({ subjects: [], categories: [] }) },
    '../services/session': { session: vue.reactive({ user: { id: 'reader' } }), ensureSession: async () => true, requireLogin: () => true },
    '../services/preferences': { readPreferences: () => ({ grade: '', subject: '', history: [] }), writePreferences() {} },
    '../services/latest-request': { createLatestRequest },
    '../services/navigation': { catalogSelection: vue.reactive({ revision: 0 }) },
    '../services/experience': { fetchTopics: async () => ({ items: [] }) },
    '../services/growth': { emptyTags: () => ({}), tagKinds: [], fetchTags: async () => ({ items: [] }) },
  }
  const page = scope.run(() => fixture('components/CatalogList.vue', modules,
    'exports.page = { activate, deactivate, refresh, favorite, items, setScroll: value => { scrollTop = value } }',
    { uni: { stopPullDownRefresh() {}, pageScrollTo: (value: { scrollTop: number }) => scroll.push(value.scrollTop) } }))!.page
  try {
    await page.activate(); await settle()
    await page.refresh(false)
    assert.equal(page.items.value.length, 40)
    await page.favorite(page.items.value[25])
    assert.equal(page.items.value[25].favorite, true)
    assert.deepEqual(calls, [0, 20])
    page.setScroll(1400); page.deactivate(); await page.activate(); await settle()
    assert.equal(page.items.value.length, 40)
    assert.deepEqual(calls, [0, 20, 0])
    assert.deepEqual(scroll, [1400])
  } finally { page.deactivate(); scope.stop() }
})

test('PDF retry retains the selected edition and exposes transfer progress', async () => {
  const calls: string[] = [], callbacks: Record<string, (...args: any[]) => void> = {}
  let attempt = 0
  class ApiError extends Error { status = 0; code = '' }
  const detail = { id: 'paper', title: '练习', can_view: true, can_download: true,
    assets: [{ kind: 'pdf', url: '/file', byte_size: 100 }], editions: [{ kind: 'original', label: '原稿' }, { kind: 'answers', label: '答案' }] }
  const scope = vue.effectScope()
  const page = scope.run(() => fixture('pages/paper/index.vue', {
    '@dcloudio/uni-app': Object.fromEntries(['onLoad', 'onShow', 'onHide', 'onUnload', 'onPullDownRefresh', 'onShareAppMessage', 'onPageScroll'].map(key => [key, (callback: (...args: any[]) => void) => { callbacks[key] = callback }])),
    '../../services/api': { ApiError, errorMessage: String, fetchCatalogPaper: async () => detail,
      requestCatalogDownload: async (_id: string, edition: string) => { calls.push(edition); return { url: '/pdf' } } },
    '../../services/session': { session: vue.reactive({ user: { id: 'reader' } }), ensureSession: async () => true, requireLogin: () => true },
    '../../services/latest-request': { createLatestRequest },
    '../../services/assets': { cancelPdfDownload() {}, clearAssetCache() {}, openPdf: async (_asset: unknown, _title: string, progress: (percent: number) => void) => {
      progress(48); assert.equal(page.downloadProgress.value, 48)
      if (++attempt === 1) throw new Error('网络断开')
    } },
    '../../presentation': { exerciseText: (title: string) => title },
    '../../services/experience': { recordView: async () => {}, recordEvent: async () => {} },
  }, 'exports.page = { load, download, edition, retryDownload, downloadProgress, error }', { uni: { stopPullDownRefresh() {} } }))!.page
  try {
    callbacks.onLoad!({ id: 'paper' }); await page.load()
    page.edition.value = 'answers'
    await page.download(); assert.equal(page.retryDownload.value, true)
    await page.load(); assert.equal(page.edition.value, 'answers'); assert.equal(page.retryDownload.value, false)
    await page.download(); assert.deepEqual(calls, ['answers', 'answers'])
    assert.equal(page.error.value, '')
    assert.equal(page.retryDownload.value, false)
  } finally { scope.stop() }
})

test('shared file progress reaches subscribers and stops after release', async () => {
  const updates: number[] = [], released: number[] = []
  let report!: (percent: number) => void, finish!: (file: string) => void
  const files = createFilePool((_key, progress) => { report = progress; return new Promise(resolve => { finish = resolve }) }, () => {})
  const first = files.acquire('pdf', value => updates.push(value))
  const second = files.acquire('pdf', value => released.push(value))
  await settle(); report(25); second.release(); report(90); finish('file')
  await first.ready
  assert.deepEqual(updates, [25, 90]); assert.deepEqual(released, [25])
  first.release()
})

test('网盘资料不依赖 PDF，获取后展示链接，复制失败可重试，离开页面清除链接', async () => {
  const callbacks: Record<string, (...args: any[]) => void> = {}, copied: string[] = []
  let pdfOpened = false
  const scope = vue.effectScope()
  const page = scope.run(() => fixture('pages/paper/index.vue', {
    '@dcloudio/uni-app': Object.fromEntries(['onLoad', 'onShow', 'onHide', 'onUnload', 'onPullDownRefresh', 'onShareAppMessage', 'onPageScroll'].map(key => [key, (cb: (...args: any[]) => void) => { callbacks[key] = cb }])),
    '../../services/api': { errorMessage: String, fetchCatalogPaper: async () => ({ id: 'link', title: '资料', can_view: true, can_download: true, download_mode: 'external', assets: [] }),
      requestCatalogDownload: async () => ({ kind: 'external', url: 'https://pan.example.com/a', extraction_code: 'Ab12' }) },
    '../../services/session': { session: vue.reactive({ user: { id: 'reader' } }), ensureSession: async () => true, requireLogin: () => true },
    '../../services/latest-request': { createLatestRequest },
    '../../services/assets': { cancelPdfDownload() {}, clearAssetCache() {}, openPdf: async () => { pdfOpened = true } },
    '../../presentation': { exerciseText: (title: string) => title },
    '../../services/experience': { recordView: async () => {}, recordEvent: async () => {} },
  }, 'exports.page = { load, download, copyLink, linkTarget, linkOpen, linkError, downloading }', {
    uni: { stopPullDownRefresh() {}, showToast() {}, setClipboardData: (options: { data: string; success(): void; fail(): void; complete(): void }) => {
      copied.push(options.data); if (copied.length === 1) options.fail(); else options.success(); options.complete()
    } },
  }))!.page
  try {
    callbacks.onLoad!({ id: 'link' }); await page.load(); await page.download()
    assert.equal(page.linkOpen.value, true); assert.equal(pdfOpened, false)
    assert.equal(page.downloading.value, false)
    page.copyLink(); assert.match(page.linkError.value, /复制失败/)
    page.copyLink(); assert.equal(page.linkError.value, '')
    assert.deepEqual(copied, ['https://pan.example.com/a\n提取码：Ab12', 'https://pan.example.com/a\n提取码：Ab12'])
    callbacks.onHide!(); assert.equal(page.linkTarget.value, null); assert.equal(page.linkOpen.value, false)
  } finally { scope.stop() }
})

test('网盘下载权限不足时显示会员入口，离开页面后迟到的链接不会展示', async () => {
  const callbacks: Record<string, (...args: any[]) => void> = {}
  let requests = 0, finish!: (value: unknown) => void, entitled = false
  const scope = vue.effectScope()
  const page = scope.run(() => fixture('pages/paper/index.vue', {
    '@dcloudio/uni-app': Object.fromEntries(['onLoad', 'onShow', 'onHide', 'onUnload', 'onPullDownRefresh', 'onShareAppMessage', 'onPageScroll'].map(key => [key, (cb: (...args: any[]) => void) => { callbacks[key] = cb }])),
    '../../services/api': { errorMessage: String, fetchCatalogPaper: async () => ({ id: 'link', title: '资料', can_view: true, can_download: entitled, download_mode: 'external', assets: [] }),
      requestCatalogDownload: async () => { requests++; return new Promise(resolve => { finish = resolve }) } },
    '../../services/session': { session: vue.reactive({ user: { id: 'reader' } }), ensureSession: async () => true, requireLogin: () => true },
    '../../services/latest-request': { createLatestRequest }, '../../services/assets': { cancelPdfDownload() {}, clearAssetCache() {} },
    '../../presentation': { exerciseText: (title: string) => title },
    '../../services/experience': { recordView: async () => {} },
  }, 'exports.page = { load, download, membershipOpen, linkTarget, linkOpen }', { uni: { stopPullDownRefresh() {} } }))!.page
  try {
    callbacks.onLoad!({ id: 'link' }); await page.load(); await page.download()
    assert.equal(page.membershipOpen.value, true); assert.equal(requests, 0)
    entitled = true; await page.load()
    const pending = page.download(); callbacks.onHide!()
    finish({ kind: 'external', url: 'https://pan.example.com/a', extraction_code: '' }); await pending
    assert.equal(page.linkOpen.value, false); assert.equal(page.linkTarget.value, null)
  } finally { scope.stop() }
})

for (const retainedCount of [20, 200]) test(`returning to ${retainedCount} catalog rows uses two requests and preserves scroll`, async () => {
  let reads = 0
  const scope = vue.effectScope(), scroll: number[] = []
  const rows = Array.from({ length: retainedCount }, (_, i) => ({ id: String(i), revision: 1, favorite: false, can_view: true }))
  const page = scope.run(() => fixture('components/CatalogList.vue', {
    '../services/api': { errorMessage: String,
      fetchCatalog: async () => { reads++; return { items: rows.slice(0, 20), total: retainedCount, has_more: retainedCount > 20 } },
      fetchCatalogWindow: async (ids: string[]) => { reads++; return { items: ids.map(id => rows[Number(id)]) } },
      fetchCatalogSummary: async () => ({ subjects: [], categories: [] }) },
    '../services/session': { session: vue.reactive({ user: { id: 'reader' } }), ensureSession: async () => true },
    '../services/preferences': { readPreferences: () => ({ grade: '', subject: '', history: [] }), writePreferences() {} },
    '../services/latest-request': { createLatestRequest },
    '../services/navigation': { catalogSelection: vue.reactive({ revision: 0 }) },
    '../services/experience': { fetchTopics: async () => ({ items: [] }) },
    '../services/growth': { emptyTags: () => ({}), tagKinds: [], fetchTags: async () => ({ items: [] }) },
  }, 'exports.page = { activate, deactivate, items, retain: rows => { items.value = rows; nextOffset.value = rows.length; scrollTop = 2000 } }', {
    uni: { stopPullDownRefresh() {}, pageScrollTo: (value: { scrollTop: number }) => scroll.push(value.scrollTop) },
  }))!.page
  try {
    await page.activate(); await settle(); page.retain(rows); page.deactivate(); reads = 0
    await page.activate(); await settle()
    assert.equal(reads, 2); assert.equal(page.items.value.length, retainedCount)
    assert.equal(scroll[scroll.length - 1], 2000)
  } finally { page.deactivate(); scope.stop() }
})
