// @vitest-environment node
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
// @ts-expect-error 本机独立 Node 模块。
import { createPublisher, validateAssistPayload } from '../../scripts/xhs-publish-assist.mjs'

const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='
const source = 'https://localhost'
const meta = { record_id: 'publication-123', revision: 2 }
const payload = () => ({ ...meta, headline: '数学练习', body: '先观察，再解题。\n\n#数学', account_confirmed: true, media_confirmed: true, reviewed: true, media: [{ type: 'image/png', base64: png }] })
let folder: string
beforeEach(async () => { folder = await mkdtemp(path.join(os.tmpdir(), 'lc-assist-test-')) })
afterEach(async () => { await rm(folder, { recursive: true, force: true }) })
function setup(fill = vi.fn(async (_page: unknown, _payload: unknown, before: () => Promise<void>) => { await before() })) {
  const page = { isClosed: () => false, setDefaultTimeout: vi.fn(), goto: vi.fn(), bringToFront: vi.fn() }
  const context = { newPage: vi.fn(async () => ({ ...page })), on: vi.fn(), close: vi.fn() }
  const launch = vi.fn(async () => context)
  const options = { profileDir: path.join(folder, 'publisher'), journalFile: path.join(folder, 'attempts.json'), launch, fill }
  return { publisher: createPublisher(options), options, context, page, launch, fill }
}
async function settled(publisher: ReturnType<typeof createPublisher>) { await vi.waitFor(() => expect(publisher.state(source).busy).toBe(false)) }

it('按文件签名校验媒体并按选择顺序生成固定文件名', () => {
  const data = payload(); data.media.push({ type: 'image/png', base64: png })
  const result = validateAssistPayload(data)
  expect(result.media.map((item: { name: string }) => item.name)).toEqual(['01.png', '02.png'])
  expect(result.media[0].buffer).toEqual(Buffer.from(png, 'base64'))
  expect(() => validateAssistPayload({ ...data, media: [{ type: 'image/png', base64: Buffer.from('<svg/>').toString('base64') }] })).toThrow('类型不一致')
})
it.each(['account_confirmed', 'media_confirmed', 'reviewed'])('缺少 %s 确认拒绝上传', key => {
  expect(() => validateAssistPayload({ ...payload(), [key]: false })).toThrow('确认')
})
it('拒绝空文件、过多素材、超大文件、混合图文视频和无效文案', () => {
  const data = payload()
  expect(() => validateAssistPayload({ ...data, media: [] })).toThrow('1–9')
  expect(() => validateAssistPayload({ ...data, media: Array(10).fill(data.media[0]) })).toThrow('1–9')
  expect(() => validateAssistPayload({ ...data, media: [{ type: 'image/png', base64: Buffer.alloc(10 * 1024 * 1024 + 1).toString('base64') }] })).toThrow('10 MB')
  const video = { type: 'video/mp4', base64: Buffer.from([0,0,0,16,102,116,121,112,105,115,111,109,0,0,0,0]).toString('base64') }
  expect(() => validateAssistPayload({ ...data, media: [...data.media, video] })).toThrow('混用')
  expect(validateAssistPayload({ ...data, media: [video] }).video).toBe(true)
  expect(() => validateAssistPayload({ ...data, headline: '字'.repeat(21) })).toThrow('过长')
})
it('专用有界面配置，令牌和来源绑定；重开不会导航或覆盖旧页面', async () => {
  const { publisher, launch, context, page } = setup()
  const first = await publisher.open(source, meta)
  await publisher.open(source, meta)
  expect(launch).toHaveBeenCalledWith(path.join(folder, 'publisher'), { headless: false, viewport: null })
  expect(context.newPage).toHaveBeenCalledOnce()
  expect(page.goto).toHaveBeenCalledOnce()
  expect(publisher.state('http://localhost:5173').session).toBeNull()
  await expect(publisher.prepare('http://localhost:5173', { ...payload(), token: first.session.token })).rejects.toThrow('会话')
  await expect(publisher.prepare(source, { ...payload(), token: 'wrong' })).rejects.toThrow('会话')
  await expect(publisher.prepare(source, { ...payload(), token: first.session.token, revision: 3 })).rejects.toThrow('会话')
})
it('重复点击、版本变化和服务重启不会重复上传；明确新建时保留旧窗口', async () => {
  const { publisher, options, fill, context } = setup()
  const first = await publisher.open(source, meta)
  const body = { ...payload(), token: first.session.token }
  await publisher.prepare(source, body); await settled(publisher)
  expect(publisher.state(source).session.status).toBe('prepared')
  await publisher.prepare(source, body)
  expect(fill).toHaveBeenCalledOnce()
  const saved = await readFile(options.journalFile, 'utf8')
  expect(saved).not.toContain('数学')
  expect(saved).not.toContain(png)
  expect(saved).not.toContain(first.session.token)
  const restarted = createPublisher(options)
  const next = await restarted.open(source, { ...meta, revision: 3 })
  await expect(restarted.prepare(source, { ...body, token: next.session.token, revision: 3 })).rejects.toThrow('曾尝试上传')
  const fresh = await publisher.open(source, { ...meta, new_session: true, acknowledged: true })
  expect(fresh.session.token).not.toBe(first.session.token)
  expect(context.close).not.toHaveBeenCalled()
  await publisher.prepare(source, { ...body, token: fresh.session.token }); await settled(publisher)
  expect(fill).toHaveBeenCalledTimes(2)
})
it('填入中的请求互斥；失败后保留已尝试状态，不自动重试', async () => {
  let reject!: (error: Error) => void
  const blocked = new Promise<void>((_, fail) => { reject = fail })
  const { publisher, fill } = setup(vi.fn(async (_page, _payload, before) => { await before(); await blocked }))
  const opened = await publisher.open(source, meta), body = { ...payload(), token: opened.session.token }
  await publisher.prepare(source, body)
  await expect(publisher.prepare(source, body)).rejects.toThrow('正在填入')
  await expect(publisher.open(source, { ...meta, new_session: true, acknowledged: true })).rejects.toThrow('正在处理')
  await vi.waitFor(() => expect(publisher.state(source).session.touched).toBe(true))
  reject(new Error('Timeout'))
  await settled(publisher)
  expect(publisher.state(source).session).toMatchObject({ status: 'paused', touched: true })
  await publisher.prepare(source, body)
  expect(fill).toHaveBeenCalledOnce()
})
it('未上传的窗口关闭后直接恢复，保留上传尝试的窗口关闭后必须明确新建', async () => {
  let closed = false
  const { publisher, context, page } = setup()
  page.isClosed = () => closed
  const first = await publisher.open(source, meta)
  closed = true
  const restored = await publisher.open(source, meta)
  expect(restored.session.token).not.toBe(first.session.token)
  expect(context.newPage).toHaveBeenCalledTimes(2)
  closed = false
  await publisher.prepare(source, { ...payload(), token: restored.session.token }); await settled(publisher)
  closed = true
  await expect(publisher.open(source, meta)).rejects.toThrow('曾尝试上传')
  expect(context.newPage).toHaveBeenCalledTimes(2)
})
