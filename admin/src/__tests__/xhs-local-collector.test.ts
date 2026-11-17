// @vitest-environment node
import { EventEmitter } from 'node:events'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  createServer: vi.fn(), launch: vi.fn(), writeFile: vi.fn(), readFile: vi.fn(),
}))
vi.mock('node:http', () => ({ default: { createServer: mocks.createServer } }))
vi.mock('node:fs/promises', () => ({
  mkdir: vi.fn(), readFile: mocks.readFile, stat: vi.fn(async () => { throw Object.assign(new Error("missing"), { code: "ENOENT" }) }),
  appendFile: vi.fn(async () => {}), rename: vi.fn(), writeFile: mocks.writeFile,
}))
vi.mock('@playwright/test', () => ({ chromium: { launchPersistentContext: mocks.launch } }))

type Handler = (request: IncomingMessage, response: ServerResponse) => Promise<void>
let handler: Handler
const accountId = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
const task = { account_id: accountId, query: '一年级数学', period: 'week', sort_by: 'popular', note_limit: 10 }

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

function browser(browserState: { message?: string; empty?: boolean } = {}) {
  const option = { count: async () => 1, isVisible: async () => true, getAttribute: async () => 'tags active' }
  const options = { filter: () => ({ first: () => option }) }
  const sections = { filter: () => ({ first: () => ({ locator: () => options }) }) }
  const panel = { isVisible: async () => true, waitFor: vi.fn(), locator: () => sections, page: (): object => page }
  const filter = { hover: vi.fn(), count: async () => 1, locator: () => ({ first: () => panel }) }
  const cards = Array.from({ length: browserState.empty ? 0 : 10 }, (_, i) => ({
    note_id: `note-${i}`, title: '数学练习', likes_text: '10',
    url: `https://www.xiaohongshu.com/explore/note-${i}`,
  }))
  const pageEvents = new EventEmitter()
  const page = {
    on: pageEvents.on.bind(pageEvents), off: pageEvents.off.bind(pageEvents),
    isClosed: () => false, url: () => 'https://www.xiaohongshu.com/explore',
    close: vi.fn(async () => {}), bringToFront: vi.fn(), goto: vi.fn(), waitForTimeout: vi.fn(), evaluate: vi.fn(),
    getByText: () => ({ first: () => ({ count: async () => 0 }) }),
    locator: (selector: string) => {
      if (selector === 'body') return { innerText: async () => browserState.message || '公开搜索结果' }
      if (selector === '.filter') return { first: () => filter }
      if (selector === 'section.note-item') return { evaluateAll: async () => cards, allInnerTexts: async () => cards.map(card => card.title) }
      throw new Error(`Unexpected selector: ${selector}`)
    },
  }
  const events = new EventEmitter()
  return { newPage: async () => page, pages: () => [page], on: events.on.bind(events), close: vi.fn(async () => { events.emit('close') }) }
}

async function request(url: string, body?: unknown, origin = 'https://localhost') {
  const input = Object.assign(new EventEmitter(), {
    url, method: url === '/health' || url === '/accounts' || url.startsWith('/publisher/state') || url.startsWith('/jobs/') ? 'GET' : 'POST', headers: { origin, 'x-admin-capability': 'fixture-capability', 'content-type': 'application/json' },
  })
  const response = { writeHead: vi.fn(), end: vi.fn() }
  const done = handler(input as unknown as IncomingMessage, response as unknown as ServerResponse)
  await new Promise(resolve => setTimeout(resolve, 0))
  input.emit('data', Buffer.from(JSON.stringify(body ?? {})))
  input.emit('end')
  await done
  return { status: response.writeHead.mock.calls[0][0], body: JSON.parse(response.end.mock.calls[0][0] || '{}') }
}

beforeEach(async () => {
  vi.resetModules()
  vi.resetAllMocks()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ authorized: true }) }))
  vi.spyOn(process, 'on').mockReturnValue(process)
  vi.spyOn(console, 'log').mockImplementation(() => {})
  mocks.createServer.mockImplementation((listener: Handler) => {
    handler = listener
    return { listen: vi.fn(), on: vi.fn() }
  })
  mocks.launch.mockImplementation(async () => browser())
  mocks.readFile.mockImplementation(async filename => String(filename).endsWith('xhs-accounts.json')
    ? JSON.stringify({ version: 1, items: [{ id: accountId, origin: 'https://localhost', name: '测试账号', revision: 1 }] })
    : '{"enabled":true}')
  // @ts-expect-error The standalone Node entry point has no TypeScript declarations.
  await import('../../scripts/xhs-local-collector.mjs')
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('首次采集使用所选账号的可见浏览器并返回笔记', async () => {
  const result = await request('/collect', task)
  expect(result.status).toBe(200)
  expect(result.body.items).toHaveLength(10)
  expect(mocks.launch).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ headless: false }))
  expect((await request('/health')).body).toMatchObject({ busy: false, background: false })
})

it('笔记打开接口沿用所选账号，采集关闭时仍可打开，非法链接不放行', async () => {
  await request('/control', { enabled: false })
  const url = 'https://www.xiaohongshu.com/explore/65abcdef0123456789abcdef?xsec_token=fixture-token'
  expect((await request('/accounts/open-note', { account_id: accountId, url })).status).toBe(200)
  const context = await mocks.launch.mock.results[0]!.value
  expect(context.pages()[0].goto).toHaveBeenLastCalledWith(url, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  expect((await request('/accounts/open-note', { account_id: accountId, url: 'https://example.com/explore/note-test' })).status).toBe(400)
})

it('辅助窗口独立于采集开关；新接口继续限制来源', async () => {
  mocks.readFile.mockRejectedValue(Object.assign(new Error('missing'), { code: 'ENOENT' }))
  const publisherPage = { isClosed: () => false, setDefaultTimeout: vi.fn(), goto: vi.fn(), bringToFront: vi.fn() }
  const publisherContext = { newPage: async () => publisherPage, on: vi.fn(), close: vi.fn() }
  mocks.launch.mockResolvedValueOnce(publisherContext)
  const account = (await request('/accounts/add', { request_id: 'account-test-1', name: '测试账号', note: '' })).body.account
  expect((await request('/publisher/open', { account_id: account.id, record_id: 'publication-test', revision: 1 })).status).toBe(200)
  const research = (await request('/accounts/add', { request_id: 'research-test-1', name: '采集账号', note: '' })).body.account
  expect((await request('/collect', { ...task, account_id: research.id })).status).toBe(200)
  expect((await request('/control', { enabled: false })).status).toBe(200)
  expect(publisherContext.close).not.toHaveBeenCalled()
  expect((await request('/publisher/state?account_id='+account.id)).body.session.browser_open).toBe(true)
  expect((await request('/health')).body).toMatchObject({ version: 11, publishing: true, enabled: false })
  expect((await request('/publisher/open', {}, 'https://untrusted.example')).status).toBe(403)
  expect((await request('/publisher/state', undefined, 'https://untrusted.example')).status).toBe(403)
  expect((await request('/publisher/preview?account_id='+account.id, undefined, 'https://untrusted.example')).status).toBe(403)
})

it('采集复用已打开的账号窗口，用户关闭后可以重新采集', async () => {
  const login = browser()
  const background = browser()
  mocks.launch.mockResolvedValueOnce(login).mockResolvedValueOnce(background)
  expect((await request('/open', { account_id: accountId })).status).toBe(200)
  expect((await request('/collect', task)).status).toBe(200)
  expect(login.close).not.toHaveBeenCalled()
  expect(mocks.launch.mock.calls.map(call => call[1].headless)).toEqual([false])

  await login.close()
  expect((await request('/health')).body.browser_open).toBe(false)
  expect((await request('/collect', task)).status).toBe(200)
  expect(mocks.launch).toHaveBeenCalledTimes(2)
})

it('采集启动期间拒绝并发采集、登录和关闭请求，完成后释放锁', async () => {
  const launch = deferred<ReturnType<typeof browser>>()
  mocks.launch.mockReturnValueOnce(launch.promise)
  const collecting = request('/collect', task)
  await vi.waitFor(() => expect(mocks.launch).toHaveBeenCalledOnce())
  expect((await request('/health')).body.busy).toBe(true)
  expect((await request('/collect', task)).status).toBe(409)
  expect((await request('/open', { account_id: accountId })).status).toBe(409)
  expect((await request('/control', { enabled: false })).status).toBe(409)
  expect((await request('/health')).body.busy).toBe(true)

  launch.resolve(browser())
  expect((await collecting).status).toBe(200)
  expect((await request('/health')).body.busy).toBe(false)
  expect((await request('/control', { enabled: false })).status).toBe(200)
})

it('登录窗口启动期间独占浏览器，避免重复启动或切换', async () => {
  const launch = deferred<ReturnType<typeof browser>>()
  mocks.launch.mockReturnValueOnce(launch.promise)
  const opening = request('/open', { account_id: accountId })
  await vi.waitFor(() => expect(mocks.launch).toHaveBeenCalledOnce())
  expect((await request('/health')).body.busy).toBe(true)
  expect((await request('/collect', task)).status).toBe(409)
  expect((await request('/open', { account_id: accountId })).status).toBe(409)
  expect((await request('/control', { enabled: false })).status).toBe(409)
  launch.resolve(browser())
  expect((await opening).status).toBe(200)
  expect((await request('/collect', task)).status).toBe(200)
})

it('关闭采集器期间拒绝新任务，完成后保持关闭状态', async () => {
  const saving = deferred<void>()
  mocks.writeFile.mockReturnValueOnce(saving.promise)
  const closing = request('/control', { enabled: false })
  await vi.waitFor(() => expect(mocks.writeFile).toHaveBeenCalledOnce())
  expect((await request('/health')).body.busy).toBe(true)
  expect((await request('/collect', task)).status).toBe(409)
  expect((await request('/open', { account_id: accountId })).status).toBe(409)
  expect((await request('/control', { enabled: true })).status).toBe(409)
  saving.resolve()
  expect((await closing).status).toBe(200)
  expect((await request('/health')).body).toMatchObject({ busy: false, enabled: false })
  expect((await request('/collect', task)).status).toBe(409)
})

it.each(['/collect', '/open'])('%s 浏览器启动失败后释放锁并允许重试', async (url) => {
  mocks.launch.mockRejectedValueOnce(new Error('browser launch failed'))
  expect(await request(url, task)).toEqual({ status: 502, body: { error: 'browser launch failed' } })
  expect((await request('/health')).body.busy).toBe(false)
  expect((await request('/collect', task)).status).toBe(200)
})

it('无效采集参数和开关保存失败都不会残留忙碌状态', async () => {
  expect((await request('/collect', { ...task, note_limit: 0 })).status).toBe(400)
  expect((await request('/health')).body.busy).toBe(false)
  mocks.writeFile.mockRejectedValueOnce(new Error('disk failure'))
  expect((await request('/control', { enabled: false })).status).toBe(502)
  expect((await request('/health')).body).toMatchObject({ busy: false, enabled: true })
  expect((await request('/collect', task)).status).toBe(200)
})

it('异步采集可读取进度，相同任务重复提交复用结果', async () => {
  const launch = deferred<ReturnType<typeof browser>>()
  mocks.launch.mockReturnValueOnce(launch.promise)
  const body = { ...task, task_id: 'job-progress-one', retry: true }
  expect((await request('/jobs', body)).status).toBe(202)
  expect((await request('/jobs/job-progress-one')).body).toMatchObject({ status: 'running', stage: 'opening', collected: 0 })
  expect((await request('/jobs', body)).status).toBe(200)
  await vi.waitFor(() => expect(mocks.launch).toHaveBeenCalledOnce())
  expect((await request('/jobs', { ...body, task_id: 'another-job' })).status).toBe(409)
  launch.resolve(browser())
  await vi.waitFor(async () => expect((await request('/jobs/job-progress-one')).body.status).toBe('completed'))
  const completed = await request('/jobs', body)
  expect(completed.body.items).toHaveLength(10)
  expect(completed.body).not.toHaveProperty('origin')
  expect(completed.body).not.toHaveProperty('task')
  expect(mocks.launch).toHaveBeenCalledOnce()
  expect((await request('/jobs', { ...body, query: '不同条件' })).status).toBe(409)
  expect((await request('/jobs', { ...body, account_id: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' })).status).toBe(409)
  expect(completed.body.account_id).toBe(accountId)
})

it('缺失账号、其他来源账号和归档账号不能创建采集任务', async () => {
  expect((await request('/jobs', { ...task, task_id: 'job-missing-account', account_id: undefined })).status).toBe(400)
  expect((await request('/jobs', { ...task, task_id: 'job-missing-account', account_id: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' })).status).toBe(404)
  expect((await request('/jobs', { ...task, task_id: 'job-cross-origin' }, 'https://127.0.0.1')).status).toBe(404)
  await request('/accounts/update', { account_id: accountId, revision: 1, name: '测试账号', note: '', archived: true })
  expect((await request('/jobs', { ...task, task_id: 'job-archived-account' })).status).toBe(409)
  expect(mocks.launch).not.toHaveBeenCalled()
  expect((await request('/health')).body.busy).toBe(false)
})

it('完成结果持久化后，采集器重启可以取回并且不会重新抓取', async () => {
  const body = { ...task, task_id: 'job-cached-one' }
  await request('/jobs', body)
  await vi.waitFor(async () => expect((await request('/jobs/job-cached-one')).body.status).toBe('completed'))
  const data = mocks.writeFile.mock.calls.filter(call => String(call[0]).endsWith('jobs.json.tmp')).slice(-1)[0]![1]
  mocks.readFile.mockImplementation(async filename => String(filename).endsWith('jobs.json') ? data : '{"enabled":true}')
  vi.resetModules()
  // @ts-expect-error The standalone Node entry point has no TypeScript declarations.
  await import('../../scripts/xhs-local-collector.mjs')
  expect((await request('/jobs', body)).body.items).toHaveLength(10)
  expect((await request('/health')).body.browser_open).toBe(false)
  expect(mocks.launch).toHaveBeenCalledOnce()
})

it('异步任务区分网络失败并允许显式重试', async () => {
  mocks.launch.mockRejectedValueOnce(new Error('page.goto: Timeout 30000ms exceeded'))
  const body = { ...task, task_id: 'job-network-one' }
  await request('/jobs', body)
  await vi.waitFor(async () => expect((await request('/jobs/job-network-one')).body.status).toBe('failed'))
  expect((await request('/jobs/job-network-one')).body).toMatchObject({ error_code: 'network', retryable: true })
  expect((await request('/jobs', body)).body.status).toBe('failed')
  expect((await request('/jobs', { ...body, retry: true })).status).toBe(202)
  await vi.waitFor(async () => expect((await request('/jobs/job-network-one')).body.status).toBe('completed'))
})

it('缓存写入失败不会留下假运行任务或占用锁', async () => {
  mocks.writeFile.mockRejectedValueOnce(new Error('disk full'))
  const body = { ...task, task_id: 'job-storage-one' }
  expect((await request('/jobs', body)).status).toBe(502)
  expect((await request('/jobs/job-storage-one')).status).toBe(404)
  expect((await request('/health')).body.busy).toBe(false)
  expect((await request('/jobs', body)).status).toBe(202)
  await vi.waitFor(async () => expect((await request('/jobs/job-storage-one')).body.status).toBe('completed'))
})

it('非真人操作使采集器自动关闭，拒绝重试但允许打开原账号，恢复必须显式确认', async () => {
  mocks.launch.mockResolvedValueOnce(browser({ message: '您的操作不符合真人操作习惯' }))
  const body = { ...task, task_id: 'job-account-risk' }
  await request('/jobs', body)
  await vi.waitFor(async () => expect((await request('/jobs/job-account-risk')).body.status).toBe('failed'))
  expect((await request('/jobs/job-account-risk')).body).toMatchObject({ error_code: 'account_restricted', retryable: false })
  expect((await request('/health')).body).toMatchObject({ enabled: false, busy: false, pause_reason: expect.stringContaining('非真人操作') })
  expect((await request('/jobs', { ...body, retry: true })).status).toBe(409)
  expect((await request('/collect', task)).status).toBe(409)
  expect((await request('/open', { account_id: accountId })).status).toBe(200)
  expect((await request('/health')).body.enabled).toBe(false)
  expect((await request('/control', { enabled: true })).status).toBe(409)
  expect((await request('/control', { enabled: true, confirmed: true })).status).toBe(200)
  expect((await request('/health')).body).toMatchObject({ enabled: true, pause_reason: '' })
  const context = await mocks.launch.mock.results[0]!.value
  expect(context.pages()[0].close).not.toHaveBeenCalled()
})

it('平台限制造成的暂停状态在重启后保留', async () => {
  mocks.launch.mockResolvedValueOnce(browser({ message: '账号存在异常，部分功能受限' }))
  await request('/collect', task)
  const state = mocks.writeFile.mock.calls.find(call => String(call[0]).endsWith('state.json.tmp'))![1]
  mocks.readFile.mockImplementation(async filename => String(filename).endsWith('state.json') ? state : '{"enabled":true}')
  vi.resetModules()
  // @ts-expect-error The standalone Node entry point has no TypeScript declarations.
  await import('../../scripts/xhs-local-collector.mjs')
  expect((await request('/health')).body).toMatchObject({ enabled: false, pause_reason: expect.stringContaining('账号异常') })
  expect((await request('/collect', task)).status).toBe(409)
  expect(mocks.launch).toHaveBeenCalledOnce()
})

it('暂停状态写入失败仍在本次进程内停止采集并释放忙碌锁', async () => {
  mocks.launch.mockResolvedValueOnce(browser({ message: '请完成安全验证' }))
  mocks.writeFile.mockImplementation(async filename => { if (String(filename).endsWith('state.json.tmp')) throw new Error('disk full') })
  await request('/jobs', { ...task, task_id: 'job-risk-disk-full' })
  await vi.waitFor(async () => expect((await request('/jobs/job-risk-disk-full')).body.status).toBe('failed'))
  expect((await request('/health')).body).toMatchObject({ enabled: false, busy: false })
  expect((await request('/jobs/job-risk-disk-full')).body).toMatchObject({ error_code: 'verification', retryable: false })
  expect((await request('/collect', task)).status).toBe(409)
})

it('没有页面提示且未取得数据时按原因不明暂停，不声明账号被风控', async () => {
  const context = browser({ message: '公开搜索页', empty: true })
  mocks.launch.mockResolvedValueOnce(context)
  await request('/jobs', { ...task, task_id: 'job-empty-uncertain' })
  await vi.waitFor(async () => expect((await request('/jobs/job-empty-uncertain')).body.status).toBe('failed'))
  const failed = (await request('/jobs/job-empty-uncertain')).body
  expect(failed).toMatchObject({ error_code: 'collection_uncertain', retryable: false, error: expect.stringContaining('原因尚不明确') })
  expect(failed.error).not.toContain('账号被风控')
  expect((await request('/health')).body).toMatchObject({ enabled: false, busy: false })
  expect(context.pages()[0].evaluate).not.toHaveBeenCalled()
  expect((await request('/jobs', { ...task, task_id: 'job-empty-uncertain', retry: true })).status).toBe(409)
})

it('不同任务的相同条件复用近期快照，不再次访问平台，也不会延长缓存有效期', async () => {
  await request('/jobs', { ...task, task_id: 'job-cache-source' })
  await vi.waitFor(async () => expect((await request('/jobs/job-cache-source')).body.status).toBe('completed'))
  const first = (await request('/jobs/job-cache-source')).body
  const context = await mocks.launch.mock.results[0]!.value
  const visits = context.pages()[0].goto.mock.calls.length
  const clock = vi.spyOn(Date, 'now').mockReturnValue(Date.parse(first.cache_created_at) + 5 * 60_000)
  const second = await request('/jobs', { ...task, task_id: 'job-cache-reused' })
  expect(second).toMatchObject({ status: 200, body: { cached: true, status: 'completed', cache_created_at: first.cache_created_at, items: first.items } })
  expect(context.pages()[0].goto).toHaveBeenCalledTimes(visits)
  clock.mockReturnValue(Date.parse(first.cache_created_at) + 10 * 60_000 + 1)
  const expired = await request('/jobs', { ...task, task_id: 'job-cache-expired' })
  expect(expired.status).toBe(202)
  await vi.waitFor(async () => expect((await request('/jobs/job-cache-expired')).body.status).toBe('completed'))
  expect(context.pages()[0].goto).toHaveBeenCalledTimes(visits + 1)
})

it('缓存不跨账号、来源或搜索条件复用', async () => {
  await request('/jobs', { ...task, task_id: 'job-cache-account-a' })
  await vi.waitFor(async () => expect((await request('/jobs/job-cache-account-a')).body.status).toBe('completed'))
  const other = (await request('/accounts/add', { request_id: 'cache-account-b', name: '另一账号', note: '' })).body.account
  expect((await request('/jobs', { ...task, account_id: other.id, task_id: 'job-cache-account-b' })).status).toBe(202)
  await vi.waitFor(async () => expect((await request('/jobs/job-cache-account-b')).body.status).toBe('completed'))
  expect(mocks.launch).toHaveBeenCalledTimes(2)
  expect((await request('/jobs', { ...task, task_id: 'job-cache-other-origin' }, 'https://127.0.0.1')).status).toBe(404)
  expect((await request('/jobs', { ...task, query: '不同关键词', task_id: 'job-cache-other-query' })).status).toBe(202)
  await vi.waitFor(async () => expect((await request('/jobs/job-cache-other-query')).body.status).toBe('completed'))
})
