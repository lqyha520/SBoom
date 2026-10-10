import { openDB, type DBSchema } from 'idb'
import type { GenerationRun } from './generation'
import type { Difficulty, PaperData, PaperStyle, PaperTemplate, Section } from './types'
import { deepClone } from './utils'
// crypto.randomUUID 是 [SecureContext] 限定 API，http://内网IP 下不存在
import { randomId } from '../../shared/webcrypto'
import { draftLockName } from './draft-session'
export { claimDraftSession } from './draft-session'

export interface WorkspaceSnapshot {
  version: 1
  grade: string
  subject: string
  keyword: string
  selectedTags: string[]
  title: string
  titleHtml: string
  difficulty: Difficulty
  hiddenElements: string[]
  sections: Section[]
  papers: PaperData[]
  view: 'build' | 'result'
  paperCount: number
  addDayLabel: boolean
  templateId: string
  customTemplate: PaperTemplate
  style: PaperStyle
  generateWarn: string
  generateError: string
  pendingRun: GenerationRun | null
}

interface DraftRecord {
  id: string
  owner: string
  updatedAt: number
  snapshot: WorkspaceSnapshot
}
export interface DraftEntry { id: string; owner: string; updatedAt: number; title: string; grade: string; subject: string }
const draftEntry = (record: DraftRecord): DraftEntry => ({ id: record.id, owner: record.owner, updatedAt: record.updatedAt,
  title: record.snapshot.title || record.snapshot.keyword || '未命名草稿', grade: record.snapshot.grade, subject: record.snapshot.subject })

export type HistoryReason = 'manual' | 'generated' | 'before-restore' | 'before-generate' | 'before-clear'
export interface HistoryEntry {
  id: string
  owner: string
  updatedAt: number
  title: string
  grade: string
  subject: string
  keyword: string
  paperCount: number
  questionCount: number
  reason: HistoryReason
}

interface HistoryRecord extends HistoryEntry { snapshot: WorkspaceSnapshot }

interface WorkspaceDB extends DBSchema {
  drafts: { key: string; value: DraftRecord; indexes: { ownerUpdated: [string, number] } }
  history: { key: string; value: HistoryRecord; indexes: { ownerUpdated: [string, number] } }
  historyMeta: { key: string; value: HistoryEntry; indexes: { ownerUpdated: [string, number] } }
  draftMeta: { key: string; value: DraftEntry; indexes: { ownerUpdated: [string, number] } }
}

const database = () => openDB<WorkspaceDB>('learn-coach-workspaces', 2, {
  upgrade(db, oldVersion, _newVersion, tx) {
    for (const name of ['drafts', 'history', 'draftMeta', 'historyMeta'] as const) {
      if (!db.objectStoreNames.contains(name)) db.createObjectStore(name, { keyPath: 'id' }).createIndex('ownerUpdated', ['owner', 'updatedAt'])
    }
    if (oldVersion === 1) {
      // 旧版本只在升级事务中扫描一次；列表从此只读摘要，原快照保持不变。
      void (async () => {
        let history = await tx.objectStore('history').openCursor()
        while (history) {
          const { snapshot: _snapshot, ...entry } = history.value
          await tx.objectStore('historyMeta').put(entry)
          history = await history.continue()
        }
        let drafts = await tx.objectStore('drafts').openCursor()
        while (drafts) {
          await tx.objectStore('draftMeta').put(draftEntry(drafts.value))
          drafts = await drafts.continue()
        }
      })().catch(() => { try { tx.abort() } catch { /* 升级失败保留原数据库。 */ } })
    }
  },
})

function ownedRange(owner: string) {
  if (!owner) throw new Error('未绑定账号，不能访问本地试卷')
  return IDBKeyRange.bound([owner, 0], [owner, Number.MAX_SAFE_INTEGER])
}

function assertNotPurged(owner: string) {
  let purged = false
  try { purged = !!localStorage.getItem('lc_purge:' + owner) } catch { /* IndexedDB 不依赖 localStorage 可用。 */ }
  if (purged) throw new Error('本机数据已清除，请重新登录后继续编辑')
}

function validateSnapshot(value: WorkspaceSnapshot): WorkspaceSnapshot {
  if (!value || value.version !== 1 || !Array.isArray(value.sections) || !Array.isArray(value.papers)
      || typeof value.grade !== 'string' || typeof value.keyword !== 'string' || !value.style || !value.customTemplate
      || value.sections.some(section => !section || typeof section.id !== 'string' || !section.layout)
      || value.papers.some(paper => !paper || !Array.isArray(paper.sections))) {
    throw new Error('本地草稿格式不完整，原数据仍保留')
  }
  return deepClone(value)
}

export function draftSession(owner: string): { previous: string | null; current: string } {
  const current = randomId()
  const key = 'lc_draft_session:' + owner
  let previous: string | null = null
  try {
    previous = sessionStorage.getItem(key)
    // A duplicated tab can inherit sessionStorage. Give each page its own writer.
    sessionStorage.setItem(key, current)
  } catch { /* IndexedDB can still save the draft when sessionStorage is disabled. */ }
  return { previous, current }
}

export async function loadDraft(owner: string, sessionId?: string | null): Promise<DraftRecord | null> {
  const range = ownedRange(owner)
  const db = await database()
  try {
    const sameTab = sessionId ? await db.get('drafts', owner + ':' + sessionId) : undefined
    const record = sameTab || (await db.transaction('drafts').store.index('ownerUpdated').openCursor(range, 'prev'))?.value
    return record ? { ...record, snapshot: validateSnapshot(record.snapshot) } : null
  } finally { db.close() }
}

export async function saveDraft(owner: string, sessionId: string, snapshot: WorkspaceSnapshot): Promise<number> {
  ownedRange(owner)
  // 在首个异步边界前隔离调用方的响应式数据，避免等待数据库时内容变化。
  const captured = deepClone(snapshot)
  const db = await database()
  const updatedAt = Date.now()
  try {
    assertNotPurged(owner)
    const record = { id: owner + ':' + sessionId, owner, updatedAt, snapshot: captured }
    const tx = db.transaction(['drafts', 'draftMeta'], 'readwrite')
    await tx.objectStore('drafts').put(record)
    await tx.objectStore('draftMeta').put(draftEntry(record))
    await tx.done
    return updatedAt
  } finally { db.close() }
}

export async function addHistory(owner: string, snapshot: WorkspaceSnapshot, reason: HistoryReason): Promise<HistoryEntry> {
  ownedRange(owner)
  snapshot = deepClone(snapshot)
  const questions = snapshot.papers.length
    ? snapshot.papers.reduce((n, paper) => n + paper.sections.reduce((m, section) => m + section.data.questions.length, 0), 0)
    : snapshot.sections.reduce((n, section) => n + (section.data?.questions.length || 0), 0)
  const entry: HistoryEntry = {
    id: randomId(), owner, updatedAt: Date.now(), title: snapshot.title || snapshot.keyword || '未命名试卷',
    grade: snapshot.grade, subject: snapshot.subject, keyword: snapshot.keyword,
    paperCount: snapshot.papers.length, questionCount: questions, reason,
  }
  const db = await database()
  try {
    assertNotPurged(owner)
    const tx = db.transaction(['history', 'historyMeta'], 'readwrite')
    await tx.objectStore('history').add({ ...entry, snapshot })
    await tx.objectStore('historyMeta').add(entry)
    await tx.done
    // 历史只保留有界的恢复窗口，避免每次生成积累两份无限增长的快照。
    await pruneHistory(owner)
    return entry
  } finally { db.close() }
}

export async function listHistory(owner: string, options: { offset?: number; limit?: number; query?: string } = {}): Promise<HistoryEntry[]> {
  const range = ownedRange(owner)
  const db = await database()
  try {
    const entries: HistoryEntry[] = []
    const query = (options.query || '').trim().toLowerCase()
    const offset = Math.max(0, options.offset || 0), limit = Math.min(100, Math.max(1, options.limit || 20))
    let skipped = 0
    let cursor = await db.transaction('historyMeta').store.index('ownerUpdated').openCursor(range, 'prev')
    while (cursor) {
      const entry = cursor.value
      if ([entry.title, entry.grade, entry.subject, entry.keyword].join(' ').toLowerCase().includes(query)) {
        if (skipped++ >= offset) entries.push(entry)
        if (entries.length >= limit) break
      }
      cursor = await cursor.continue()
    }
    return entries
  } finally { db.close() }
}

export async function getHistory(owner: string, id: string): Promise<WorkspaceSnapshot> {
  ownedRange(owner)
  const db = await database()
  try {
    const record = await db.get('history', id)
    if (!record || record.owner !== owner) throw new Error('历史版本不存在')
    return validateSnapshot(record.snapshot)
  } finally { db.close() }
}

export async function removeHistory(owner: string, id: string): Promise<void> {
  ownedRange(owner)
  const db = await database()
  try {
    const tx = db.transaction(['history', 'historyMeta'], 'readwrite')
    const record = await tx.objectStore('historyMeta').get(id)
    if (record?.owner === owner) {
      await tx.objectStore('history').delete(id)
      await tx.objectStore('historyMeta').delete(id)
    }
    await tx.done
  } finally { db.close() }
}

export async function listDrafts(owner: string, offset = 0): Promise<DraftEntry[]> {
  const range = ownedRange(owner), db = await database()
  try {
    const entries: DraftEntry[] = []
    let cursor = await db.transaction('draftMeta').store.index('ownerUpdated').openCursor(range, 'prev')
    if (cursor && offset > 0) cursor = await cursor.advance(offset)
    while (cursor && entries.length < 21) { entries.push(cursor.value); cursor = await cursor.continue() }
    return entries
  } finally { db.close() }
}

export async function removeDraft(owner: string, entry: DraftEntry, currentSession: string): Promise<void> {
  ownedRange(owner)
  if (entry.owner !== owner || entry.id === owner + ':' + currentSession) throw new Error('不能删除当前页面或其他账号的草稿')
  const remove = async () => {
    const db = await database()
    try {
      const tx = db.transaction(['drafts', 'draftMeta'], 'readwrite')
      const latest = await tx.objectStore('draftMeta').get(entry.id)
      if (latest && (latest.owner !== owner || latest.updatedAt !== entry.updatedAt)) throw new Error('草稿已更新，请刷新列表后再操作')
      await tx.objectStore('drafts').delete(entry.id)
      await tx.objectStore('draftMeta').delete(entry.id)
      await tx.done
    } finally { db.close() }
  }
  if (!navigator.locks) { await remove(); return }
  await navigator.locks.request(draftLockName(owner, entry.id.slice(owner.length + 1)), { ifAvailable: true }, async lock => {
    if (!lock) throw new Error('草稿正在其他页面使用，请先关闭该页面')
    await remove()
  })
}

export const RETENTION = { drafts: 10, history: 100, days: 30 } as const

async function pruneHistory(owner: string): Promise<void> {
  const db = await database()
  try {
    const tx = db.transaction(['history', 'historyMeta'], 'readwrite')
    let cursor = await tx.objectStore('historyMeta').index('ownerUpdated').openCursor(ownedRange(owner), 'prev')
    let count = 0
    while (cursor) {
      if (++count > RETENTION.history || (count > 1 && cursor.value.updatedAt < Date.now() - RETENTION.days * 86400000)) {
        await tx.objectStore('history').delete(cursor.value.id)
        await cursor.delete()
      }
      cursor = await cursor.continue()
    }
    await tx.done
  } finally { db.close() }
}

/** 正在其他标签页使用的草稿有 Web Lock；不支持锁时只清理至少一天未更新的副本。 */
export async function pruneWorkspace(owner: string, currentSession: string): Promise<void> {
  await pruneHistory(owner)
  const db = await database()
  let entries: DraftEntry[]
  try { entries = (await db.getAllFromIndex('draftMeta', 'ownerUpdated', ownedRange(owner))).reverse() }
  finally { db.close() }
  for (const [index, entry] of entries.entries()) {
    if (entry.id === owner + ':' + currentSession) continue
    if (index < RETENTION.drafts && entry.updatedAt >= Date.now() - RETENTION.days * 86400000) continue
    if (!navigator.locks && entry.updatedAt >= Date.now() - 86400000) continue
    try { await removeDraft(owner, entry, currentSession) }
    catch { /* 活跃页面或并发更新拥有优先权，下次启动再清理。 */ }
  }
}

/** 只删除本账号的草稿/历史，不触碰其他账号的数据。 */
export async function clearWorkspace(owner: string): Promise<void> {
  const db = await database()
  try {
    const tx = db.transaction(['drafts', 'draftMeta', 'history', 'historyMeta'], 'readwrite')
    for (const name of ['drafts', 'draftMeta', 'history', 'historyMeta'] as const) {
      let cursor = await tx.objectStore(name).index('ownerUpdated').openCursor(ownedRange(owner))
      while (cursor) { await cursor.delete(); cursor = await cursor.continue() }
    }
    await tx.done
  } finally { db.close() }
}
