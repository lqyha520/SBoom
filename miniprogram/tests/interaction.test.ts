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

test('favorite updates a loaded row without replacing pages; returning restores the loaded window and scroll', async () => {
  const calls: number[] = [], scroll: number[] = []
  const scope = vue.effectScope()
  const modules = {
    '../services/api': { errorMessage: String, favoriteCatalogPaper: async () => ({ favorite: true }),
      fetchCatalog: async ({ offset }: { offset: number }) => { calls.push(offset); return { items: Array.from({ length: 20 }, (_, index) => ({ id: String(offset + index), favorite: false })), total: 60, has_more: offset < 40 } },
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
    assert.deepEqual(calls, [0, 20, 0, 20])
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
    '@dcloudio/uni-app': Object.fromEntries(['onLoad', 'onShow', 'onHide', 'onUnload', 'onPullDownRefresh', 'onShareAppMessage'].map(key => [key, (callback: (...args: any[]) => void) => { callbacks[key] = callback }])),
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
    '@dcloudio/uni-app': Object.fromEntries(['onLoad', 'onShow', 'onHide', 'onUnload', 'onPullDownRefresh', 'onShareAppMessage'].map(key => [key, (cb: (...args: any[]) => void) => { callbacks[key] = cb }])),
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
    '@dcloudio/uni-app': Object.fromEntries(['onLoad', 'onShow', 'onHide', 'onUnload', 'onPullDownRefresh', 'onShareAppMessage'].map(key => [key, (cb: (...args: any[]) => void) => { callbacks[key] = cb }])),
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
