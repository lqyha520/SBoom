import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { executeResearchQueue, executeResearchTask } from '../xhs-queue'
import { CollectorError, type ResearchTask } from '../xhs-research'

const api = vi.hoisted(() => ({ get: vi.fn(), start: vi.fn(), collect: vi.fn(), save: vi.fn(), fail: vi.fn() }))
vi.mock('../xhs-research', async original => ({
  ...await original<typeof import('../xhs-research')>(), getResearchTask: api.get, startResearchTask: api.start,
  collectLocally: api.collect, saveResearchResults: api.save, failResearchTask: api.fail,
}))
const task = { id: 'task-one', grade: '一年级', subject: '数学', keyword: '口算', note_limit: 20, status: 'queued' } as ResearchTask
beforeEach(() => {
  vi.resetAllMocks(); vi.useFakeTimers()
  api.get.mockImplementation(async id => ({ ...task, id }))
  api.start.mockImplementation(async (_admin, id) => ({ ...task, id, status: 'running' }))
  api.collect.mockResolvedValue([])
  api.save.mockImplementation(async (_admin, id) => ({ ...task, id, status: 'completed' }))
})
afterEach(() => vi.useRealTimers())

it('已经保存的任务恢复时跳过采集和写入', async () => {
  api.get.mockResolvedValue({ ...task, status: 'completed' })
  expect((await executeResearchTask(1, task, 'account-a', vi.fn())).status).toBe('completed')
  expect(api.collect).not.toHaveBeenCalled(); expect(api.start).not.toHaveBeenCalled(); expect(api.save).not.toHaveBeenCalled()
})

it('本机连接中断只重连一次取回原任务并上报保存阶段', async () => {
  api.collect.mockRejectedValueOnce(new CollectorError('超时', 'bridge_network', true)).mockResolvedValueOnce([])
  const progress = vi.fn()
  const running = executeResearchTask(1, task, 'account-a', progress)
  await vi.runAllTimersAsync()
  expect((await running).status).toBe('completed')
  expect(api.collect).toHaveBeenCalledTimes(2)
  expect(api.collect.mock.calls.map(call => call[1])).toEqual(['account-a', 'account-a'])
  expect(progress.mock.calls.map(call => call[0].stage)).toEqual(['retrying', 'saving'])
  expect(api.fail).not.toHaveBeenCalled()
})

it('登录失效停止队列，后续任务保留待执行', async () => {
  api.collect.mockRejectedValue(new CollectorError('请登录', 'login'))
  const running = executeResearchQueue(1, [task, { ...task, id: 'task-two' }], {
    accounts: { 'task-one': 'account-a', 'task-two': 'account-b', failed: 'account-a' }, paused: () => false, progress: vi.fn(), completed: vi.fn(), started: vi.fn(),
  })
  await expect(running).rejects.toThrow('请登录')
  expect(api.start).toHaveBeenCalledTimes(1)
  expect(api.collect).toHaveBeenCalledTimes(1)
  expect(api.fail).toHaveBeenCalledWith(1, task.id, '请登录')
})

it('暂停等待当前项保存后停止，不启动下一项', async () => {
  let paused = false
  const completed = vi.fn(() => { paused = true })
  await executeResearchQueue(1, [task, { ...task, id: 'task-two' }], {
    accounts: { 'task-one': 'account-a', 'task-two': 'account-b', failed: 'account-a' }, paused: () => paused, progress: vi.fn(), completed, started: vi.fn(),
  })
  expect(api.save).toHaveBeenCalledOnce(); expect(api.start).toHaveBeenCalledOnce(); expect(completed).toHaveBeenCalledOnce()
})

it('每次只执行下一项，恢复时跳过已完成项且不自动启动后续任务', async () => {
  const done = { ...task, id: 'done', status: 'completed' } as ResearchTask
  const failed = { ...task, id: 'failed', status: 'failed' } as ResearchTask
  const tasks = [done, failed, task]
  const options = { accounts: { 'task-one': 'account-a', 'task-two': 'account-b', failed: 'account-a' }, paused: () => false, progress: vi.fn(),
    completed: (completed: ResearchTask) => { tasks[tasks.findIndex(item => item.id === completed.id)] = completed }, started: vi.fn() }
  await executeResearchQueue(1, tasks, options)
  await vi.runAllTimersAsync()
  expect(api.start.mock.calls.map(call => call[1])).toEqual(['failed'])
  await executeResearchQueue(1, tasks, options)
  expect(api.start.mock.calls.map(call => call[1])).toEqual(['failed', 'task-one'])
  expect(api.collect.mock.calls.map(call => call[1])).toEqual(['account-a', 'account-a'])
})

it.each(['account_restricted', 'verification', 'restricted', 'network', 'collection_uncertain'])('%s 平台访问失败不自动重试或启动下一项', async code => {
  api.collect.mockRejectedValue(new CollectorError('请先处理平台提示', code, true))
  await expect(executeResearchQueue(1, [task, { ...task, id: 'task-two' }], {
    accounts: { 'task-one': 'account-a', 'task-two': 'account-b' }, paused: () => false, progress: vi.fn(), completed: vi.fn(), started: vi.fn(),
  })).rejects.toThrow('请先处理平台提示')
  expect(api.collect).toHaveBeenCalledOnce()
  expect(api.start).toHaveBeenCalledOnce()
})
