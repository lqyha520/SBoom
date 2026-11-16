import { afterEach, expect, it, vi } from 'vitest'
// 凭证传递在 local-access.test.ts 单独测试，本文件关注采集协议。
vi.mock('../local-access', () => ({ localFetch: (...args: Parameters<typeof fetch>) => fetch(...args) }))
import { buildResearchQuery, collectLocally, getCollectorStatus, listResearchTasks, researchSearchUrl, setCollectorEnabled, type ResearchTask } from '../xhs-research'

const task: ResearchTask = {
  id: 'task-1', grade: '四年级', subject: '数学', keyword: '找规律', period: 'week', sort_by: 'popular',
  note_limit: 20, status: 'running', note_count: 0, median_likes: null, average_likes: null,
  error: '', created_at: '', finished_at: '',
}

afterEach(() => vi.unstubAllGlobals())

it('将年级、科目和知识点组合成搜索词', () => {
  expect(buildResearchQuery(task)).toBe('四年级数学 找规律')
  expect(buildResearchQuery({ ...task, keyword: '  ' })).toBe('四年级数学')
  expect(researchSearchUrl(task)).toBe(
    'https://www.xiaohongshu.com/search_result/?keyword=%E5%9B%9B%E5%B9%B4%E7%BA%A7%E6%95%B0%E5%AD%A6%20%E6%89%BE%E8%A7%84%E5%BE%8B',
  )
})

it('向本机采集器发送完整条件并取回已完成的任务', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ task_id: task.id, account_id: 'account-a', status: 'completed', items: [] }) })
  vi.stubGlobal('fetch', fetch)

  await collectLocally(task, 'account-a')

  expect(fetch).toHaveBeenCalledWith('http://127.0.0.1:17632/jobs', expect.objectContaining({
    body: JSON.stringify({ task_id: task.id, account_id: 'account-a', retry: true, query: '四年级数学 找规律', grade: '四年级', subject: '数学', period: 'week', sort_by: 'popular', note_limit: 20 }),
  }))
})

it('读取采集器连接、开关和忙碌状态', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ enabled: true, busy: false }) })
  vi.stubGlobal('fetch', fetch)

  await expect(getCollectorStatus()).resolves.toEqual({ connected: true, enabled: true, busy: false })
  expect(fetch.mock.calls[0][0]).toBe('http://127.0.0.1:17632/health')
})

it('通过本机采集器控制接口切换运行状态', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ enabled: false, busy: false }) })
  vi.stubGlobal('fetch', fetch)

  await expect(setCollectorEnabled(false)).resolves.toEqual({ connected: true, enabled: false, busy: false })
  expect(fetch.mock.calls[0][0]).toBe('http://127.0.0.1:17632/control')
  expect(fetch.mock.calls[0][1]).toMatchObject({ method: 'POST', body: JSON.stringify({ enabled: false }) })
})

it('读取平台限制暂停原因，显式确认恢复时将确认传给采集器', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ enabled: false, busy: false, version: 9, pause_reason: '账号受限' }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ enabled: true, busy: false }) })
  vi.stubGlobal('fetch', fetch)
  await expect(getCollectorStatus()).resolves.toMatchObject({ enabled: false, pause_reason: '账号受限' })
  await setCollectorEnabled(true, true)
  expect(fetch.mock.calls[1][1]).toMatchObject({ body: JSON.stringify({ enabled: true, confirmed: true }) })
})

it('读取指定页的采集历史', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [], total: 12, page: 2, page_size: 10 }) })
  vi.stubGlobal('fetch', fetch)

  const result = await listResearchTasks(2, 10)

  expect(fetch.mock.calls[0][0]).toBe('/api/v1/admin/xhs-research/tasks?page=2&page_size=10')
  expect(fetch.mock.calls[0][1]?.headers).toBeInstanceOf(Headers)
  expect(result).toMatchObject({ items: [], total: 12, page: 2, page_size: 10 })
})

 it('拒绝不同账号的完成结果，避免串号', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ task_id: task.id, account_id: 'other-account', status: 'completed', items: [] }) }))
  await expect(collectLocally(task, 'account-a')).rejects.toThrow('账号与任务不一致')
})
