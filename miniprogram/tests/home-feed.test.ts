import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'
import { parse } from 'vue/compiler-sfc'
import { createLatestRequest } from '../src/services/latest-request'
import { homeSelection } from '../src/presentation'
import type { PaperList, PaperSummary } from '../src/types'

type Params = Record<string, string | number | boolean>
type HomeState = {
  loadPapers(reset?: boolean): Promise<void>; changePapers(): void; retryPapers(): void; byGrade(grade: string): void
  items: vue.Ref<PaperSummary[]>; cards: vue.ComputedRef<PaperSummary[]>; offset: vue.Ref<number>; error: vue.Ref<string>
}
const settle = async () => { for (let i = 0; i < 30; i++) await Promise.resolve() }
const rows = Array.from({ length: 9 }, (_, id) => ({ id: String(id), favorite: false } as PaperSummary))
function fixture(read: (params: Params) => Promise<PaperList>) {
  const calls: Params[] = [], hooks: Record<string, () => unknown> = {}, scrolls: number[] = []
  const scope = vue.effectScope(), exports: { state?: HomeState } = {}
  const modules: Record<string, unknown> = {
    vue,
    '@dcloudio/uni-app': Object.fromEntries(['onShow', 'onHide', 'onUnload', 'onPullDownRefresh', 'onShareAppMessage', 'onShareTimeline'].map(name => [name, (fn: () => unknown) => { hooks[name] = fn }])),
    '../../services/session': { session: vue.reactive({ ready: true, user: null, error: '' }), ensureSession: async () => false },
    '../../services/latest-request': { createLatestRequest },
    '../../services/api': { errorMessage: (cause: Error) => cause.message, fetchCatalog: async (params: Params) => { calls.push(params); return read(params) }, fetchCatalogSummary: async () => ({}), fetchSiteHome: async () => ({ banners: [] }) },
    '../../services/experience': { fetchTopics: async () => ({ items: [] }) },
    '../../services/page-lifecycle': { captureScroll: (save: (top: number) => void) => save(600) },
    '../../presentation': { homeSelection, subjectTone: () => '' },
  }
  const source = parse(readFileSync(new URL('../src/pages/home/index.vue', import.meta.url), 'utf8')).descriptor.scriptSetup!.content
  scope.run(() => vm.runInNewContext(ts.transpileModule(source + '\nexports.state = { loadPapers, changePapers, retryPapers, byGrade, items, cards, offset, error };', {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, {
    exports, require: (id: string) => modules[id] || {},
    uni: { stopPullDownRefresh() {}, $on() {}, $off() {}, pageScrollTo: ({ scrollTop }: { scrollTop: number }) => scrolls.push(scrollTop) },
  }))
  return { state: exports.state!, calls, hooks, scrolls, dispose() { hooks.onUnload(); scope.stop() } }
}
function page(params: Params, source = rows): PaperList {
  const start = params.cursor ? Number(String(params.cursor).slice(5)) : 0
  return { items: source.slice(start, start + 4), total: params.include_total ? source.length : null,
    has_more: start + 4 < source.length, next_cursor: start + 4 < source.length ? 'page-' + (start + 4) : null }
}

test('首页小批次按需换组能遍历后续资料，末组仅一条时仍可回到首组', async () => {
  const app = fixture(async params => page(params)), p = app.state
  try {
    await p.loadPapers()
    assert.deepEqual(Array.from(p.cards.value, item => item.id), ['0', '1'])
    p.changePapers(); await settle()
    assert.equal(p.cards.value[0].id, '2'); assert.equal(app.calls.length, 1, '第二组复用首屏缓存')
    p.changePapers(); await settle()
    assert.equal(p.cards.value[0].id, '4'); assert.equal(p.items.value.length, 4)
    p.changePapers(); await settle()
    assert.equal(p.cards.value[0].id, '6'); assert.equal(app.calls.length, 2)
    p.changePapers(); await settle()
    assert.deepEqual(Array.from(p.cards.value, item => item.id), ['8'])
    p.changePapers(); await settle()
    assert.equal(p.cards.value[0].id, '0')
    assert.deepEqual(app.calls.map(call => call.cursor), ['', 'page-4', 'page-8', ''])
    assert.ok(app.calls.every(call => call.limit === 4 && call.pagination === 'cursor'))
    assert.deepEqual(app.calls.map(call => call.include_total), [true, false, false, true])
  } finally { app.dispose() }
})

test('首页换组失败保留原卡片，重试继续同一后续游标', async () => {
  let fail = true
  const app = fixture(async params => {
    if (params.cursor && fail) { fail = false; throw new Error('offline') }
    return page(params)
  }), p = app.state
  try {
    await p.loadPapers(); p.changePapers(); p.changePapers(); await settle()
    assert.equal(p.cards.value[0].id, '2'); assert.equal(p.error.value, 'offline')
    p.retryPapers(); await settle()
    assert.equal(p.cards.value[0].id, '4'); assert.equal(p.error.value, '')
    assert.deepEqual(app.calls.map(call => call.cursor), ['', 'page-4', 'page-4'])
  } finally { app.dispose() }
})

test('详情返回保留后续推荐窗口、组内位置和滚动位置', async () => {
  const app = fixture(async params => page(params)), p = app.state
  try {
    await p.loadPapers(); p.changePapers(); p.changePapers(); await settle(); p.changePapers()
    assert.equal(p.cards.value[0].id, '6')
    app.hooks.onHide(); await app.hooks.onShow(); await settle()
    assert.equal(p.cards.value[0].id, '6')
    assert.equal(app.calls.at(-1)?.cursor, 'page-4')
    assert.equal(app.scrolls.at(-1), 600)
  } finally { app.dispose() }
})

for (const reason of ['invalid_cursor', 'empty']) test(`后续推荐${reason === 'empty' ? '全部下架' : '游标失效'}时有界地返回首组`, async () => {
  const app = fixture(async params => {
    if (params.cursor) {
      if (reason === 'invalid_cursor') throw Object.assign(new Error('expired'), { code: 'invalid_cursor' })
      return { items: [], total: null, has_more: false, next_cursor: null }
    }
    return page(params)
  }), p = app.state
  try {
    await p.loadPapers(); p.changePapers(); p.changePapers(); await settle()
    assert.equal(p.cards.value[0].id, '0'); assert.equal(p.error.value, '')
    assert.deepEqual(app.calls.map(call => call.cursor), ['', 'page-4', ''])
  } finally { app.dispose() }
})

test('切换年级重置推荐游标，旧换组请求不能覆盖新筛选', async () => {
  let resolveOld!: (value: PaperList) => void
  const app = fixture(params => params.cursor ? new Promise(resolve => { resolveOld = resolve }) : Promise.resolve(page(params))), p = app.state
  try {
    await p.loadPapers(); p.changePapers(); p.changePapers(); await settle()
    p.byGrade('小学二年级'); await settle()
    assert.equal(app.calls.at(-1)?.cursor, '')
    assert.equal(app.calls.at(-1)?.grade, '小学二年级')
    resolveOld(page({ cursor: 'page-4' })); await settle()
    assert.equal(p.cards.value[0].id, '0'); assert.equal(p.offset.value, 0)
  } finally { app.dispose() }
})
