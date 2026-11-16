import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { request } from '../api'
import { posterArtwork, useReferralPoster, type PosterDraft } from '../referral-poster'

vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), request: vi.fn() }))
const api = vi.mocked(request), scopes: ReturnType<typeof effectScope>[] = []
const draft: PosterDraft = { title: '阅读的春天', caption: '每天一点进步', style: 'editorial', direction: '森林', version: 'release' }
const asset = { asset_id: 'a'.repeat(32), request_id: 'original', expires_at: 9999999999 }
function setup(actor = ref(1), campaign = ref('first')) {
  const scope = effectScope(); scopes.push(scope)
  return scope.run(() => useReferralPoster(() => actor.value, () => campaign.value))!
}
beforeEach(() => { api.mockReset(); localStorage.clear() })
afterEach(() => { scopes.splice(0).forEach(scope => scope.stop()); vi.restoreAllMocks() })

it('使用图片配置与唯一请求号，刷新找回原图且不再次调用模型', async () => {
  api.mockResolvedValueOnce({ timeout_ms: 240000, revision: 'r7' }).mockRejectedValueOnce(new Error('网络中断'))
  const flow = setup(); await flow.generate(draft)
  expect(api.mock.calls[0]?.[0]).toBe('/api/v1/generation/options?kind=image')
  const call = api.mock.calls[1]!, init = call[1]!
  const id = (init.headers as Record<string, string>)['X-Request-ID']
  expect(init.headers).toMatchObject({ 'X-Model-Config-Revision': 'r7' })
  expect(call[3]).toBe(240000)
  expect(JSON.parse(init.body as string)).toEqual({ campaign_id: 'first', title: draft.title, style: draft.style, direction: draft.direction })
  expect(flow.pending.value).toBe(true)
  await flow.generate(draft); expect(api).toHaveBeenCalledTimes(2)
  const reopened = setup()
  api.mockResolvedValueOnce({ status: 'running', result: null })
  await reopened.recover(); expect(reopened.pending.value).toBe(true)
  api.mockResolvedValueOnce({ status: 'succeeded', result: asset })
  await reopened.recover()
  expect(api).toHaveBeenLastCalledWith(`/api/v1/me/generations/${id}`)
  expect(reopened.job.value?.result).toEqual(asset)
  expect(reopened.pending.value).toBe(false)
  expect(setup().job.value?.result).toEqual(asset)
  expect(api.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1)
})

it('账号和活动隔离，迟到的旧结果不会覆盖新活动', async () => {
  const campaign = ref('first'), actor = ref(1)
  let finish!: (value: typeof asset) => void
  api.mockResolvedValueOnce({ timeout_ms: 30000, revision: 'r1' }).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const flow = setup(actor, campaign), running = flow.generate(draft)
  await vi.waitFor(() => expect(api).toHaveBeenCalledTimes(2))
  campaign.value = 'second'; await nextTick()
  finish(asset); await running
  expect(flow.job.value).toBeNull()
  campaign.value = 'first'; actor.value = 2; await nextTick()
  expect(flow.job.value).toBeNull()
  actor.value = 1; await nextTick()
  expect(flow.pending.value).toBe(true)
})

it('本机请求号无法保存时不启动付费调用；恢复终态失败后才允许重试', async () => {
  api.mockResolvedValue({ timeout_ms: 30000, revision: 'r1' })
  const storage = vi.spyOn(localStorage, 'setItem').mockImplementation(() => { throw new Error('storage full') })
  const flow = setup(); await flow.generate(draft)
  expect(api).toHaveBeenCalledTimes(1)
  expect(flow.error.value).toContain('storage full')
  storage.mockRestore()
  localStorage.setItem('lc-referral-poster:1:first', JSON.stringify({ id: 'failed', draft }))
  const reopened = setup()
  api.mockResolvedValueOnce({ status: 'failed', result: null, error: { error: '上游拒绝' } })
  await reopened.recover(); expect(reopened.pending.value).toBe(false)
  expect(reopened.error.value).toBe('上游拒绝')
})

it('只通过当前账号的受保护资源接口读取原图', async () => {
  await posterArtwork(asset)
  expect(api).toHaveBeenLastCalledWith('/api/v1/image-generation/assets/' + asset.asset_id, undefined, 'blob')
  expect(() => posterArtwork({ ...asset, asset_id: '../another' })).toThrow('标识无效')
})
