// @vitest-environment node
import { EventEmitter } from 'node:events'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
// @ts-expect-error 本机独立 Node 服务。
import { createXhsAccounts } from '../../scripts/xhs-accounts.mjs'

const origin = 'https://localhost'
let folder: string
beforeEach(async () => { folder = await mkdtemp(path.join(os.tmpdir(), 'lc-account-test-')) })
afterEach(async () => { await rm(folder, { recursive: true, force: true }) })
function setup() {
  const contexts: ReturnType<typeof context>[] = []
  function context() {
    const events = new EventEmitter(), pages: { isClosed: () => boolean; url: () => string; goto: ReturnType<typeof vi.fn>; bringToFront: ReturnType<typeof vi.fn>; setDefaultTimeout: ReturnType<typeof vi.fn> }[] = []
    let closed = false
    const value = { on: events.on.bind(events), pages: () => pages, close: vi.fn(async () => { closed = true; events.emit('close') }), newPage: vi.fn(async () => {
      let url = 'about:blank'
      const page = { isClosed: () => closed, url: () => url, goto: vi.fn(async (next: string) => { url = next }), bringToFront: vi.fn(), setDefaultTimeout: vi.fn() }
      pages.push(page); return page
    }) }
    return value
  }
  const launch = vi.fn(async () => { const value = context(); contexts.push(value); return value })
  const service = createXhsAccounts({ rootDir: folder, launch })
  return { service, launch, contexts }
}
async function add(service: ReturnType<typeof createXhsAccounts>, name = '数学账号', request = 'account-request-1') { return (await service.add(origin, { name, note: '', request_id: request })).account }

it('创建幂等，重复名称拒绝，名称不能控制配置目录，账号来源隔离', async () => {
  const { service, launch } = setup()
  const a = await add(service, '../../另一个账号')
  expect((await add(service, '../../另一个账号')).id).toBe(a.id)
  await expect(add(service, '../../另一个账号', 'account-request-2')).rejects.toThrow('同名')
  expect((await service.list('https://elsewhere.example')).items).toHaveLength(0)
  await expect(service.open('https://elsewhere.example', { account_id: a.id })).rejects.toThrow('其他后台')
  await expect(service.open(origin, { account_id: '../../outside' })).rejects.toThrow('编号')
  await service.open(origin, { account_id: a.id })
  expect(launch).toHaveBeenCalledWith(path.join(folder, 'xhs-account-profiles', a.id), { headless: false, viewport: null })
})
it('账号使用不同目录；重复打开唤起原页，不重复启动或导航；关闭一个保留另一个', async () => {
  const { service, launch, contexts } = setup()
  const a = await add(service), b = await add(service, '日常账号', 'account-request-2')
  await service.open(origin, { account_id: a.id }); await service.open(origin, { account_id: b.id })
  await service.open(origin, { account_id: a.id })
  expect(launch).toHaveBeenCalledTimes(2)
  expect(launch.mock.calls[0]).not.toEqual(launch.mock.calls[1])
  expect(contexts[0]!.newPage).toHaveBeenCalledTimes(2)
  expect(contexts[0]!.pages()[1]!.goto).toHaveBeenCalledOnce()
  expect(contexts[0]!.pages()[1]!.bringToFront).toHaveBeenCalledTimes(2)
  await expect(service.close(origin, { account_id: a.id })).rejects.toThrow('确认')
  await service.close(origin, { account_id: a.id, acknowledged: true })
  expect(contexts[1]!.close).not.toHaveBeenCalled()
  expect((await service.list(origin)).items.map((item: { browser_open: boolean }) => item.browser_open)).toEqual([false, true])
  await service.open(origin, { account_id: a.id })
  expect(launch.mock.calls[2]).toEqual(launch.mock.calls[0])
})
it('同一账号并发打开只启动一个浏览器', async () => {
  const { service, launch } = setup(), a = await add(service)
  const requests = await Promise.allSettled([service.open(origin, { account_id: a.id }), service.open(origin, { account_id: a.id })])
  expect(requests.filter(result => result.status === 'fulfilled')).toHaveLength(1)
  expect(launch).toHaveBeenCalledOnce()
})

it('查看笔记在所选账号中新开标签，保留访问参数及其他账号和已有页面', async () => {
  const { service, launch, contexts } = setup(), a = await add(service), b = await add(service, '语文账号', 'account-request-2')
  await service.open(origin, { account_id: a.id }); await service.open(origin, { account_id: b.id })
  const original = contexts[0]!.pages()[1]!, previousUrl = original.url()
  const url = 'https://www.xiaohongshu.com/search_result/65abcdef0123456789abcdef?xsec_token=fixture-token&xsec_source=pc_search'
  await service.openNote(origin, { account_id: a.id, url })
  expect(launch).toHaveBeenCalledTimes(2)
  expect(original.url()).toBe(previousUrl)
  expect(original.goto).toHaveBeenCalledOnce()
  expect(contexts[0]!.pages()[2]!.goto).toHaveBeenCalledWith(url, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  expect(contexts[0]!.pages()[2]!.bringToFront).toHaveBeenCalledOnce()
  expect(contexts[1]!.pages()).toHaveLength(2)
  await service.shutdown()
})

it('拒绝非小红书笔记链接和跨来源账号，不启动浏览器', async () => {
  const { service, launch } = setup(), a = await add(service)
  for (const url of ['javascript:alert(1)', 'https://example.com/explore/note-test', 'https://www.xiaohongshu.com.evil.com/explore/note-test',
    'https://user:pass@www.xiaohongshu.com/explore/note-test', 'https://www.xiaohongshu.com:8443/explore/note-test', 'https://www.xiaohongshu.com/explore']) {
    await expect(service.openNote(origin, { account_id: a.id, url })).rejects.toThrow('笔记链接')
  }
  await expect(service.openNote('https://elsewhere.example', { account_id: a.id, url: 'https://www.xiaohongshu.com/explore/note-test' })).rejects.toThrow('其他后台')
  expect(launch).not.toHaveBeenCalled()
})
it('改名保持目录，拒绝旧版本覆盖，归档需先关闭，恢复和服务重启保留账号', async () => {
  const { service, launch } = setup(), a = await add(service)
  await service.open(origin, { account_id: a.id })
  const data = { account_id: a.id, revision: a.revision, name: '新版名称', note: '用途', archived: false }
  const changed = (await service.update(origin, data)).account
  await expect(service.update(origin, data)).rejects.toThrow('其他页面修改')
  await expect(service.update(origin, { ...data, revision: changed.revision, archived: true })).rejects.toThrow('关闭')
  await service.close(origin, { account_id: a.id, acknowledged: true })
  const archived = (await service.update(origin, { ...data, revision: changed.revision, archived: true })).account
  await expect(service.open(origin, { account_id: a.id })).rejects.toThrow('已归档')
  await service.update(origin, { ...data, revision: archived.revision })
  const restarted = createXhsAccounts({ rootDir: folder, launch })
  expect((await restarted.list(origin)).items[0]).toMatchObject({ id: a.id, name: '新版名称', archived: false, browser_open: false })
  await restarted.open(origin, { account_id: a.id })
  expect(launch.mock.calls[1]).toEqual(launch.mock.calls[0])
})
it('辅助发布绑定所选账号；令牌不能跨账号使用，打开使用同一浏览器', async () => {
  const { service, launch } = setup(), a = await add(service), b = await add(service, '另一个', 'account-request-2')
  await service.open(origin, { account_id: a.id })
  const meta = { record_id: 'publication-123', revision: 1 }
  const first = await service.publication(origin, a.id, 'open', meta)
  const second = await service.publication(origin, b.id, 'open', meta)
  expect(launch).toHaveBeenCalledTimes(2)
  expect(first.session.account_id).toBe(a.id)
  expect(second.session.account_id).toBe(b.id)
  await expect(service.publication(origin, b.id, 'prepare', { ...meta, token: first.session.token })).rejects.toThrow('会话')
})
it('原辅助配置原位登记，清单损坏时不覆盖、不丢失数据', async () => {
  const { service, launch } = setup()
  const directory = path.join(folder, 'xhs-publisher-profile')
  await mkdir(directory); await writeFile(path.join(directory, 'fixture-marker'), 'preserve')
  const items = (await service.list(origin)).items
  expect(items).toHaveLength(1)
  expect(items[0].id).toBe('legacy-publisher')
  await service.open(origin, { account_id: items[0].id })
  expect(launch).toHaveBeenCalledWith(directory, expect.anything())
  await writeFile(path.join(folder, 'xhs-accounts.json'), '{broken')
  const restarted = createXhsAccounts({ rootDir: folder, launch })
  await expect(restarted.list(origin)).rejects.toThrow('无法读取')
  expect(await readFile(path.join(directory, 'fixture-marker'), 'utf8')).toBe('preserve')
})

it('原采集目录原位导入一次，与原发布目录保持独立', async () => {
  const { service, launch } = setup()
  await mkdir(path.join(folder, 'xhs-research-profile'))
  await mkdir(path.join(folder, 'xhs-publisher-profile'))
  const first = await service.list(origin)
  expect(first.items.map((item: { id: string }) => item.id)).toEqual(['legacy-publisher', 'legacy-research'])
  expect((await service.list(origin)).items).toHaveLength(2)
  await service.open(origin, { account_id: 'legacy-research' })
  expect(launch).toHaveBeenCalledWith(path.join(folder, 'xhs-research-profile'), expect.objectContaining({ headless: false }))
})

it('账号定位持久化，旧客户端归档不清空档案，非法字段不覆盖', async () => {
  const { service, launch } = setup(), a = await add(service)
  const profile = { audience: '小学家长', direction: '数学练习', style: '温和具体', topics: '#数学' }
  const saved = (await service.update(origin, { account_id: a.id, revision: a.revision, name: a.name, note: '', archived: false, profile })).account
  await service.update(origin, { account_id: a.id, revision: saved.revision, name: a.name, note: '', archived: true })
  const restarted = createXhsAccounts({ rootDir: folder, launch })
  const result = await restarted.list(origin)
  expect(result.profile_support).toBe(true)
  expect(result.items[0].profile).toEqual(profile)
  await expect(restarted.update(origin, { account_id: a.id, revision: result.items[0].revision, name: a.name, note: '', archived: false, profile: { ...profile, style: 'x'.repeat(1001) } })).rejects.toThrow('超过')
  expect((await restarted.list(origin)).items[0].profile).toEqual(profile)
})
