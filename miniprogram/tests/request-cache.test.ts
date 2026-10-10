import * as sharedHttp from '../../shared/http'
import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { createLatestRequest } from '../src/services/latest-request'
import { createUnreadTracker } from '../src/services/unread-tracker'
import * as vue from 'vue'

function fixture() {
  const calls: any[] = []
  let now = 1000
  class Clock extends Date { static now() { return now } }
  const source = readFileSync(new URL('../src/services/api.ts', import.meta.url), 'utf8').replace(/import\.meta\.env/g, "({ VITE_API_BASE_URL: 'https://api.example', DEV: false })")
  const exports: any = {}
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, {
    exports, Date: Clock, require: (name: string) => name.endsWith('/shared/http') ? sharedHttp : ({ exerciseText: (value: string) => value }),
    uni: { request(options: any) { const call = { ...options, aborted: false }; calls.push(call); return { abort() { call.aborted = true; options.fail() } } } },
  })
  const reply = (index: number, value: unknown) => calls[index].success({ statusCode: 200, data: value })
  const growth: any = {}
  vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/services/growth.ts', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, { exports: growth, require: (name: string) => name === './api' ? exports : name === 'vue' ? vue : name === './unread-tracker' ? { createUnreadTracker } : {} })
  return { api: exports, growth, calls, reply, advance: (milliseconds: number) => { now += milliseconds } }
}

test('public metadata shares requests, clones cached values, and supports force refresh', async () => {
  const { api, calls, reply } = fixture()
  const first = api.fetchSiteHome(), second = api.fetchSiteHome()
  assert.equal(calls.length, 1)
  reply(0, { title: 'old' }); const one = await first; await second
  one.title = 'local edit'
  assert.equal((await api.fetchSiteHome()).title, 'old')
  const fresh = api.fetchSiteHome({ force: true }); assert.equal(calls.length, 2)
  reply(1, { title: 'new' }); assert.equal((await fresh).title, 'new')
})

test('公开启动读取不携带登录信息，登录恢复不会取消公开内容', async () => {
  const { api, calls, reply } = fixture()
  api.configureSession('old-token', 'old-owner')
  const reading = api.fetchCatalog({ limit: 12 }, { anonymous: true })
  assert.equal(calls[0].header.Authorization, undefined)
  assert.equal(calls[0].header['X-Mini-User'], undefined)
  api.configureSession('new-token', 'new-owner')
  assert.equal(calls[0].aborted, false)
  reply(0, { items: [{ id: 'public', favorite: false }], total: 1 })
  assert.equal((await reading).items[0].id, 'public')
  await assert.rejects(api.request('/api/v1/mini/me', 'GET', undefined, { anonymous: true }), /不支持公开读取/)
  await assert.rejects(api.request('/api/v1/catalog/papers', 'POST', {}, { anonymous: true }), /不支持公开读取/)
})

test('公开读取仍可取消，失败不会注销当前账号或污染个人摘要缓存', async () => {
  const { api, calls, reply } = fixture()
  let loggedOut = false
  api.unauthorizedHandler(() => { loggedOut = true })
  const scope = createLatestRequest()
  const pending = api.fetchSiteHome({ anonymous: true, scope: scope.begin() })
  const cancelled = assert.rejects(pending, /取消/)
  scope.invalidate(); await cancelled
  assert.equal(calls[0].aborted, true)
  const denied = api.fetchCatalogSummary({ anonymous: true })
  calls[1].success({ statusCode: 401, data: { detail: 'unauthorized' } })
  await assert.rejects(denied)
  assert.equal(loggedOut, false)
  const summary = api.fetchCatalogSummary()
  assert.equal(calls.length, 3)
  reply(2, { favorites: 3 }); assert.equal((await summary).favorites, 3)
})

test('only the last cancelled consumer aborts shared metadata; account changes abort private reads', async () => {
  const { api, calls, reply } = fixture()
  const a = createLatestRequest(), b = createLatestRequest()
  const first = api.fetchSiteHome({ scope: a.begin() }), second = api.fetchSiteHome({ scope: b.begin() })
  const cancelled = assert.rejects(first, /取消/)
  a.invalidate(); await cancelled; assert.equal(calls[0].aborted, false)
  reply(0, { title: 'home' }); await second
  const privateRequest = api.fetchCatalog()
  const expired = assert.rejects(privateRequest, /取消/)
  api.configureSession('new-token', 'new-owner'); await expired
  assert.equal(calls[1].aborted, true)
})

test('forced refresh does not join an older pending request or cache its late response', async () => {
  const { api, calls, reply } = fixture()
  const old = api.fetchSiteHome(), fresh = api.fetchSiteHome({ force: true })
  assert.equal(calls.length, 2)
  reply(1, { title: 'new' }); await fresh
  reply(0, { title: 'old' }); await old
  assert.equal((await api.fetchSiteHome()).title, 'new')
})

test('真实教学标签接口合并请求、缓存独立副本，强制刷新可更新', async () => {
  const { growth, calls, reply } = fixture()
  const first = growth.fetchTags(), second = growth.fetchTags()
  assert.equal(calls.length, 1)
  assert.ok(calls[0].url.endsWith('/api/v1/site/catalog-tags'))
  reply(0, { items: [{ id: 'tag', name: '教材' }] })
  const original = await first; await second; original.items[0].name = '本地编辑'
  assert.equal((await growth.fetchTags()).items[0].name, '教材')
  assert.equal(calls.length, 1)
  const fresh = growth.fetchTags({ force: true }); reply(1, { items: [] }); await fresh
  assert.equal((await growth.fetchTags()).items.length, 0)
})

test('浏览和已读等个人写操作保留公共缓存，私人统计短暂合并缓存', async () => {
  const { api, growth, calls, reply } = fixture()
  const home = api.fetchSiteHome(); reply(0, { title: 'home' }); await home
  for (const path of ['/api/v1/mini/events', '/api/v1/mini/history/paper', '/api/v1/mini/messages/read-all']) {
    const writing = api.request(path, 'POST'); reply(calls.length - 1, {}); await writing
    assert.equal((await api.fetchSiteHome()).title, 'home')
  }
  assert.equal(calls.filter(call => call.url.endsWith('/site/home')).length, 1)
  const first = api.fetchCatalogSummary(), second = api.fetchCatalogSummary()
  assert.equal(calls.filter(call => call.url.endsWith('/catalog/summary')).length, 1)
  reply(calls.length - 1, {}); await Promise.all([first, second])
  const tags = growth.fetchTags(); reply(calls.length - 1, { items: [] }); await tags
  api.configureSession('new', '2')
  const fresh = api.fetchSiteHome(); reply(calls.length - 1, { title: 'new account' }); await fresh
  assert.equal(calls.filter(call => call.url.endsWith('/site/home')).length, 2)
})

test('刷新一种公共配置不会让其他配置的在途结果失去缓存', async () => {
  const { api, growth, calls, reply } = fixture()
  const tags = growth.fetchTags(), home = api.fetchSiteHome({ force: true })
  reply(0, { items: [] }); reply(1, {}); await Promise.all([tags, home])
  await growth.fetchTags(); assert.equal(calls.length, 2)
})

test('公共缓存到期后重新读取，失效的旧响应不能回填缓存', async () => {
  const { api, calls, reply, advance } = fixture()
  const first = api.fetchSiteHome(); reply(0, { title: 'first' }); await first
  advance(60_001)
  const old = api.fetchSiteHome(); api.invalidateMetadata()
  const fresh = api.fetchSiteHome(); reply(2, { title: 'fresh' }); await fresh
  reply(1, { title: 'old' }); await old
  assert.equal((await api.fetchSiteHome()).title, 'fresh')
  assert.equal(calls.length, 3)
})


test('相同 token 补齐账号不会取消冷启动读取，个人缓存到期后刷新', async () => {
  const { api, calls, reply, advance } = fixture()
  api.configureSession('token')
  const reading = api.request('/api/v1/mini/me')
  const epoch = api.authGeneration()
  api.configureSession('token', 'reader')
  assert.equal(api.authGeneration(), epoch); assert.equal(calls[0].aborted, false)
  reply(0, { id: 'reader' }); await reading
  await api.request('/api/v1/mini/me'); assert.equal(calls.length, 1)
  advance(20_001)
  const fresh = api.request('/api/v1/mini/me'); assert.equal(calls.length, 2)
  reply(1, { id: 'reader' }); await fresh
})

test('401 使用共享错误类型保留关联 ID，并清除认证状态', async () => {
  const { api, calls } = fixture()
  let cleared = 0
  api.unauthorizedHandler(() => { cleared++ })
  const reading = api.fetchCatalog()
  calls[0].success({ statusCode: 401, header: { 'X-Correlation-ID': 'trace-123' }, data: { detail: { error: '登录过期', code: 'expired' } } })
  await assert.rejects(reading, (error: any) => error instanceof sharedHttp.ApiError && error.requestId === 'trace-123')
  assert.equal(cleared, 1)
})
