import { openDB, type DBSchema } from 'idb'
import type { GenerationRun } from './generation'
import type { Difficulty, PaperData, PaperStyle, PaperTemplate, Section } from './types'
import { deepClone } from './utils'

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

export type HistoryReason = 'manual' | 'generated' | 'before-restore' | 'before-generate'
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
}

const database = () => openDB<WorkspaceDB>('learn-coach-workspaces', 1, {
  upgrade(db) {
    for (const name of ['drafts', 'history'] as const) {
      db.createObjectStore(name, { keyPath: 'id' }).createIndex('ownerUpdated', ['owner', 'updatedAt'])
    }
  },
})

function ownedRange(owner: string) {
  if (!owner) throw new Error('未绑定账号，不能访问本地试卷')
  return IDBKeyRange.bound([owner, 0], [owner, Number.MAX_SAFE_INTEGER])
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
  const current = crypto.randomUUID()
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
  const db = await database()
  const updatedAt = Date.now()
  try {
    await db.put('drafts', { id: owner + ':' + sessionId, owner, updatedAt, snapshot: deepClone(snapshot) })
    return updatedAt
  } finally { db.close() }
}

export async function addHistory(owner: string, snapshot: WorkspaceSnapshot, reason: HistoryReason): Promise<HistoryEntry> {
  ownedRange(owner)
  const questions = snapshot.papers.length
    ? snapshot.papers.reduce((n, paper) => n + paper.sections.reduce((m, section) => m + section.data.questions.length, 0), 0)
    : snapshot.sections.reduce((n, section) => n + (section.data?.questions.length || 0), 0)
  const entry: HistoryEntry = {
    id: crypto.randomUUID(), owner, updatedAt: Date.now(), title: snapshot.title || snapshot.keyword || '未命名试卷',
    grade: snapshot.grade, subject: snapshot.subject, keyword: snapshot.keyword,
    paperCount: snapshot.papers.length, questionCount: questions, reason,
  }
  const db = await database()
  try {
    await db.add('history', { ...entry, snapshot: deepClone(snapshot) })
    return entry
  } finally { db.close() }
}

export async function listHistory(owner: string): Promise<HistoryEntry[]> {
  const range = ownedRange(owner)
  const db = await database()
  try {
    const entries: HistoryEntry[] = []
    let cursor = await db.transaction('history').store.index('ownerUpdated').openCursor(range, 'prev')
    while (cursor) {
      const { snapshot: _snapshot, ...entry } = cursor.value
      entries.push(entry)
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
    const tx = db.transaction('history', 'readwrite')
    const record = await tx.store.get(id)
    if (record?.owner === owner) await tx.store.delete(id)
    await tx.done
  } finally { db.close() }
}
