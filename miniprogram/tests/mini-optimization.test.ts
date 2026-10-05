import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'
import { parse } from 'vue/compiler-sfc'
import { usePageLifecycle } from '../src/services/page-lifecycle'
import { createLatestRequest } from '../src/services/latest-request'
import * as drafts from '../src/services/request-draft'
import { safeDestination } from '../src/services/return-route'

const storage = new Map<string, unknown>()
let storageFails = false
const native = {
  $on() {}, $off() {}, stopPullDownRefresh() {}, showToast() {},
  getStorageSync: (key: string) => storage.get(key),
  setStorageSync: (key: string, value: unknown) => { if (storageFails) throw Error('storage full'); storage.set(key, value) },
  removeStorageSync: (key: string) => { if (storageFails) throw Error('storage full'); storage.delete(key) },
}
Object.assign(globalThis, { uni: native })
const settle = async () => { for (let i = 0; i < 30; i++) await Promise.resolve() }

function component(file: string, modules: Record<string, unknown>, expose: string, input: Record<string, unknown> = {}) {
  const hooks: Record<string, ((...args: any[]) => unknown)[]> = {}, events: unknown[][] = [], scope = vue.effectScope()
  const props = vue.reactive(input), exports: Record<string, any> = {}
  const source = parse(readFileSync(new URL('../src/' + file, import.meta.url), 'utf8')).descriptor.scriptSetup!.content
  scope.run(() => vm.runInNewContext(ts.transpileModule(source + '\nexports.page = {' + expose + '}', {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, {
    exports, uni: native, setTimeout, clearTimeout, defineProps: () => props, defineOptions() {}, defineExpose() {},
    defineEmits: () => (...args: unknown[]) => events.push(args),
    require: (id: string) => id === 'vue' ? { ...vue, onBeforeUnmount: (fn: () => void) => (hooks.dispose ||= []).push(fn) }
      : id === '@dcloudio/uni-app' ? Object.fromEntries(['onLoad', 'onHide', 'onUnload', 'onShow', 'onReachBottom'].map(key => [key, (fn: () => void) => (hooks[key] ||= []).push(fn)]))
      : modules[id] || (id.endsWith('/page-lifecycle') ? { usePageLifecycle } : id.endsWith('/latest-request') ? { createLatestRequest } : id.endsWith('/tabbar-overlay') ? { useTabBarOverlay() {} } : {}),
  }))
  return { page: exports.page, props, events, hook: (name: string, ...args: unknown[]) => hooks[name]?.forEach(fn => fn(...args)), dispose() { hooks.dispose?.forEach(fn => fn()); scope.stop() } }
}

test('account statistics appear before unrelated requests settle, and retry only the failed section', async () => {
  let failMessages!: (cause: Error) => void, reads = 0, memberReads = 0, messageReads = 0
  const app = component('pages/account/index.vue', {
    '../../services/session': { session: vue.reactive({ user: { id: 'reader' } }), ensureSession: async () => true, refreshMembership: async () => { memberReads++ } },
    '../../services/api': { errorMessage: String, fetchCatalogSummary: async () => { reads++; return { favorites: 12, downloads: 8 } } },
    '../../services/growth': { refreshUnread: async () => { if (++messageReads === 1) await new Promise((_, reject) => { failMessages = reject }) } },
  }, 'load, summary, sectionErrors, sectionLoading')
  try {
    const pending = app.page.load()
    await settle()
    assert.equal(app.page.summary.value.favorites, 12)
    assert.equal(app.page.sectionLoading.messages, true)
    failMessages(Error('messages offline')); await pending
    assert.match(app.page.sectionErrors.messages, /messages offline/)
    assert.equal(app.page.sectionErrors.summary, '')
    await app.page.load('messages', true)
    assert.equal(app.page.sectionErrors.messages, '')
    assert.deepEqual([reads, memberReads, messageReads], [1, 1, 2])
  } finally { app.dispose() }
})

test('account change invalidates old statistics and errors', async () => {
  const session = vue.reactive({ user: { id: 'old' } })
  let finish!: (data: unknown) => void
  const app = component('pages/account/index.vue', {
    '../../services/session': { session, ensureSession: async () => true, refreshMembership: async () => {} },
    '../../services/api': { errorMessage: String, fetchCatalogSummary: () => new Promise(resolve => { finish = resolve }) },
    '../../services/growth': { refreshUnread: async () => {} },
  }, 'load, summary, sectionErrors')
  try {
    const pending = app.page.load(); await settle()
    session.user = { id: 'new' }
    finish({ favorites: 99 }); await pending
    assert.equal(app.page.summary.value, null)
    assert.equal(app.page.sectionErrors.summary, '')
  } finally { app.dispose() }
})

function batchFixture(confirm = async () => true, write = async () => {}) {
  const session = vue.reactive({ user: { id: 'reader' } })
  const calls: unknown[][] = []
  const app = component('components/FavoriteBatchActions.vue', {
    '../services/session': { session },
    '../services/api': { errorMessage: String },
    '../services/navigation': { confirmAction: confirm },
    '../services/experience': { batchFavorites: async (...args: unknown[]) => { calls.push(args); await write() }, fetchGroups: async () => ({ items: [] }) },
  }, 'apply, chooseGroup, busy, error, groups, groupOpen', { ids: ['a', 'b'] })
  return { ...app, session, calls }
}

test('batch removal requires confirmation and failure keeps the selection available for retry', async () => {
  let fail = true
  const app = batchFixture(async () => true, async () => { if (fail) throw Error('offline') })
  try {
    await app.page.apply('remove')
    assert.deepEqual(app.props.ids, ['a', 'b'])
    assert.match(app.page.error.value, /offline/)
    assert.equal(app.events.some(event => event[0] === 'completed'), false)
    fail = false
    await app.page.apply('remove')
    assert.equal(app.events.filter(event => event[0] === 'completed').length, 1)
    assert.equal(app.calls.length, 2)
  } finally { app.dispose() }
  const cancelled = batchFixture(async () => false)
  try { await cancelled.page.apply('remove'); assert.equal(cancelled.calls.length, 0) }
  finally { cancelled.dispose() }
})

test('batch confirmation cannot write after account change; hidden pages ignore late success', async () => {
  let confirm!: (value: boolean) => void
  const app = batchFixture(() => new Promise(resolve => { confirm = resolve }))
  try {
    const pending = app.page.apply('remove')
    app.session.user = { id: 'other' }; confirm(true); await pending
    assert.equal(app.calls.length, 0)
  } finally { app.dispose() }
  let finish!: () => void
  const hidden = batchFixture(async () => true, () => new Promise(resolve => { finish = resolve }))
  try {
    const pending = hidden.page.apply('assign', 'group')
    await settle(); hidden.hook('onHide'); finish(); await pending
    assert.equal(hidden.events.some(event => event[0] === 'completed'), false)
  } finally { hidden.dispose() }
})

test('request drafts are bounded, expire, and never cross accounts or retain extra fields', () => {
  storage.clear()
  const input = { title: 'A'.repeat(200), grade: '一年级', subject: '数学', details: 'B'.repeat(2000), token: 'private' }
  assert.equal(drafts.writeRequestDraft('a', input), true)
  assert.equal(drafts.readRequestDraft('a')!.title.length, 120)
  assert.equal(drafts.readRequestDraft('a')!.details.length, 1000)
  assert.equal('token' in drafts.readRequestDraft('a')!, false)
  assert.equal(drafts.readRequestDraft('b'), null)
  assert.equal(drafts.readRequestDraft(''), null)
  drafts.writeRequestDraft('grade-only', { title: '', grade: '小学一年级', subject: '数学', details: '' })
  assert.equal(drafts.readRequestDraft('grade-only')!.grade, '小学一年级')
  storage.set('lc-resource-draft-v1:a', { ...input, updatedAt: Date.now() - 8 * 86400_000 })
  assert.equal(drafts.readRequestDraft('a'), null)
  storageFails = true
  try { assert.equal(drafts.writeRequestDraft('a', input), false) } finally { storageFails = false }
})

test('request page restores drafts, flushes on hide, isolates account changes and clears successful submissions', async () => {
  storage.clear()
  drafts.writeRequestDraft('a', { title: '原有需求', grade: '小学一年级', subject: '数学', details: '详细描述' })
  const session = vue.reactive({ user: { id: 'a' } })
  const jobs: Promise<unknown>[] = []
  const app = component('subpages/requests/index.vue', {
    '../../services/session': { session },
    '../../services/request-draft': drafts,
    '../../services/return-route': { decodeParam: (value: unknown) => typeof value === 'string' ? value : '' },
    '../../services/consumer-page': { useConsumerPage: () => ({ busy: vue.ref(false), loading: vue.ref(false), error: vue.ref(''), act: (run: (valid: () => boolean) => Promise<void>) => jobs.push(run(() => true)) }) },
    '../../services/growth': { submitRequest: async () => ({}), fetchRequests: async () => ({ items: [], has_more: false }) },
    '../../services/api': { fetchSiteHome: async () => ({ dictionaries: { grades: [], subjects: [] } }) },
  }, 'title, grade, subject, details, submit, flushDraft, draftStatus')
  try {
    app.hook('onLoad', {})
    assert.equal(app.page.title.value, '原有需求')
    app.page.title.value = '修改需求'; await vue.nextTick(); app.hook('onHide')
    assert.equal(drafts.readRequestDraft('a')!.title, '修改需求')
    session.user = { id: 'b' }
    assert.equal(app.page.title.value, '')
    app.page.title.value = '新的需求'; app.page.flushDraft()
    assert.equal(drafts.readRequestDraft('b')!.title, '新的需求')
    assert.equal(drafts.readRequestDraft('a')!.title, '修改需求')
    app.page.submit(); await Promise.all(jobs); await vue.nextTick(); app.hook('onUnload')
    assert.equal(drafts.readRequestDraft('b'), null)
  } finally { app.hook('onUnload'); app.dispose() }
})

test('fit to width resets native zoom without changing the selected page', () => {
  const app = component('components/PaperPreview.vue', {
    '../services/session': { session: { user: { id: 'reader' } } },
    '../services/chrome': { chromeBar: () => ({ inset: 0, height: 44 }) },
    '../services/reading-position': { readPosition: () => 2, rememberPosition() {} },
  }, 'resize, fitPage, current, scale, zoomedCurrent, resetKeys', { pages: Array.from({ length: 4 }, (_, id) => ({ id })), paperId: 'paper', release: 1 })
  try {
    app.page.resize({ detail: { scale: 3 } }, 2)
    assert.equal(app.page.zoomedCurrent.value, true)
    app.page.fitPage()
    assert.equal(app.page.current.value, 2)
    assert.equal(app.page.scale.value, 1)
    assert.equal(app.page.zoomedCurrent.value, false)
    assert.equal(app.page.resetKeys.value[2], 1)
  } finally { app.dispose() }
})

test('contact route accepts only the explicit contact flag', () => {
  assert.equal(safeDestination('/subpages/membership/index?contact=1'), '/subpages/membership/index?contact=1')
  assert.equal(safeDestination('/subpages/membership/index?contact=https://example.com'), '/pages/home/index')
})
