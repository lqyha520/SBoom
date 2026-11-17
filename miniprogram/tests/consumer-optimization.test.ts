import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'
import { parse } from 'vue/compiler-sfc'
import { createLatestRequest } from '../src/services/latest-request'
import { usePageLifecycle } from '../src/services/page-lifecycle'
import * as drafts from '../src/services/feedback-draft'
import { catalogShare, hidePrivateTimeline } from '../src/services/return-route'

const storage = new Map<string, unknown>()
let storageFails = false
const native = {
  $on() {}, $off() {}, stopPullDownRefresh() {}, showToast() {}, pageScrollTo() {},
  getStorageSync: (key: string) => storage.get(key),
  setStorageSync: (key: string, value: unknown) => { if (storageFails) throw Error('storage full'); storage.set(key, value) },
  removeStorageSync: (key: string) => { if (storageFails) throw Error('storage full'); storage.delete(key) },
}
Object.assign(globalThis, { uni: native })
const settle = async () => { for (let i = 0; i < 30; i++) await Promise.resolve() }
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done }); return { promise, resolve } }
function component(file: string, modules: Record<string, unknown>, expose: string, input: Record<string, any> = {}) {
  const hooks: Record<string, ((...args: any[]) => any)[]> = {}, scope = vue.effectScope(), exports: any = {}
  const props = vue.reactive(input)
  const source = parse(readFileSync(new URL('../src/' + file, import.meta.url), 'utf8')).descriptor.scriptSetup!.content
  scope.run(() => vm.runInNewContext(ts.transpileModule(source + '\nexports.page = {' + expose + '}', {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, {
    exports, uni: native, setTimeout, clearTimeout, defineProps: () => props, defineEmits: () => () => {},
    require: (id: string) => id === 'vue' ? { ...vue, onBeforeUnmount: (fn: () => void) => (hooks.dispose ||= []).push(fn) }
      : id === '@dcloudio/uni-app' ? Object.fromEntries(['onLoad', 'onShow', 'onHide', 'onUnload', 'onShareAppMessage', 'onShareTimeline', 'onPullDownRefresh'].map(name => [name, (fn: () => void) => (hooks[name] ||= []).push(fn)]))
      : modules[id] || (id.endsWith('/latest-request') ? { createLatestRequest } : id.endsWith('/feedback-draft') ? drafts
        : id.endsWith('/page-lifecycle') ? { usePageLifecycle, captureScroll() {} }
          : id.endsWith('/tabbar-overlay') ? { useTabBarOverlay() {} } : {}),
  }))
  return { page: exports.page, props, hook: (name: string, ...args: any[]) => Promise.all((hooks[name] || []).map(fn => fn(...args))),
    dispose() { hooks.dispose?.forEach(fn => fn()); hooks.onUnload?.forEach(fn => fn()); scope.stop() } }
}

function membershipFixture() {
  let failContact = true, failPlans = false, enabled = true, contacts = 0, plans = 0
  const app = component('components/MembershipSheet.vue', {
    '../services/session': { session: vue.reactive({ user: { id: 'reader' } }), refreshMembership: async () => {} },
    '../services/api': { errorMessage: (error: Error) => error.message },
    '../services/checkout': { iosRestricted: (allowed: boolean) => !allowed },
    '../services/experience': { fetchSupport: async () => { contacts++; if (failContact) throw Error('contact offline'); return { benefits: '资料权益' } } },
    '../services/growth': { fetchPlans: async () => { plans++; if (failPlans) throw Error('plans offline'); return { ios_enabled: enabled } } },
  }, 'restricted, plansKnown, plansError, contactError, loadContact, loadPlans, contact', { open: false })
  return { ...app, counts: () => [contacts, plans], configure: (options: { contact?: boolean; plans?: boolean; enabled?: boolean }) => {
    failContact = options.contact ?? failContact; failPlans = options.plans ?? failPlans; enabled = options.enabled ?? enabled
  } }
}
test('客服失败不误判iPhone开通能力，重试只读取失败部分', async () => {
  const app = membershipFixture()
  try {
    app.props.open = true; await settle()
    assert.equal(app.page.plansKnown.value, true); assert.equal(app.page.restricted.value, false)
    assert.match(app.page.contactError.value, /contact offline/)
    app.configure({ contact: false }); await app.page.loadContact()
    assert.equal(app.page.contactError.value, ''); assert.deepEqual(app.counts(), [2, 1])
    app.configure({ plans: true }); await app.page.loadPlans()
    assert.equal(app.page.plansKnown.value, false); assert.equal(app.page.restricted.value, false)
    assert.match(app.page.plansError.value, /plans offline/)
    assert.equal(app.page.contact.value.benefits, '资料权益')
    app.configure({ plans: false, enabled: false }); await app.page.loadPlans()
    assert.equal(app.page.restricted.value, true)
  } finally { app.dispose() }
})
test('关闭会员弹层取消配置读取，迟到结果不修改下一次开通能力', async () => {
  const plans = deferred<{ ios_enabled: boolean }>()
  const app = component('components/MembershipSheet.vue', {
    '../services/session': { session: vue.reactive({ user: { id: 'reader' } }) },
    '../services/api': { errorMessage: String },
    '../services/checkout': { iosRestricted: (enabled: boolean) => !enabled },
    '../services/experience': { fetchSupport: async () => ({}) },
    '../services/growth': { fetchPlans: () => plans.promise },
  }, 'plansKnown, plansLoading', { open: false })
  try {
    app.props.open = true; await settle(); app.props.open = false; await settle()
    plans.resolve({ ios_enabled: true }); await settle()
    assert.equal(app.page.plansKnown.value, false); assert.equal(app.page.plansLoading.value, false)
  } finally { app.dispose() }
})

function paperFixture() {
  const restored = deferred<boolean>(), personal = deferred<any>()
  const session = vue.reactive({ ready: false, error: '', user: null as { id: string } | null })
  const calls: boolean[] = []
  const cacheChecks: unknown[][] = []
  let cacheClears = 0
  const detail = { id: 'paper', title: '公开说明', can_view: true, can_download: false, favorite: false,
    assets: [{ kind: 'page', url: '/original' }], thumbnail_url: '/thumb' }
  const app = component('pages/paper/index.vue', {
    '../../services/session': { session, ensureSession: () => restored.promise },
    '../../services/api': { ApiError: Error, errorMessage: String, fetchCatalogPaper: (_id: string, options: { anonymous: boolean }) => { calls.push(options.anonymous); return options.anonymous ? Promise.resolve(detail) : personal.promise } },
    '../../services/paper-intent': { takePaperIntent: () => null },
    '../../services/assets': { clearAssetCache() { cacheClears++ }, cancelPdfDownload() {}, revalidateCatalogAssetCache(...args: unknown[]) { cacheChecks.push(args) } },
    '../../services/experience': { recordView: async () => {} },
  }, 'paper, verified, pages, cover, error, reconnectSession, previewOpen, reconnect')
  void app.hook('onLoad', { id: 'paper' })
  return { ...app, session, restored, personal, detail, calls, cacheChecks, cacheClears: () => cacheClears }
}
test('详情公开说明先于登录恢复，登录后重新核验权限且保留标题', async () => {
  const app = paperFixture()
  try {
    const showing = app.hook('onShow'); await settle()
    assert.equal(app.page.paper.value.title, '公开说明'); assert.deepEqual(app.calls, [true])
    assert.equal(app.page.verified.value, false); assert.equal(app.page.pages.value.length, 0)
    app.session.ready = true; app.session.user = { id: 'reader' }; app.restored.resolve(true); await showing; await settle()
    assert.deepEqual(app.calls, [true, false]); assert.equal(app.page.paper.value.title, '公开说明')
    app.personal.resolve({ ...app.detail, can_view: false, assets: [], thumbnail_url: null }); await settle()
    assert.equal(app.page.verified.value, true); assert.equal(app.page.cover.value, null); assert.equal(app.page.error.value, '')
  } finally { app.dispose() }
})
test('登录恢复失败保留公开说明和重连入口，不开放原稿操作', async () => {
  const app = paperFixture()
  try {
    const showing = app.hook('onShow'); await settle()
    app.session.ready = true; app.session.error = 'network offline'; app.restored.resolve(false); await showing
    assert.equal(app.page.paper.value.title, '公开说明'); assert.equal(app.page.verified.value, false)
    assert.equal(app.page.pages.value.length, 0); assert.deepEqual(app.calls, [true])
    app.session.error = ''; app.session.user = { id: 'reader' }
    const retry = app.page.reconnectSession(); await settle(); app.personal.resolve({ ...app.detail, can_view: true }); await retry
    assert.deepEqual(app.calls, [true, false]); assert.equal(app.page.verified.value, true); assert.equal(app.page.error.value, '')
  } finally { app.dispose() }
})
test('详情离开后登录恢复不触发旧页面的权限请求', async () => {
  const app = paperFixture()
  try {
    const showing = app.hook('onShow'); await settle(); await app.hook('onHide')
    app.session.user = { id: 'reader' }; app.session.ready = true; app.restored.resolve(true); await showing
    assert.deepEqual(app.calls, [true]); assert.equal(app.page.verified.value, false)
  } finally { app.dispose() }
})

test('详情按观看与下载权限核验缓存，网络恢复保留阅读器，关闭后合并刷新', async () => {
  const app = paperFixture()
  try {
    app.session.ready = true; app.restored.resolve(false); app.personal.resolve(app.detail)
    await app.hook('onShow'); await settle()
    assert.deepEqual(app.cacheChecks, [['paper', true, false]])
    assert.equal(app.cacheClears(), 0, '免费原图不能因 PDF 需会员而全量清空')
    app.page.previewOpen.value = true
    app.page.reconnect(); app.page.reconnect(); await settle()
    assert.equal(app.page.previewOpen.value, true); assert.equal(app.calls.length, 1)
    app.page.previewOpen.value = false; await settle()
    assert.equal(app.calls.length, 2, '关闭阅读器后只补一次详情核验')
    app.page.previewOpen.value = true; app.page.reconnect(); await app.hook('onHide'); await settle()
    assert.equal(app.calls.length, 2, '离开页面清除待补刷新')
  } finally { app.dispose() }
})

function feedbackFixture(send = async () => {}) {
  const session = vue.reactive({ user: { id: 'a' } })
  const app = component('subpages/support/index.vue', {
    '../../services/session': { session, ensureSession: async () => true },
    '../../services/api': { errorMessage: String },
    '../../services/return-route': { decodeParam: (value: unknown) => typeof value === 'string' ? value : '' },
    '../../services/experience': { feedbackKinds: ['correction', 'download', 'membership', 'other'].map(value => ({ value })),
      fetchSupport: async () => ({}), fetchFeedback: async () => ({ items: [], has_more: false }), submitFeedback: send },
  }, 'body, paper, kind, flushDraft, draftStatus, draftSaved, submit, clearDraft')
  return { ...app, session }
}
test('反馈草稿限制字段和七天期限，不跨账号或保存额外数据', () => {
  storage.clear()
  drafts.writeFeedbackDraft('a', { body: 'A'.repeat(2500), kind: 'download', paper: 'p', token: 'private' } as any)
  assert.equal(drafts.readFeedbackDraft('a')!.body.length, 2000)
  assert.equal('token' in drafts.readFeedbackDraft('a')!, false); assert.equal(drafts.readFeedbackDraft('b'), null)
  storage.set('lc-feedback-draft-v1:a', { body: '过期', updatedAt: Date.now() - 8 * 86400_000 })
  assert.equal(drafts.readFeedbackDraft('a'), null)
})
test('反馈重新进入恢复描述和关联资料，切换账号前保存旧草稿', async () => {
  storage.clear(); drafts.writeFeedbackDraft('a', { body: '打开文件失败', kind: 'download', paper: 'p' })
  const app = feedbackFixture()
  try {
    await app.hook('onLoad', {})
    assert.equal(app.page.body.value, '打开文件失败'); assert.equal(app.page.paper.value, 'p')
    app.page.body.value = '修改后的文件问题'; app.session.user = { id: 'b' }
    assert.equal(drafts.readFeedbackDraft('a')!.body, '修改后的文件问题'); assert.equal(app.page.body.value, '')
    app.page.body.value = '另一个账号的问题'; await app.hook('onHide')
    assert.equal(drafts.readFeedbackDraft('b')!.body, '另一个账号的问题')
  } finally { app.dispose() }
})
test('反馈存储失败可重试，成功提交后清理草稿', async () => {
  storage.clear(); const app = feedbackFixture()
  try {
    await app.hook('onLoad', { paper: 'p', kind: 'correction' }); app.page.body.value = '这里有一个错误'
    storageFails = true; app.page.flushDraft(); assert.equal(app.page.draftSaved.value, false)
    storageFails = false; app.page.flushDraft(); assert.equal(app.page.draftSaved.value, true)
    await app.page.submit(); assert.equal(drafts.readFeedbackDraft('a'), null); assert.equal(app.page.body.value, '')
  } finally { storageFails = false; app.dispose() }
})
test('反馈发送中离开仍清理已提交草稿，迟到成功不删除新的草稿', async () => {
  storage.clear(); const done = deferred<void>(), app = feedbackFixture(() => done.promise)
  try {
    await app.hook('onLoad', {}); app.page.body.value = '第一个提交的问题'
    const sending = app.page.submit(); await app.hook('onHide')
    drafts.writeFeedbackDraft('a', { body: '后来填写的新问题', kind: 'other', paper: '' })
    done.resolve(); await sending
    assert.equal(drafts.readFeedbackDraft('a')!.body, '后来填写的新问题')
  } finally { app.dispose() }
})
test('反馈在后台提交成功后返回页面不会恢复已提交内容', async () => {
  storage.clear(); const done = deferred<void>(), app = feedbackFixture(() => done.promise)
  try {
    await app.hook('onLoad', {}); app.page.body.value = '后台返回的反馈问题'
    const sending = app.page.submit(); await app.hook('onHide'); done.resolve(); await sending
    assert.equal(drafts.readFeedbackDraft('a'), null)
    await app.hook('onShow'); assert.equal(app.page.body.value, '')
  } finally { app.dispose() }
})
test('个人列表隐藏朋友圈菜单，单份公共资料好友分享仍打开资料详情', () => {
  const calls: any[] = []; Object.assign(globalThis, { wx: { hideShareMenu: (options: any) => calls.push(options) } })
  try {
    hidePrivateTimeline(); assert.deepEqual(calls, [{ menus: ['shareTimeline'] }])
    for (const page of ['favorites', 'downloads', 'recent']) {
      const source = readFileSync(new URL('../src/pages/' + page + '/index.vue', import.meta.url), 'utf8')
      assert.match(source, /onShow\(\(\) => \{ hidePrivateTimeline\(\)/); assert.doesNotMatch(source, /onShareTimeline/)
    }
    assert.equal(catalogShare({ target: { dataset: { paperId: 'p', paperTitle: '练习' } } }).path, '/pages/paper/index?id=p')
  } finally { Reflect.deleteProperty(globalThis, 'wx') }
})
