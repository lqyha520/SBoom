import {
  CollectorError, collectLocally, failResearchTask, getResearchTask, saveResearchResults, startResearchTask,
  type CollectionProgress, type ResearchTask,
} from './xhs-research'

const delay = (milliseconds: number) => new Promise(resolve => setTimeout(resolve, milliseconds))

export async function executeResearchTask(adminId: number, task: ResearchTask, accountId: string, progress: (value: CollectionProgress) => void): Promise<ResearchTask> {
  const current = await getResearchTask(task.id)
  if (current.status === 'completed') return current
  if (!accountId) throw new CollectorError('任务未绑定采集账号，请先选择账号。', 'account_required')
  const running = await startResearchTask(adminId, task.id)
  try {
    let notes
    let cached = false
    const report = (value: CollectionProgress) => { cached = value.cached === true; progress(value) }
    try { notes = await collectLocally(running, accountId, report) }
    catch (cause) {
      // 只重连本机服务取回原任务，平台访问失败留给用户处理，避免重复访问。
      if (!(cause instanceof CollectorError) || cause.code !== 'bridge_network' || !cause.retryable) throw cause
      progress({ task_id: task.id, status: 'running', stage: 'retrying', collected: 0, total: task.note_limit })
      await delay(3000)
      notes = await collectLocally(running, accountId, report)
    }
    progress({ task_id: task.id, status: 'running', stage: 'saving', collected: notes.length, total: task.note_limit, ...(cached ? { cached: true } : {}) })
    return await saveResearchResults(adminId, task.id, notes)
  } catch (cause) {
    try { await failResearchTask(adminId, task.id, (cause instanceof Error ? cause.message : '采集失败').slice(0, 500)) }
    catch { /* 本机缓存仍可恢复；不覆盖最初错误或其他页面已保存的结果。 */ }
    throw cause
  }
}

export async function executeResearchQueue(adminId: number, tasks: ResearchTask[], options: {
  accounts: Readonly<Record<string, string>>
  paused: () => boolean
  progress: (value: CollectionProgress) => void
  completed: (task: ResearchTask) => void
  started: (task: ResearchTask) => void
}) {
  for (const task of tasks) {
    if (options.paused()) break
    if (task.status === 'completed') continue
    options.started(task)
    const completed = await executeResearchTask(adminId, task, options.accounts[task.id] || '', options.progress)
    options.completed(completed)
    // 每次点击只执行下一项，批量关键词不再自动连续访问平台。
    break
  }
}
