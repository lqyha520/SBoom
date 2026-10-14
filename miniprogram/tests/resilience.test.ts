import { usePageLifecycle } from '../src/services/page-lifecycle'
import { reconcileRows } from '../src/services/catalog-rows'
import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'
import { parse } from 'vue/compiler-sfc'
import { createUnreadTracker } from '../src/services/unread-tracker'
import { createLatestRequest } from '../src/services/latest-request'
import * as paperIntents from '../src/services/paper-intent'

function fixture(file: string, modules: Record<string, unknown>, expose = '', props: Record<string, unknown> = {}, globals: Record<string, unknown> = {}) {
  let source = readFileSync(new URL('../src/' + file, import.meta.url), 'utf8')
  if (file.endsWith('.vue')) source = parse(source).descriptor.scriptSetup!.content
  const scope = vue.effectScope(), exports: Record<string, any> = {}, events: unknown[][] = []
  const hooks: Record<string, (...args: any[]) => unknown> = {}
  const state = vue.reactive(props)
  scope.run(() => vm.runInNewContext(ts.transpileModule(source + '\nexports.state = {' + expose + '}', { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, {
    exports, require: (id: string) => id === 'vue' ? { ...vue, onMounted() {}, onBeforeUnmount() {} } : id === '@dcloudio/uni-app'
      ? Object.fromEntries(['onShow', 'onHide', 'onUnload', 'onLoad', 'onPullDownRefresh', 'onReachBottom', 'onShareAppMessage', 'onPageScroll'].map(name => [name, (cb: (...args: any[]) => unknown) => { hooks[name] = cb }])) : modules[id] || (id.endsWith('/page-lifecycle') ? { usePageLifecycle, captureScroll: (save: (top: number) => void) => save(600) } : id.endsWith('/catalog-rows') ? { reconcileRows } : id.endsWith('/page-navigation') ? { navigatePage: (options: unknown) => (globals.uni as any)?.navigateTo?.(options) } : {}),
    defineProps: () => state, withDefaults: (_: unknown, defaults: object) => Object.assign(state, { ...defaults, ...props }),
    defineEmits: () => (...args: unknown[]) => events.push(args), defineExpose() {}, setTimeout, clearTimeout, ...globals,
  }))
  return { exports, page: exports.state, props: state, events, hooks, dispose: () => scope.stop() }
}
function deferred<T>() { let resolve!: (value: T) => void, reject!: (cause: Error) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
async function settle() { for (let i = 0; i < 40; i++) await Promise.resolve() }

function sessionFixture(token = 'saved-token') {
  let generation = 0, removed = 0, calls = 0, unauthorized = () => {}
  let response: () => Promise<unknown> = async () => { throw Error('offline') }
  const app = fixture('services/session.ts', {
    './paper-intent': paperIntents,
    './api': { TOKEN_KEY: 'token', authGeneration: () => generation, configureSession: () => { generation++ }, errorMessage: String,
      unauthorizedHandler: (callback: () => void) => { unauthorized = callback }, request: () => { calls++; return response() } },
    './assets': { clearAssetCache() {} }, './growth': { inboxState: { unread: 0 } }, './experience': { recordEvent: async () => {} },
  }, '', {}, { uni: { getStorageSync: () => token, setStorageSync: (_key: string, value: string) => { token = value }, removeStorageSync: () => { removed++; token = '' } } })
  return { ...app, service: app.exports, removed: () => removed, calls: () => calls, unauthorized: () => unauthorized(), respond: (fn: typeof response) => { response = fn } }
}

test('logout clears local credentials immediately even while the network request never completes', async () => {
  const app = sessionFixture()
  try {
    app.respond(() => new Promise(() => {}))
    await app.service.logout()
    assert.equal(app.removed(), 1)
    assert.equal(app.service.session.user, null)
  } finally { app.dispose() }
})

test('network and server failures retain the saved session and a later retry restores it', async () => {
  const app = sessionFixture()
  try {
    const first = app.service.ensureSession(), second = app.service.ensureSession()
    assert.equal(first, second)
    assert.equal(await first, false); assert.equal(app.removed(), 0); assert.equal(app.service.session.ready, true)
    assert.match(app.service.session.error, /offline/)
    app.respond(async () => { throw Error('503') }); await app.service.ensureSession(); assert.equal(app.removed(), 0)
    app.respond(async () => ({ id: 'reader' }))
    assert.equal(await app.service.ensureSession(), true); assert.equal(app.service.session.user.id, 'reader'); assert.equal(app.service.session.error, '')
    await app.service.ensureSession(); assert.equal(app.calls(), 3)
  } finally { app.dispose() }
})

test('explicit unauthorized responses clear the credential and late responses cannot replace a new account', async () => {
  const app = sessionFixture()
  try {
    app.respond(async () => { app.unauthorized(); throw Error('401') })
    await app.service.ensureSession(); assert.equal(app.removed(), 1); assert.equal(app.service.session.error, '')
    app.service.acceptSession({ id: 'old' }, 'old-token'); app.service.session.ready = false
    const pending = deferred<unknown>(); app.respond(() => pending.promise)
    const restore = app.service.ensureSession(); await settle()
    app.service.acceptSession({ id: 'new' }, 'new-token'); pending.resolve({ id: 'old' }); await restore
    assert.equal(app.service.session.user.id, 'new')
  } finally { app.dispose() }
})

test('a guest initialization never leaves a completed promise blocking a future retry', async () => {
  const app = sessionFixture('')
  try {
    await app.service.ensureSession(); assert.equal(app.calls(), 0)
    app.service.acceptSession({ id: 'reader' }, 'token'); app.service.session.ready = false
    app.respond(async () => ({ id: 'reader' })); await app.service.ensureSession(); assert.equal(app.calls(), 1)
  } finally { app.dispose() }
})

function catalogFixture() {
  const calls: Record<string, any>[] = [], scrolls: number[] = []
  let response = async (filters: Record<string, any>) => ({ items: Array.from({ length: 20 }, (_, index) => ({ id: String(filters.offset + index), favorite: false })), total: 60, has_more: filters.offset < 40 })
  let mutate = async (_id: string, favorite: boolean) => ({ favorite })
  const app = fixture('components/CatalogList.vue', {
    '../services/api': { errorMessage: String, fetchCatalog: (filters: Record<string, any>) => { calls.push(filters); return response(filters) }, fetchCatalogSummary: async () => ({ grades: [], subjects: [], categories: [] }), favoriteCatalogPaper: (id: string, favorite: boolean) => mutate(id, favorite) },
    '../services/session': { session: vue.reactive({ user: { id: 'reader' } }), ensureSession: async () => true, requireLogin: () => true },
    '../services/preferences': { readPreferences: () => ({ grade: '', subject: '', history: [] }), writePreferences() {}, rememberSearch: (_: unknown, q: string) => ({ history: [q] }) },
    '../services/latest-request': { createLatestRequest }, '../services/navigation': { catalogSelection: vue.reactive({ revision: 0 }) },
    '../services/experience': { fetchTopics: async () => ({ items: [] }) },
    '../services/growth': { emptyTags: () => ({}), tagKinds: [], fetchTags: async () => ({ items: [] }) },
  }, 'activate, deactivate, refresh, favorite, items, changing, error, appendError, search, loading', {}, { uni: { stopPullDownRefresh() {}, pageScrollTo: ({ scrollTop }: { scrollTop: number }) => scrolls.push(scrollTop), showToast() {} } })
  return { ...app, calls, scrolls, respond: (fn: typeof response) => { response = fn }, mutate: (fn: typeof mutate) => { mutate = fn } }
}

test('failed pagination retries the same offset without dropping already loaded rows', async () => {
  const app = catalogFixture()
  try {
    await app.page.activate(); await settle(); await app.page.refresh(false)
    assert.equal(app.page.items.value.length, 40)
    app.respond(async () => { throw Error('offline') }); await app.page.refresh(false)
    assert.equal(app.page.items.value.length, 40); assert.equal(app.page.error.value, ''); assert.match(app.page.appendError.value, /offline/)
    app.respond(async () => ({ items: [{ id: '40', favorite: false }], total: 41, has_more: false })); await app.page.refresh(false)
    assert.deepEqual(app.calls.map(call => call.offset), [0, 20, 40, 40]); assert.equal(app.page.items.value.length, 41)
    app.page.search('分数'); await settle(); assert.equal(app.scrolls.at(-1), 0); assert.equal(app.calls.at(-1)!.offset, 0)
  } finally { app.page.deactivate(); app.dispose() }
})

test('favorites and pagination do not cancel each other and only the selected row is busy', async () => {
  const app = catalogFixture()
  try {
    await app.page.activate(); await settle()
    const next = deferred<any>(), favorite = deferred<{ favorite: boolean }>()
    app.respond(() => next.promise); app.mutate(() => favorite.promise)
    const append = app.page.refresh(false), mutation = app.page.favorite(app.page.items.value[0])
    assert.equal(app.page.changing.has('0'), true); assert.equal(app.page.changing.has('1'), false)
    next.resolve({ items: [{ id: '20', favorite: false }], total: 21, has_more: false }); await append
    favorite.resolve({ favorite: true }); await mutation
    assert.equal(app.page.items.value.length, 21); assert.equal(app.page.items.value[0].favorite, true); assert.equal(app.page.loading.value, false)
    const stale = deferred<any>(); app.respond(() => stale.promise)
    const refresh = app.page.refresh(); app.mutate(async () => ({ favorite: false })); await app.page.favorite(app.page.items.value[0])
    stale.resolve({ items: [{ id: '0', favorite: true }], total: 1, has_more: false }); await refresh
    assert.equal(app.page.items.value[0].favorite, false, 'an older list response cannot undo a completed favorite change')
  } finally { app.page.deactivate(); app.dispose() }
})

test('opening a busy row still respects swipe click suppression but does not wait for favorite completion', () => {
  const opened: string[] = [], checks: unknown[] = []
  const app = fixture('components/PaperRow.vue', { '../services/navigation': { openCatalogPaper: (id: string) => opened.push(id) } }, 'openPaper, swipe', { busy: true, paper: { id: 'paper' } })
  try {
    app.page.swipe.value = { blocksClick: (allow: boolean) => { checks.push(allow); return !allow } }; app.page.openPaper()
    assert.deepEqual(opened, ['paper']); assert.deepEqual(checks, [true])
    app.page.swipe.value = { blocksClick: () => true }; app.page.openPaper(); assert.equal(opened.length, 1)
  } finally { app.dispose() }
})

test('message navigation is immediate even while the read receipt is pending', () => {
  const actions: string[] = []
  const app = fixture('subpages/messages/index.vue', {
    '../../services/consumer-page': { useConsumerPage: () => ({ ticket: () => () => true }) },
    '../../services/message-reads': { markMessageRead: () => actions.push('read') },
    '../../services/growth': { messageDestination: () => '/pages/paper/index?id=paper' },
    '../../services/navigation': { visitDestination: (url: string) => actions.push(url) },
  }, 'open')
  try { app.page.open({ id: 'message', read_at: null }); assert.deepEqual(actions, ['read', '/pages/paper/index?id=paper']) } finally { app.dispose() }
})

test('read receipts retry after failure, deduplicate taps and stop updating after account changes', async () => {
  let generation = 1, fail = true, calls = 0
  const inboxState = vue.reactive({ unread: 3 })
  let reply: () => Promise<void> = async () => { calls++; if (fail) throw Error('offline'); inboxState.unread = 2 }
  const unreadTracker = createUnreadTracker(() => generation, count => { inboxState.unread = count })
  const app = fixture('services/message-reads.ts', { './api': { authGeneration: () => generation }, './growth': { inboxState, unreadTracker, readMessages: () => reply() } })
  const service = app.exports
  try {
    const message = { id: 'message', read_at: null }
    service.markMessageRead(message); service.markMessageRead(message)
    service.markMessageRead({ id: 'message', read_at: null })
    assert.equal(inboxState.unread, 2); await service.syncMessageReads(); assert.equal(calls, 1); assert.equal(service.readSync.pending, 1)
    assert.match(service.readSync.error, /暂未同步/)
    fail = false; await service.syncMessageReads(); assert.equal(calls, 2); assert.equal(service.readSync.pending, 0); assert.equal(inboxState.unread, 2)
    const waiting = deferred<void>(); reply = () => waiting.promise
    service.markMessageRead({ id: 'old', read_at: null }); await settle()
    generation++; inboxState.unread = 7; service.applyPendingReads([], 7)
    waiting.reject(Error('offline')); await settle()
    assert.equal(inboxState.unread, 7); assert.equal(service.readSync.error, ''); assert.equal(service.readSync.pending, 0)
  } finally { app.dispose() }
})

test('login recovery notifies the visible parent before the auth gate is removed', async () => {
  const session = vue.reactive({ user: null as null | { id: string }, ready: true, error: 'offline' })
  const app = fixture('components/AuthGate.vue', { '../services/session': { session, ensureSession: async () => { session.user = { id: 'reader' }; return true } } }, 'reconnect')
  try {
    await app.page.reconnect()
    assert.deepEqual(app.events, [['restored']])
  } finally { app.dispose() }
})

test('a server-confirmed read clears a queued receipt after its original response was lost', async () => {
  const inboxState = vue.reactive({ unread: 3 })
  const unreadTracker = createUnreadTracker(() => 1, count => { inboxState.unread = count })
  const app = fixture('services/message-reads.ts', { './api': { authGeneration: () => 1 }, './growth': { inboxState, unreadTracker, readMessages: async () => { throw Error('response lost') } } })
  try {
    app.exports.markMessageRead({ id: 'message', read_at: null }); await app.exports.syncMessageReads()
    app.exports.applyPendingReads([{ id: 'message', read_at: 1 }], 2)
    assert.equal(app.exports.readSync.pending, 0); assert.equal(app.exports.readSync.error, ''); assert.equal(inboxState.unread, 2)
  } finally { app.dispose() }
})

test('reading positions survive reopening, are isolated by account and release, and store no asset URLs', () => {
  let saved: unknown = []
  const app = fixture('services/reading-position.ts', {}, '', {}, { uni: { getStorageSync: () => saved, setStorage: ({ data, complete }: { data: unknown; complete: () => void }) => { saved = data; complete() } } })
  const service = app.exports
  try {
    service.rememberPosition('reader', 'paper', 1, 8)
    assert.equal(service.readPosition('reader', 'paper', 1, 12), 8); assert.equal(service.readPosition('reader', 'paper', 1, 4), 3)
    assert.equal(service.readPosition('other', 'paper', 1, 12), 0); assert.equal(service.readPosition('reader', 'paper', 2, 12), 0)
    assert.deepEqual(Object.keys((saved as object[])[0]!).sort(), ['key', 'page'])
    for (let index = 0; index < 70; index++) service.rememberPosition('reader', String(index), 1, 0)
    assert.equal((saved as unknown[]).length, 50)
  } finally { app.dispose() }
})

test('the reader restores a page, clamps navigation, resets zoom on turn and persists the chosen page', () => {
  const saved: number[] = []
  const app = fixture('components/PaperPreview.vue', { '../services/session': { session: { user: { id: 'reader' } } },
    '../services/chrome': { chromeBar: () => ({ inset: 24, height: 68 }) },
    '../services/reading-position': { readPosition: () => 4, rememberPosition: (_owner: string, _paper: string, _release: number, page: number) => saved.push(page) },
  }, 'current, scale, select, change, resize, resetKeys', { pages: Array.from({ length: 8 }, (_, index) => ({ id: String(index), page_number: index + 1 })), paperId: 'paper', release: 1 }, { uni: { getWindowInfo: () => ({ statusBarHeight: 24 }), getMenuButtonBoundingClientRect: () => ({ top: 28, height: 32 }) } })
  try {
    assert.equal(app.page.current.value, 4); app.page.resize({ detail: { scale: 2 } }, 4)
    app.page.select(5); assert.equal(app.page.scale.value, 1); assert.equal(app.page.current.value, 5)
    assert.equal(app.page.resetKeys.value[4], 1)
    app.page.select(8); assert.equal(app.page.current.value, 5)
    app.page.change({ detail: { current: 4, source: 'touch' } }); assert.deepEqual(saved, []); app.hooks.onHide(); assert.deepEqual(saved, [6])
    assert.deepEqual(Object.keys(app.page.resetKeys.value), ['4'])
    app.page.resize({ detail: { scale: 3 } }, 5)
    assert.equal(app.page.scale.value, 1)
    app.page.resize({ detail: { scale: 2 } }, 6)
    app.page.resize({ detail: { scale: 1 } }, 6)
    app.page.select(7)
    assert.equal(app.page.resetKeys.value[6], 1)
  } finally { app.dispose() }
})

test('the shared chrome bar clears the WeChat capsule and never collapses', () => {
  const devices = [
    { statusBarHeight: 24, top: 28, bottom: 60, height: 32 },
    { statusBarHeight: 47, top: 54, bottom: 86, height: 32 },
    { statusBarHeight: 20, top: 26, height: 32 },
  ]
  for (const device of devices) {
    const app = fixture('services/chrome.ts', {}, '', {}, { uni: { getWindowInfo: () => device, getMenuButtonBoundingClientRect: () => device } })
    try {
      const bar = app.exports.chromeBar()
      assert.equal(bar.inset, device.statusBarHeight)
      assert.ok(bar.height >= device.statusBarHeight + 44, 'the bar must fit a 44px control')
      assert.ok(bar.height >= (device.bottom || device.top + device.height) + 8, 'the bar must clear the capsule')
    } finally { app.dispose() }
  }
})

test('page chrome reserves the status bar and capsule even without a back button', () => {
  // 首页/我的/资料库(tab 态) 传 back=false；曾经把占位高度写成 `back ? bar.height : 0`，
  // 于是这些页面 height=0、内容顶到状态栏下面被胶囊挡住。
  const bar = { inset: 24, height: 68 }
  for (const back of [false, true]) {
    const app = fixture('components/PageChrome.vue', { '../services/chrome': { chromeBar: () => bar } }, 'inset, height', { back })
    try {
      assert.equal(app.page.inset.value, bar.inset)
      assert.equal(app.page.height.value, bar.height, 'page height must not depend on the back button')
      assert.ok(app.page.height.value >= bar.inset + 44, 'content must start below the status bar and capsule')
    } finally { app.dispose() }
  }
})

test('preview back closes the reader and page picker without leaving the detail route', () => {
  // 顶部栏几何由 services/chrome.ts 统一计算（见上一条用例），这里只验证预览页确实采用了它。
  for (const bar of [{ inset: 24, height: 68 }, { inset: 47, height: 94 }]) {
    const app = fixture('components/PaperPreview.vue', {
      '../services/session': { session: { user: { id: 'reader' } } },
      '../services/chrome': { chromeBar: () => bar },
      '../services/reading-position': { readPosition: () => 2 },
    }, 'current, close, jumpOpen, navigationTop, navigationHeight', {
      pages: Array.from({ length: 4 }, (_, index) => ({ id: String(index), page_number: index + 1 })), paperId: 'paper', release: 1,
    }, { uni: { getWindowInfo: () => bar, getMenuButtonBoundingClientRect: () => bar } })
    try {
      app.page.jumpOpen.value = true
      app.page.close()
      assert.deepEqual(app.events, [['close']])
      assert.equal(app.page.jumpOpen.value, false)
      assert.equal(app.page.current.value, 2)
      assert.equal(app.page.navigationTop.value, bar.inset)
      assert.equal(app.page.navigationHeight.value, bar.height)
      assert.ok(app.page.navigationTop.value + app.page.navigationHeight.value >= bar.inset + 44)
    } finally { app.dispose() }
  }
})

test('a new favorite group can be created in the detail sheet and assignment can retry without creating duplicates', async () => {
  let created = 0, assigned = 0, fail = true
  const app = fixture('pages/paper/index.vue', {
    '../../services/session': { session: vue.reactive({ user: { id: 'reader' } }) },
    '../../services/latest-request': { createLatestRequest }, '../../services/assets': { cancelPdfDownload() {} },
    '../../services/api': { errorMessage: String },
    '../../services/experience': { fetchGroups: async () => ({ items: [] }), createGroup: async (name: string) => { created++; return { id: 'group', name } }, assignGroup: async () => { assigned++; if (fail) throw Error('offline') } },
  }, 'paper, chooseGroup, groupOpen, groupName, createAndAssignGroup, groupItems, groupError, selectGroup', {}, { uni: { showToast() {}, stopPullDownRefresh() {} } })
  try {
    app.page.paper.value = { id: 'paper', favorite: true }
    await app.page.chooseGroup(); assert.equal(app.page.groupOpen.value, true)
    app.page.groupName.value = '复习'; await app.page.createAndAssignGroup()
    assert.equal(created, 1); assert.equal(assigned, 1); assert.equal(app.page.groupItems.value[0].name, '复习'); assert.match(app.page.groupError.value, /分组已创建/)
    assert.equal(app.page.groupName.value, ''); fail = false; await app.page.selectGroup('group')
    assert.equal(created, 1); assert.equal(assigned, 2); assert.equal(app.page.groupOpen.value, false)
  } finally { app.dispose() }
})

test('leaving the detail page during group creation prevents a late assignment or popup', async () => {
  const pending = deferred<any>(); let assigned = 0
  const app = fixture('pages/paper/index.vue', { '../../services/session': { session: vue.reactive({ user: { id: 'reader' } }) },
    '../../services/latest-request': { createLatestRequest }, '../../services/assets': { cancelPdfDownload() {} },
    '../../services/api': { errorMessage: String },
    '../../services/experience': { createGroup: () => pending.promise, assignGroup: async () => { assigned++ } },
  }, 'paper, groupOpen, groupName, createAndAssignGroup', {}, { uni: { stopPullDownRefresh() {} } })
  try {
    app.page.paper.value = { id: 'paper', favorite: true }; app.page.groupOpen.value = true; app.page.groupName.value = '复习'
    const create = app.page.createAndAssignGroup(); app.hooks.onHide!(); pending.resolve({ id: 'group', name: '复习' }); await create
    assert.equal(assigned, 0); assert.equal(app.page.groupOpen.value, false)
  } finally { app.dispose() }
})
