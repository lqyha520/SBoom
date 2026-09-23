import { nextTick, watch } from 'vue'
import type { WorkspaceSnapshot } from './persistence'

const fields = [
  'grade', 'subject', 'keyword', 'selectedTags', 'title', 'titleHtml', 'difficulty',
  'hiddenElements', 'sections', 'papers', 'view', 'paperCount', 'addDayLabel',
  'templateId', 'customTemplate', 'style', 'generateWarn', 'generateError', 'pendingRun',
] as const satisfies readonly (keyof WorkspaceSnapshot)[]

type Workspace = Omit<WorkspaceSnapshot, 'version'>

/** 仅投影字段；需要独立副本的调用方必须在异步边界前复制。 */
export function workspaceSnapshot(source: Workspace): WorkspaceSnapshot {
  return { version: 1, ...Object.fromEntries(fields.map(key => [key, source[key]])) } as WorkspaceSnapshot
}

/** 各字段独立订阅，修改标题或样式时不遍历未变化的题目。 */
export function watchWorkspace(source: Workspace, changed: () => void): () => void {
  const stops = fields.map(key => watch(() => source[key], changed, { deep: true }))
  return () => stops.forEach(stop => stop())
}

interface DraftOptions {
  source: Workspace
  // save 必须同步复制输入，再进行异步写入（persistence.saveDraft 遵守此约定）。
  save(snapshot: WorkspaceSnapshot): Promise<number>
  saving(): void
  saved(updatedAt: number): void
  failed(): void
  canQueue(): boolean
}

/** 同一时刻只有一个写入；慢磁盘期间的编辑合并为下一次最新快照。 */
export function createWorkspaceDraft(options: DraftOptions) {
  let revision = 0, savedRevision = -1
  let timer: ReturnType<typeof setTimeout> | undefined
  let pending: Promise<boolean> | undefined
  let stopped = false

  function queue() {
    revision++
    if (stopped || !options.canQueue()) return
    clearTimeout(timer)
    options.saving()
    timer = setTimeout(() => { void flush() }, 350)
  }

  const stopWatching = watchWorkspace(options.source, queue)

  async function drain(): Promise<boolean> {
    while (savedRevision < revision) {
      const writingRevision = revision
      options.saving()
      try {
        const updatedAt = await options.save(workspaceSnapshot(options.source))
        savedRevision = writingRevision
        if (savedRevision === revision) options.saved(updatedAt)
      } catch {
        options.failed()
        return false
      }
    }
    return true
  }

  async function flush(): Promise<boolean> {
    // 收齐同一轮直接修改及嵌套编辑，生成请求 ID 也必须在本次保存中。
    await nextTick()
    clearTimeout(timer)
    if (!pending) pending = drain().finally(() => { pending = undefined })
    return pending
  }

  function stop() {
    stopped = true
    clearTimeout(timer)
    stopWatching()
  }

  return { queue, flush, stop, idle: async () => { await nextTick(); await pending } }
}

export type WorkspaceDraft = ReturnType<typeof createWorkspaceDraft>
