import { afterEach, expect, it, vi } from 'vitest'
import { reactive, nextTick, watch } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { useExamStore } from '../stores/exam'
import { createWorkspaceDraft, watchWorkspace, workspaceSnapshot } from '../workspace-draft'
import { deepClone } from '../utils'
import { DEFAULT_LAYOUT } from '../constants'

const stops: (() => void)[] = []
afterEach(() => { stops.splice(0).forEach(stop => stop()); vi.useRealTimers() })
function workspace() {
  setActivePinia(createPinia())
  return reactive(useExamStore().captureSnapshot())
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { resolve, reject, promise }
}

it('合并慢写入期间的多次编辑，所有 flush 等到最新版本保存后才成功', async () => {
  const source = workspace(), firstWrite = deferred<number>()
  const savedTitles: string[] = []
  const save = vi.fn(snapshot => {
    savedTitles.push(snapshot.title)
    return savedTitles.length === 1 ? firstWrite.promise : Promise.resolve(2)
  })
  const saved = vi.fn(), failed = vi.fn()
  const controller = createWorkspaceDraft({ source, save, saved, failed, saving() {}, canQueue: () => true })
  stops.push(controller.stop)
  source.title = 'A'
  const first = controller.flush()
  await nextTick()
  expect(save).toHaveBeenCalledTimes(1)
  const pending: Promise<boolean>[] = []
  for (let i = 0; i < 30; i++) { source.title = 'B' + i; pending.push(controller.flush()); await nextTick() }
  expect(save).toHaveBeenCalledTimes(1)
  firstWrite.resolve(1)
  expect(await Promise.all([first, ...pending])).toEqual(Array(31).fill(true))
  expect(savedTitles).toEqual(['A', 'B29'])
  expect(saved).toHaveBeenCalledExactlyOnceWith(2)
  expect(failed).not.toHaveBeenCalled()
  await controller.flush()
  expect(save).toHaveBeenCalledTimes(2)
})

it('写入失败可以重试，直接修改嵌套题目不会漏存', async () => {
  const source = workspace()
  source.sections = [{ id: 'section', type: 'fill_blank', name: '填空', count: 1,
    layout: { ...DEFAULT_LAYOUT }, status: 'ready', data: { questions: [{ stem: '原题' }] } }]
  const save = vi.fn().mockRejectedValueOnce(new Error('Full')).mockResolvedValue(2)
  const failed = vi.fn()
  const controller = createWorkspaceDraft({ source, save, failed, saved() {}, saving() {}, canQueue: () => true })
  stops.push(controller.stop)
  expect(await controller.flush()).toBe(false)
  source.sections[0].data!.questions[0]._stemHtml = '<b>编辑</b>'
  expect(await controller.flush()).toBe(true)
  expect(save.mock.calls[1]![0].sections[0].data.questions[0]._stemHtml).toBe('<b>编辑</b>')
  expect(failed).toHaveBeenCalledOnce()
})

it('350ms 内的连续输入只保存一次，停止后不再自动保存', async () => {
  vi.useFakeTimers()
  const source = workspace(), save = vi.fn().mockResolvedValue(1)
  const controller = createWorkspaceDraft({ source, save, failed() {}, saved() {}, saving() {}, canQueue: () => true })
  stops.push(controller.stop)
  for (let i = 0; i < 10; i++) { source.title += '字'; await nextTick(); await vi.advanceTimersByTimeAsync(100) }
  expect(save).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(350)
  expect(save).toHaveBeenCalledOnce()
  controller.stop(); source.title = '离开页面'; await nextTick(); await vi.advanceTimersByTimeAsync(400)
  expect(save).toHaveBeenCalledOnce()
})

it('大工作区修改标题不再遍历题目，题目编辑仍能触发保存', async () => {
  const results: object[] = []
  for (const count of [200, 1000]) {
    const source = workspace()
    let reads = 0
    source.sections = [{ id: 'large', type: 'fill_blank', name: '填空', count,
      layout: { ...DEFAULT_LAYOUT }, status: 'ready', data: { questions: Array.from({ length: count }, () => ({
        get stem() { reads++; return '题干'.repeat(50) }, _stemHtml: '',
      })) } }]
    const observe = async (optimized: boolean) => {
      const changed = vi.fn()
      const stop = optimized ? watchWorkspace(source, changed)
        : watch(() => Object.values(workspaceSnapshot(source)), changed, { deep: true })
      reads = 0
      const start = performance.now()
      for (let i = 0; i < 30; i++) { source.title = `${optimized}-${i}`; await nextTick() }
      const elapsedMs = performance.now() - start, titleReads = reads
      expect(changed).toHaveBeenCalledTimes(30)
      source.sections[0].data!.questions[0]._stemHtml += '编辑'
      await nextTick()
      expect(changed).toHaveBeenCalledTimes(31)
      stop()
      return { titleReads, elapsedMs }
    }
    const before = await observe(false), after = await observe(true)
    expect(before.titleReads).toBeGreaterThanOrEqual(count * 30)
    expect(after.titleReads).toBe(0)
    results.push({ questions: count, edits: 30, snapshotBytes: new TextEncoder().encode(JSON.stringify(deepClone(source))).length, before, after })
  }
  if (process.env.LC_WORKSPACE_BENCH) {
    const target = resolve(process.env.LC_WORKSPACE_BENCH)
    mkdirSync(target, { recursive: true })
    writeFileSync(resolve(target, 'workspace-watch.json'), JSON.stringify({ environment: 'Vitest happy-dom, Vue watcher microbenchmark; not device/UI latency', results }, null, 2))
  }
})
