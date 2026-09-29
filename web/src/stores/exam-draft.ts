/** 草稿保存、版本历史和账号切换时的持久化生命周期。 */
import type { ExamWorkspace } from './exam-context'
import { randomId } from '../../../shared/webcrypto'
import { deepClone } from '../utils'
import * as persistence from '../persistence'
import type { WorkspaceSnapshot, HistoryReason } from '../persistence'
import { createWorkspaceDraft, workspaceSnapshot, type WorkspaceDraft } from '../workspace-draft'
import { styleSaveTimers } from './exam-local'
const draftRuntimes = new WeakMap<object, WorkspaceDraft>()
const draftReleases = new WeakMap<object, () => void>()
const historyReads = new WeakMap<object, number>()


export const draftActions = {
  captureSnapshot(this: ExamWorkspace): WorkspaceSnapshot {
    return deepClone(workspaceSnapshot(this))
  },

  applySnapshot(this: ExamWorkspace, snapshot: WorkspaceSnapshot) {
    this.undoStack = []
    this.redoStack = []
    this.generationJobs = []
    this.stopRequested = false
    const value = deepClone(snapshot)
    this.grade = value.grade
    this.subject = value.subject
    this.keyword = value.keyword
    this.selectedTags = value.selectedTags
    this.title = value.title
    this.titleHtml = value.titleHtml
    this.difficulty = value.difficulty
    this.hiddenElements = value.hiddenElements
    this.sections = value.sections.map((section) => ({
      ...section,
      status: section.status === 'loading' ? 'error' : section.status,
      error: section.status === 'loading' ? '生成请求已中断，可查询原请求结果' : section.error,
    }))
    this.papers = value.papers
    this.view = value.view === 'result' && value.papers.length ? 'result' : 'build'
    this.paperCount = value.paperCount
    this.addDayLabel = value.addDayLabel
    this.templateId = value.templateId
    this.customTemplate = value.customTemplate
    this.style = value.style
    this.generateWarn = value.generateWarn
    this.generateError = value.generateError
    this.pendingRun = value.pendingRun
    this.pendingRun?.jobs.forEach((job) =>
      job.chunks.forEach((chunk) => {
        if (chunk.state === 'running') chunk.state = 'unknown'
      }),
    )
    this.failedCount = this.pendingRun?.jobs.length || 0
    this.generating = false
    this.layoutMode = false
    this.scope = null
  },

  async initPersistence(this: ExamWorkspace) {
    if (this.persistenceReady) return
    if (!this.ownerId) {
      this.persistenceReady = true
      this.draftState = 'saved'
      return
    }
    // draftSession 抛错也必须留下 runtime：否则 flushDraft() 恒返回 false，
    // 「退出登录」会被「草稿未保存」永久拦下，而真正的原因（存储不可用）没人看得到。
    let session: { previous: string | null; current: string; release?: () => void } = {
      previous: null,
      current: randomId(),
    }
    try {
      session = await persistence.claimDraftSession(this.ownerId, persistence.draftSession(this.ownerId))
    } catch (error) {
      this.storageError = error instanceof Error ? error.message : '本地草稿会话初始化失败'
    }
    const owner = this.ownerId
    this.draftId = session.current
    if (session.release) draftReleases.set(this, session.release)
    const runtime = createWorkspaceDraft({
      source: this,
      save: (snapshot) => persistence.saveDraft(owner, session.current, snapshot),
      canQueue: () => this.persistenceReady && !this.accountChanged,
      saving: () => {
        this.draftState = 'saving'
      },
      saved: (updatedAt) => {
        this.draftSavedAt = updatedAt
        this.draftState = 'saved'
        this.storageError = ''
      },
      failed: () => {
        this.draftState = 'error'
        this.storageError = '本地保存失败，可能存储空间不足或浏览器禁用了存储；当前内容仍在页面中'
      },
    })
    draftRuntimes.set(this, runtime)
    try {
      const draft = await persistence.loadDraft(owner, session.previous)
      if (draft) {
        this.applySnapshot(draft.snapshot)
        this.draftSavedAt = draft.updatedAt
      }
      await persistence.pruneWorkspace(owner, session.current)
      await this.refreshHistory()
      this.draftState = 'saved'
    } catch (error) {
      this.draftState = 'error'
      this.storageError = error instanceof Error ? error.message : '本地草稿读取失败'
    }
    this.persistenceReady = true
  },

  queueDraft(this: ExamWorkspace) {
    draftRuntimes.get(this)?.queue()
  },

  async flushDraft(this: ExamWorkspace): Promise<boolean> {
    return draftRuntimes.get(this)?.flush() ?? false
  },

  async suspendForAccountChange(this: ExamWorkspace): Promise<boolean> {
    this.accountChanged = true
    const saved = await this.flushDraft()
    draftRuntimes.get(this)?.stop()
    return saved
  },

  disposePersistence(this: ExamWorkspace) {
    const runtime = draftRuntimes.get(this)
    const release = draftReleases.get(this)
    if (runtime) {
      runtime.stop()
      void runtime.idle().finally(() => release?.())
      draftRuntimes.delete(this)
    } else release?.()
    draftReleases.delete(this)
    historyReads.set(this, (historyReads.get(this) || 0) + 1)
    clearTimeout(styleSaveTimers.get(this))
  },

  async refreshHistory(this: ExamWorkspace, query?: string, offset?: number) {
    if (!this.ownerId) return
    query ??= this.historyQuery
    offset ??= this.historyOffset
    const sequence = (historyReads.get(this) || 0) + 1
    historyReads.set(this, sequence)
    this.historyLoading = true
    this.historyError = ''
    try {
      const entries = await persistence.listHistory(this.ownerId, { query, offset, limit: 21 })
      if (historyReads.get(this) !== sequence) return
      if (!entries.length && offset > 0) {
        await this.refreshHistory(query, Math.max(0, offset - 20))
        return
      }
      this.history = entries.slice(0, 20)
      this.historyHasMore = entries.length > 20
      this.historyQuery = query
      this.historyOffset = offset
      if (this.storageError === '历史记录读取失败，现有数据未删除') this.storageError = ''
    } catch {
      if (historyReads.get(this) === sequence)
        this.historyError = this.storageError = '历史记录读取失败，现有数据未删除'
    } finally {
      if (historyReads.get(this) === sequence) this.historyLoading = false
    }
  },

  async saveHistory(this: ExamWorkspace, reason: HistoryReason = 'manual'): Promise<boolean> {
    if (!this.ownerId || this.accountChanged) return false
    try {
      await persistence.addHistory(this.ownerId, this.captureSnapshot(), reason)
      await this.refreshHistory()
      return true
    } catch {
      this.storageError = '历史版本保存失败，可能存储空间不足；现有历史未删除'
      return false
    }
  },

  async saveVersion(this: ExamWorkspace): Promise<boolean> {
    if (this.historyBusy || this.generating || this.accountChanged) return false
    this.historyBusy = true
    try {
      return await this.saveHistory('manual')
    } finally {
      this.historyBusy = false
    }
  },

  async restoreHistory(this: ExamWorkspace, id: string): Promise<boolean> {
    if (this.generating || this.historyBusy || this.accountChanged) return false
    this.historyBusy = true
    try {
      const snapshot = await persistence.getHistory(this.ownerId, id)
      if ((this.sections.length || this.papers.length || this.keyword) && !(await this.saveHistory('before-restore')))
        return false
      this.applySnapshot(snapshot)
      await this.flushDraft()
      if (this.subject) await this.selectSubject(this.subject)
      return true
    } catch (error) {
      this.storageError = error instanceof Error ? error.message : '历史版本恢复失败'
      return false
    } finally {
      this.historyBusy = false
    }
  },

  async deleteHistory(this: ExamWorkspace, id: string) {
    await persistence.removeHistory(this.ownerId, id)
    await this.refreshHistory()
  },
}
