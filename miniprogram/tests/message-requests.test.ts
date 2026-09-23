import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'
import { parse } from 'vue/compiler-sfc'
import { createUnreadTracker } from '../src/services/unread-tracker'
import type { ConsumerTicket } from '../src/services/consumer-page'

const settle = async () => { for (let i = 0; i < 20; i++) await Promise.resolve() }
function runtime() {
  type Options = { url: string; method: string; success(value: { statusCode: number; data: unknown }): void; fail(): void }
  const calls: (Options & { aborted: boolean })[] = []
  const hooks: Record<string, () => unknown> = {}
  const session = vue.reactive({ user: { id: 'reader' } as { id: string } | null })
  const uni = { stopPullDownRefresh() {}, $on() {}, $off() {}, request(options: Options) {
    const call = { ...options, aborted: false }; calls.push(call)
    return { abort() { call.aborted = true; options.fail() } }
  } }
  function module<T>(file: string, imports: Record<string, unknown>, expose = ''): T {
    let source = readFileSync(new URL('../src/' + file, import.meta.url), 'utf8')
    if (file.endsWith('.vue')) source = parse(source).descriptor.scriptSetup!.content
    source = source.replace(/import\.meta\.env/g, "({ VITE_API_BASE_URL: 'https://api.example', DEV: false })")
    const exports = {}
    vm.runInNewContext(ts.transpileModule(source + '\n' + expose, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, {
      exports, uni, defineOptions() {}, require: (name: string) => name === 'vue' ? vue : name === '@dcloudio/uni-app'
        ? Object.fromEntries(['onLoad', 'onShow', 'onHide', 'onUnload', 'onPullDownRefresh', 'onReachBottom'].map(hook => [hook, (fn: () => unknown) => { hooks[hook] = fn }])) : imports[name] || {},
    })
    return exports as T
  }
  const api = module<typeof import('../src/services/api')>('services/api.ts', { '../presentation': { exerciseText: (value: string) => value } })
  const growth = module<typeof import('../src/services/growth')>('services/growth.ts', { './api': api, './unread-tracker': { createUnreadTracker } })
  const reads = module<typeof import('../src/services/message-reads')>('services/message-reads.ts', { './api': api, './growth': growth })
  const consumer = module<typeof import('../src/services/consumer-page')>('services/consumer-page.ts', { './api': api, './session': { session, ensureSession: async () => true } })
  return { api, growth, reads, consumer, session, module, hooks, calls,
    reply(index: number, data: unknown) { calls[index].success({ statusCode: 200, data }) },
  }
}

test('全部已读后，写入前和写入期间发起的迟到未读查询都不能恢复旧角标', async () => {
  const { growth, reply } = runtime()
  const before = growth.refreshUnread()
  const write = growth.readMessages()
  const during = growth.refreshUnread()
  reply(1, { unread: 0 }); await write
  reply(0, { unread: 5 }); reply(2, { unread: 4 }); await Promise.all([before, during])
  assert.equal(growth.inboxState.unread, 0)
  const fresh = growth.refreshUnread(); reply(3, { unread: 1 }); await fresh
  assert.equal(growth.inboxState.unread, 1, '后续新消息仍可增加角标')
})

test('并发查询按发起顺序生效，切换账号后旧结果不能修改角标', async () => {
  const { api, growth, reply } = runtime()
  const first = growth.refreshUnread(), second = growth.refreshUnread()
  reply(1, { unread: 2 }); await second; reply(0, { unread: 5 }); await first
  assert.equal(growth.inboxState.unread, 2)
  const write = growth.readMessages()
  const rejected = assert.rejects(write, /登录状态已变化/)
  api.configureSession('new-token', 'other'); growth.inboxState.unread = 9
  reply(2, { unread: 0 }); await rejected
  assert.equal(growth.inboxState.unread, 9)
})

test('回执失败保留乐观已读，后续查询与重试不会重复扣减', async () => {
  const { growth, reads, calls, reply } = runtime()
  growth.inboxState.unread = 3
  reads.markMessageRead({ id: 'm1', read_at: null } as import('../src/services/growth').Message)
  await settle(); calls[0].fail(); await reads.syncMessageReads()
  assert.equal(growth.inboxState.unread, 2)
  const query = growth.refreshUnread(); reply(1, { unread: 3 }); await query
  assert.equal(growth.inboxState.unread, 2)
  const retry = reads.syncMessageReads(); await settle(); reply(2, { unread: 2 }); await retry
  assert.equal(growth.inboxState.unread, 2); assert.equal(growth.inboxState.pending, 0)
})

test('多条回执串行同步时保留其他待同步消息的乐观计数', async () => {
  const { growth, reads, reply } = runtime()
  growth.inboxState.unread = 5
  for (const id of ['one', 'two']) reads.markMessageRead({ id, read_at: null } as import('../src/services/growth').Message)
  await settle(); assert.equal(growth.inboxState.unread, 3)
  reply(0, { unread: 4 }); await settle(); assert.equal(growth.inboxState.unread, 3)
  reply(1, { unread: 3 }); await reads.syncMessageReads()
  assert.equal(growth.inboxState.unread, 3); assert.equal(growth.inboxState.pending, 0)
})

test('消息列表不等待回执，旧列表不会恢复已读标记，未读集合变化后从首页重新分页', async () => {
  const env = runtime(), { growth, reads, calls, reply } = env
  const scope = vue.effectScope()
  type State = { load(valid: ConsumerTicket, append?: boolean): Promise<void>; items: vue.Ref<import('../src/services/growth').Message[]>; unreadOnly: vue.Ref<boolean> }
  const component = scope.run(() => env.module<{ state: State }>('pages/messages/index.vue', {
    '../../services/growth': growth, '../../services/message-reads': reads,
    '../../services/consumer-page': { useConsumerPage: () => ({}) },
  }, 'exports.state = { load, items, unreadOnly };'))!.state
  const valid = Object.assign(() => true, { onCancel: () => () => {} })
  growth.inboxState.unread = 2
  reads.markMessageRead({ id: 'm1', read_at: null } as import('../src/services/growth').Message)
  await settle()
  try {
    const loading = component.load(valid)
    assert.equal(calls.length, 2, '回执未响应时，列表请求已经发出')
    reply(0, { unread: 1 }); await reads.syncMessageReads()
    reply(1, { items: [{ id: 'm1', read_at: null }], unread: 2, has_more: true })
    await settle(); reply(2, { available: false }); await loading
    assert.ok(component.items.value[0].read_at)
    assert.equal(growth.inboxState.unread, 1)
    component.unreadOnly.value = true
    const next = component.load(valid, true)
    assert.ok(!calls[3].url.includes('offset=1'), '回执改变未读集合后必须重置 offset')
    reply(3, { items: [{ id: 'm2', read_at: null }], unread: 1, has_more: false })
    await settle(); reply(4, { available: false }); await next
    assert.deepEqual(component.items.value.map(item => item.id), ['m2'])
  } finally { scope.stop() }
})

test('服务页隐藏、卸载和换账号会取消读取；返回重新请求且忽略旧结果', async () => {
  const { consumer, api, session, hooks, calls, reply } = runtime()
  const scope = vue.effectScope()
  let displayed = ''
  const page = scope.run(() => consumer.useConsumerPage(async valid => {
    const value = await api.request<{ title: string }>('/api/v1/mini/orders', 'GET', undefined, { scope: valid })
    if (valid()) displayed = value.title
  }, () => { displayed = '' }))!
  try {
    await hooks.onShow(); await settle(); hooks.onHide(); await settle()
    assert.equal(calls[0].aborted, true); assert.equal(page.error.value, '')
    await hooks.onShow(); await settle(); reply(1, { title: 'new' }); await settle()
    reply(0, { title: 'old' }); await settle(); assert.equal(displayed, 'new')
    const refreshing = page.refresh(); session.user = { id: 'other' }; await refreshing
    assert.equal(calls[2].aborted, true); assert.equal(displayed, '')
    const final = page.refresh(); hooks.onUnload(); await final
    assert.equal(calls[3].aborted, true)
  } finally { scope.stop() }
})

test('离页不会中断已提交的写操作，也不会发出其过期的后续读取', async () => {
  const { consumer, api, hooks, calls, reply } = runtime()
  const scope = vue.effectScope()
  const page = scope.run(() => consumer.useConsumerPage(async () => {}, () => {}))!
  try {
    await hooks.onShow(); await settle()
    const operation = page.act(async valid => {
      await api.request('/api/v1/mini/orders/fixture/cancel', 'POST', {}, { scope: valid })
      await api.request('/api/v1/mini/orders', 'GET', undefined, { scope: valid })
    })
    hooks.onHide(); assert.equal(calls[0].aborted, false)
    reply(0, {}); await operation
    assert.equal(calls.length, 1); assert.equal(page.error.value, '')
  } finally { hooks.onUnload(); scope.stop() }
})

for (const route of ['orders', 'requests', 'messages', 'membership', 'closure']) test(`${route} 实际页面将生命周期传入读取接口`, async () => {
  const env = runtime(), scope = vue.effectScope()
  try {
    scope.run(() => env.module(`pages/${route}/index.vue`, {
      '../../services/consumer-page': env.consumer, '../../services/growth': env.growth,
      '../../services/message-reads': env.reads,
      '../../services/session': { session: env.session, refreshMembership: (options: import('../src/services/api').ReadOptions) => env.api.request('/api/v1/mini/me', 'GET', undefined, options) },
      '../../services/experience': { fetchSupport: (options: import('../src/services/api').ReadOptions) => env.api.request('/api/v1/site/support', 'GET', undefined, options) },
    }))
    await env.hooks.onShow(); await settle()
    assert.ok(env.calls.length > 0)
    env.hooks.onHide(); await settle()
    assert.ok(env.calls.every(call => call.aborted), route + ' 不应留下后台读取')
  } finally { env.hooks.onUnload?.(); scope.stop() }
})
