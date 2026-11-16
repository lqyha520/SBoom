import { localFetch } from './local-access'
import { request } from './api'

export type ResearchPeriod = 'day' | 'week' | 'half_year' | 'all'
export type ResearchSort = 'general' | 'popular' | 'latest'
export type ResearchStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface ResearchNote {
  note_id: string
  title: string
  author: string
  published_text: string
  likes_text: string
  likes_count: number | null
  url: string
  sort_rank: number
  captured_at: string
}

export interface ResearchTask {
  id: string
  grade: string
  subject: string
  keyword: string
  period: ResearchPeriod
  sort_by: ResearchSort
  note_limit: number
  status: ResearchStatus
  note_count: number
  median_likes: number | null
  average_likes: number | null
  error: string
  created_at: string
  finished_at: string
  items?: ResearchNote[]
  batch_id?: string
  batch_position?: number
}

export interface ResearchTaskInput {
  grade: string
  subject: string
  keyword: string
  period: ResearchPeriod
  sort_by: ResearchSort
  note_limit: number
}

export interface ResearchTaskPage {
  items: ResearchTask[]
  total: number
  page: number
  page_size: number
}

export interface CollectorStatus {
  connected: boolean
  enabled: boolean
  busy: boolean
  version?: number
  pause_reason?: string
}

const base = '/api/v1/admin/xhs-research/tasks'
function adminMutation(adminId: number, method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Workspace-User': String(adminId) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  }
}

export const listResearchTasks = (page = 1, pageSize = 10) =>
  request<ResearchTaskPage>(`${base}?page=${page}&page_size=${pageSize}`)
export const getResearchTask = (id: string) => request<ResearchTask>(`${base}/${encodeURIComponent(id)}`)
export const createResearchTask = (adminId: number, input: ResearchTaskInput) =>
  request<ResearchTask>(base, adminMutation(adminId, 'POST', input))
export const startResearchTask = (adminId: number, id: string) =>
  request<ResearchTask>(`${base}/${encodeURIComponent(id)}/start`, adminMutation(adminId, 'POST'))
export const saveResearchResults = (adminId: number, id: string, items: ResearchNote[]) =>
  request<ResearchTask>(`${base}/${encodeURIComponent(id)}/results`, adminMutation(adminId, 'POST', { items }))
export const failResearchTask = (adminId: number, id: string, error: string) =>
  request<ResearchTask>(`${base}/${encodeURIComponent(id)}/failure`, adminMutation(adminId, 'POST', { error }))
export const deleteResearchTask = (adminId: number, id: string) =>
  request<void>(`${base}/${encodeURIComponent(id)}`, { method: 'DELETE', headers: { 'X-Workspace-User': String(adminId) } })

const collectorBase = 'http://127.0.0.1:17632'
export async function getCollectorStatus(): Promise<CollectorStatus> {
  try {
    const response = await localFetch(`${collectorBase}/health`, { signal: AbortSignal.timeout(1200), cache: 'no-store' })
    if (!response.ok) return { connected: false, enabled: false, busy: false }
    const value = await response.json() as { enabled?: boolean; busy?: boolean; version?: number; pause_reason?: string }
    return { connected: true, enabled: value.enabled === true, busy: value.busy === true, ...(value.version ? { version: value.version } : {}),
      ...(value.pause_reason ? { pause_reason: value.pause_reason } : {}) }
  } catch { return { connected: false, enabled: false, busy: false } }
}

export async function setCollectorEnabled(enabled: boolean, confirmed = false): Promise<CollectorStatus> {
  const response = await localFetch(`${collectorBase}/control`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    signal: AbortSignal.timeout(30_000), cache: 'no-store',
    body: JSON.stringify({ enabled, ...(confirmed ? { confirmed: true } : {}) }),
  })
  if (!response.ok) throw new Error(await readCollectorError(response))
  const value = await response.json() as { enabled?: boolean; busy?: boolean; pause_reason?: string }
  return { connected: true, enabled: value.enabled === true, busy: value.busy === true,
    ...(value.pause_reason ? { pause_reason: value.pause_reason } : {}) }
}

export async function openCollectorBrowser(accountId: string): Promise<void> {
  const response = await localFetch(`${collectorBase}/open`, {
    method: 'POST', signal: AbortSignal.timeout(30_000), cache: 'no-store',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ account_id: accountId }),
  })
  if (!response.ok) throw new Error(await readCollectorError(response))
}

export interface CollectionProgress {
  task_id: string
  account_id?: string
  status: 'running' | 'completed' | 'failed'
  stage: 'opening' | 'loading' | 'filtering' | 'collecting' | 'completed' | 'failed' | 'saving' | 'retrying'
  collected: number
  total: number
  error?: string
  error_code?: string
  retryable?: boolean
  cached?: boolean
  items?: ResearchNote[]
}
export const progressLabels: Record<CollectionProgress['stage'], string> = {
  opening: '正在打开浏览器', loading: '正在加载搜索页', filtering: '正在应用筛选', collecting: '正在采集笔记',
  saving: '正在保存结果', completed: '采集完成', failed: '采集失败', retrying: '网络异常，正在重试一次',
}
export class CollectorError extends Error {
  constructor(message: string, public code: string, public retryable = false) { super(message) }
}
async function collectorFetch(url: string, init?: RequestInit): Promise<Response> {
  try { return await localFetch(url, { ...init, signal: AbortSignal.timeout(10_000), cache: 'no-store' }) }
  catch (cause) { if (cause instanceof Error && 'code' in cause && cause.code === 'permission_denied') throw cause; throw new CollectorError('与本机采集器的连接中断。恢复连接后可继续取回结果。', 'bridge_network', true) }
}
export async function getCollectionAccount(taskId: string): Promise<string> {
  const response = await collectorFetch(`${collectorBase}/jobs/${encodeURIComponent(taskId)}`)
  if (response.status === 404) return ''
  if (!response.ok) throw new CollectorError(await readCollectorError(response), 'bridge')
  const job = await response.json() as CollectionProgress
  if (job.task_id !== taskId || !job.account_id) throw new CollectorError('本机任务没有账号信息，请更新采集器后重试。', 'upgrade_required')
  return job.account_id
}
export async function collectLocally(task: ResearchTask, accountId: string, onProgress?: (value: CollectionProgress) => void): Promise<ResearchNote[]> {
  if (!accountId) throw new CollectorError('请先选择采集账号。', 'account_required')
  const response = await collectorFetch(`${collectorBase}/jobs`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      task_id: task.id, account_id: accountId, retry: true,
      query: buildResearchQuery(task),
      grade: task.grade, subject: task.subject, period: task.period, sort_by: task.sort_by,
      note_limit: task.note_limit,
    }),
  })
  if (!response.ok) throw new CollectorError(response.status === 404 ? '本机采集器版本较旧，请重启更新后的采集器。' : await readCollectorError(response), response.status === 404 ? 'upgrade_required' : 'bridge', false)
  let job = await response.json() as CollectionProgress
  const deadline = Date.now() + 300_000
  while (true) {
    if (job.task_id !== task.id) throw new Error('本机采集器返回了不同任务的数据，请刷新后重试。')
    if (job.account_id !== accountId) throw new Error('本机采集器返回的账号与任务不一致，已停止处理。')
    onProgress?.(job)
    if (job.status === 'failed') throw new CollectorError(job.error || '采集失败', job.error_code || 'unknown', job.retryable === true)
    if (job.status === 'completed') {
      if (!Array.isArray(job.items)) throw new Error('本机采集器返回的数据格式不正确')
      return job.items
    }
    if (Date.now() > deadline) throw new CollectorError('采集仍未完成，请稍后点击继续采集取回结果。', 'waiting', false)
    await new Promise(resolve => setTimeout(resolve, 1000))
    const next = await collectorFetch(`${collectorBase}/jobs/${encodeURIComponent(task.id)}`)
    if (!next.ok) throw new CollectorError(await readCollectorError(next), 'bridge')
    job = await next.json() as CollectionProgress
  }
}

async function readCollectorError(response: Response): Promise<string> {
  try {
    const value = await response.json() as { error?: string }
    if (value.error) return value.error
  } catch { /* 后续使用通用错误 */ }
  return `本机采集器请求失败（${response.status}）`
}

export function researchSearchUrl(task: ResearchTask) {
  return `https://www.xiaohongshu.com/search_result/?keyword=${encodeURIComponent(buildResearchQuery(task))}`
}

export function buildResearchQuery(task: Pick<ResearchTask, 'grade' | 'subject' | 'keyword'>) {
  const keyword = task.keyword.trim()
  return keyword ? `${task.grade}${task.subject} ${keyword}` : `${task.grade}${task.subject}`
}

export type NoteMarkStatus = '' | 'reference' | 'planned' | 'done' | 'irrelevant'
export const markLabels: Record<NoteMarkStatus, string> = { '': '未标记', reference: '值得参考', planned: '准备做', done: '已做过', irrelevant: '不相关' }
export interface NoteMark { favorite: boolean; mark_status: NoteMarkStatus; remark: string; revision: number }
export interface LibraryNote extends Omit<ResearchNote, 'sort_rank'>, NoteMark {
  seen_count: number; seen_before: boolean; grade: string; subject: string; keyword: string
}
export interface NoteFilters {
  task_id?: string; q?: string; author?: string; exclude?: string; min_likes?: number
  favorite_only?: boolean; status?: NoteMarkStatus | 'all'; hide_seen?: boolean
  sort?: 'likes_desc' | 'likes_asc' | 'latest' | 'earliest'; page?: number; page_size?: number
}
export interface NotePage { items: LibraryNote[]; total: number; page: number; page_size: number }
const researchBase = '/api/v1/admin/xhs-research'
export const getResearchNote = (id: string) => request<LibraryNote>(`${researchBase}/notes/${encodeURIComponent(id)}`)
export const listResearchNotes = (filters: NoteFilters) => {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) if (value !== undefined) query.set(key, String(value))
  return request<NotePage>(`${researchBase}/notes?${query}`)
}
export const saveNoteMark = (adminId: number, note: LibraryNote, changes: Partial<NoteMark>) => {
  const value = { ...note, ...changes }
  return request<NoteMark>(`${researchBase}/notes/${encodeURIComponent(note.note_id)}/mark`, adminMutation(adminId, 'PUT', {
    favorite: value.favorite, status: value.mark_status, remark: value.remark, revision: note.revision,
  }))
}
export interface NoteObservation { task_id: string; grade: string; subject: string; keyword: string; captured_at: string; likes_count: number | null; likes_text: string }
export const getNoteHistory = (noteId: string, page = 1) => request<{ items: NoteObservation[]; total: number }>(`${researchBase}/notes/${encodeURIComponent(noteId)}/history?page=${page}`)
export const exportResearchNotes = (adminId: number, filters: NoteFilters, noteIds?: string[]) =>
  request<Blob>(`${researchBase}/notes/export`, adminMutation(adminId, 'POST', { filters, ...(noteIds ? { note_ids: noteIds } : {}) }), 'blob')
export interface ResearchBatch { id: string; items: ResearchTask[] }
export interface BatchSummary { id: string; created_at: string; total: number; completed: number }
export const createResearchBatch = (adminId: number, input: ResearchTaskInput, keywords: string[]) =>
  request<ResearchBatch>(`${researchBase}/batches`, adminMutation(adminId, 'POST', { ...input, keywords }))
export const listResearchBatches = () => request<{ items: BatchSummary[] }>(`${researchBase}/batches`)
export const getResearchBatch = (id: string) => request<ResearchBatch>(`${researchBase}/batches/${encodeURIComponent(id)}`)
