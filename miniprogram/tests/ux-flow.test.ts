import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'
import { parse } from 'vue/compiler-sfc'
import { createLatestRequest } from '../src/services/latest-request'
import { catalogShare } from '../src/services/return-route'
import { paperExtent, paperAccess, downloadAccessHint } from '../src/presentation'

function component(file: string, modules: Record<string, unknown>, expose: string, props: Record<string, unknown> = {}, globals: Record<string, unknown> = {}) {
  const scope = vue.effectScope(), lifecycle: Record<string, () => void> = {}, events: unknown[][] = []
  const source = parse(readFileSync(new URL('../src/' + file, import.meta.url), 'utf8')).descriptor.scriptSetup!.content
  const exports: Record<string, any> = {}
  const state = vue.reactive(props)
  scope.run(() => vm.runInNewContext(ts.transpileModule(source + '\nexports.page = {' + expose + '}', { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, {
    exports, require: (id: string) => id === 'vue' ? { ...vue, getCurrentInstance: () => ({ proxy: {} }),
      onMounted: (fn: () => void) => { lifecycle.mount = fn }, onUnmounted: (fn: () => void) => { lifecycle.unmount = fn }, onBeforeUnmount() {} } : modules[id] || {},
    defineProps: () => state, withDefaults: (_value: unknown, defaults: object) => Object.assign(state, { ...defaults, ...props }),
    defineEmits: () => (...args: unknown[]) => events.push(args), defineExpose() {}, setTimeout, clearTimeout, ...globals,
  }))
  return { page: exports.page, props: state, events, mount: () => lifecycle.mount?.(), dispose: () => { lifecycle.unmount?.(); scope.stop() } }
}
async function settle() { for (let index = 0; index < 30; index++) await Promise.resolve() }

test('sideways gestures only reveal buttons; vertical scrolling, cancellation and disabled rows perform no action', async () => {
  const app = component('components/SwipeAction.vue', {}, 'handleTouchStart, handleTouchMove, handleTouchEnd, cancel, perform, blocksClick, currentX',
    { actions: [{ key: 'favorite' }, { key: 'download' }, { key: 'share' }], open: false, disabled: false })
  const touch = (x: number, y: number) => ({ touches: [{ clientX: x, clientY: y }] })
  try {
    app.page.handleTouchStart(touch(250, 100)); app.page.handleTouchMove(touch(200, 220)); app.page.handleTouchEnd()
    assert.equal(app.events.length, 0)
    app.page.handleTouchStart(touch(250, 100)); app.page.handleTouchMove(touch(190, 102)); app.page.handleTouchEnd()
    assert.deepEqual(app.events, [['update:open', true]])
    assert.equal(app.page.currentX.value, -210)
    assert.equal(app.page.blocksClick(), true, 'the synthetic tap after a swipe cannot open the paper')
    app.props.open = true; await vue.nextTick()
    app.page.perform('share')
    assert.deepEqual(app.events.slice(-2), [['action', 'share'], ['update:open', false]])
    app.props.open = false; await vue.nextTick(); app.events.length = 0
    app.page.handleTouchStart(touch(250, 100)); app.page.handleTouchMove(touch(20, 100)); app.page.cancel(); app.page.handleTouchEnd()
    assert.equal(app.events.length, 0)
    app.props.disabled = true; await vue.nextTick(); app.events.length = 0
    app.page.handleTouchStart(touch(250, 100)); app.page.handleTouchMove(touch(20, 100)); app.page.handleTouchEnd(); app.page.perform('favorite')
    assert.equal(app.events.length, 0)
  } finally { app.dispose() }
})

function catalogFixture(failTags = false) {
  const calls: Record<string, unknown>[] = [], scheduled = new Map<number, () => void>()
  let timerId = 0, metadataCalls = 0
  const modules = {
    '../services/api': { errorMessage: String, fetchCatalog: async (filters: Record<string, unknown>) => { calls.push(filters); return { items: [{ id: 'paper' }], total: 1, has_more: false } }, fetchCatalogSummary: async () => { metadataCalls++; return { grades: [], subjects: [], categories: [] } } },
    '../services/session': { session: vue.reactive({ user: { id: 'reader' } }), ensureSession: async () => true, requireLogin: () => true },
    '../services/preferences': { readPreferences: () => ({ grade: '', subject: '', history: [] }), writePreferences() {}, rememberSearch: (_value: unknown, q: string) => ({ history: [q] }) },
    '../services/latest-request': { createLatestRequest },
    '../services/navigation': { catalogSelection: vue.reactive({ revision: 0 }) },
    '../services/experience': { fetchTopics: async () => ({ items: [] }) },
    '../services/growth': { emptyTags: () => ({ textbook: '', term: '', unit: '', knowledge: '' }), tagKinds: [], fetchTags: async () => { if (failTags) throw Error('offline'); return { items: [] } } },
  }
  const app = component('components/CatalogList.vue', modules, 'activate, deactivate, searchInput, search, q, applyFilters, error, metadataError, loadMetadata, items', {}, {
    uni: { stopPullDownRefresh() {}, pageScrollTo() {} },
    setTimeout: (fn: () => void) => { scheduled.set(++timerId, fn); return timerId }, clearTimeout: (id: number) => scheduled.delete(id),
  })
  return { ...app, calls, scheduled, runTimers: () => { const tasks = [...scheduled.values()]; scheduled.clear(); tasks.forEach(fn => fn()) }, metadataCalls: () => metadataCalls, restoreTags: () => { failTags = false } }
}

test('typing is debounced, enter is immediate, filters are batched and leaving cancels pending input', async () => {
  const app = catalogFixture()
  try {
    await app.page.activate(); await settle(); assert.equal(app.calls.length, 1)
    app.page.searchInput.value = '数'; await vue.nextTick()
    app.page.searchInput.value = '数学'; await vue.nextTick()
    assert.equal(app.calls.length, 1); assert.equal(app.scheduled.size, 1)
    app.runTimers(); await settle()
    assert.deepEqual(app.calls.map(call => call.q), ['', '数学'])
    app.page.search('口算'); await settle()
    assert.deepEqual(app.calls.map(call => call.q), ['', '数学', '口算'])
    assert.equal(app.scheduled.size, 0)
    app.page.applyFilters({ grade: '二年级', category: 'daily', tags: { textbook: 'book', unit: 'unit' } }); await settle()
    assert.equal(app.calls.length, 4); assert.equal(app.calls[3]!.grade, '二年级'); assert.equal(app.calls[3]!.unit, 'unit')
    assert.equal(app.metadataCalls(), 1)
    app.page.searchInput.value = '尚未提交'; await vue.nextTick(); app.page.deactivate(); app.runTimers(); await settle()
    assert.equal(app.calls.length, 4)
  } finally { app.page.deactivate(); app.dispose() }
})

test('an optional filter failure leaves successful catalog results usable and retries separately', async () => {
  const app = catalogFixture(true)
  try {
    await app.page.activate(); await settle()
    assert.equal(app.page.items.value.length, 1); assert.equal(app.page.error.value, '')
    assert.equal(app.page.metadataError.value, '教学标签')
    app.restoreTags(); await app.page.loadMetadata(true)
    assert.equal(app.page.metadataError.value, ''); assert.equal(app.calls.length, 1)
  } finally { app.page.deactivate(); app.dispose() }
})

test('lazy thumbnails acquire files only near the viewport and release them when replaced or unmounted', async () => {
  const acquired: string[] = [], released: string[] = []
  let observe!: (value: { intersectionRatio: number }) => void
  const observer = { relativeToViewport() { return this }, observe(_selector: string, callback: typeof observe) { observe = callback }, disconnect() {} }
  const app = component('components/PrivateImage.vue', { '../services/assets': { acquireAsset: (src: string) => { acquired.push(src); return { ready: Promise.resolve(src), release: () => released.push(src), invalidate() {} } } } }, 'source', { src: '/first', lazy: true }, { uni: { createIntersectionObserver: () => observer } })
  assert.equal(acquired.length, 0)
  app.mount(); observe({ intersectionRatio: 0 }); assert.equal(acquired.length, 0)
  observe({ intersectionRatio: 1 }); await settle(); assert.deepEqual(acquired, ['/first'])
  app.props.src = '/second'; await settle(); assert.deepEqual(released, ['/first']); assert.equal(app.page.source.value, '/second')
  app.dispose(); assert.deepEqual(released, ['/first', '/second'])
  observe({ intersectionRatio: 1 }); await settle(); assert.equal(acquired.length, 2)
})

test('an observer callback queued before unmount cannot start a new file request', async () => {
  let acquired = 0, observe!: (value: { intersectionRatio: number }) => void
  const observer = { relativeToViewport() { return this }, observe(_selector: string, callback: typeof observe) { observe = callback }, disconnect() {} }
  const app = component('components/PrivateImage.vue', { '../services/assets': { acquireAsset: () => { acquired++; return { ready: Promise.resolve('/file'), release() {} } } } }, 'source', { src: '/file', lazy: true }, { uni: { createIntersectionObserver: () => observer } })
  app.mount(); app.dispose(); observe({ intersectionRatio: 1 }); await settle()
  assert.equal(acquired, 0)
})

test('native list sharing selects a public paper and cannot leak a private list route', () => {
  assert.equal(catalogShare({ target: { dataset: { paperId: 'paper-1', paperTitle: '分数练习' } } }).path, '/pages/paper/index?id=paper-1')
  assert.equal(catalogShare({ target: { dataset: { paperId: 'paper-1', paperTitle: '分数练习' } } }).title, '分数练习')
  assert.equal(catalogShare({}).path, '/pages/home/index')
  assert.equal(catalogShare({ target: { dataset: { paperId: '../favorites' } } }).path, '/pages/home/index')
})

test('imported files omit unknown counts and guest download copy declares VIP requirements', () => {
  assert.equal(paperExtent({ question_count: 0, page_count: 5 }), '5 页')
  assert.equal(paperExtent({ question_count: 12, page_count: 2 }), '12 题 · 2 页')
  assert.equal(paperExtent({ question_count: 0, page_count: 0 }), 'PDF 资料')
  assert.equal(paperExtent({ question_count: 0, page_count: 0, download_mode: 'external' }), '网盘资料')
  const access = { required_view: 'free', required_download: 'vip' } as const
  assert.equal(paperAccess(access), 'VIP 下载')
  assert.equal(downloadAccessHint(access), '可免费预览，下载需 VIP 会员')
})
