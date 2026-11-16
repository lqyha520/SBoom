import type { ApiResponse, ApiSchemas } from '../../shared/api-schema'
import { computed, onActivated, onDeactivated, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { canAdmin } from './permissions'
import { ApiError, request } from './api'
import { adminRoute, navigateAdmin, useAdminLeaveGuard, type AdminTab } from './navigation'
import { emptyAccountSnapshot, type AccountSnapshot } from './xhs-accounts'
import { randomId } from '../../shared/webcrypto'
import { useXhsDraftBackup } from './xhs-draft-backup'
import type { PublicationMedia } from './xhs-media-cache'

export type WorkflowKind = 'ideas' | 'materials' | 'drafts' | 'publications'
export const workflowTabs: Record<WorkflowKind, AdminTab> = { ideas: 'xhsIdeas', materials: 'xhsMaterials', drafts: 'xhsDrafts', publications: 'xhsPublishing' }
export const workflowLabels = { ideas: '选题库', materials: '资料制作', drafts: '笔记制作', publications: '发布管理' }
export interface BaseData { title: string; status: string }
type Filled<K extends keyof ApiSchemas> = Required<ApiSchemas[K]>
export type IdeaData = Omit<Filled<'Idea'>, 'status' | 'priority' | 'source_publication_id'> & BaseData & { priority: string; source_publication_id?: string }
export type Exercise = Filled<'Exercise'>
export type MaterialData = Omit<Filled<'Material'>, 'status' | 'game_type' | 'difficulty' | 'questions'> & BaseData & { game_type: string; difficulty: string; questions: Exercise[] }
export type CardData = Filled<'Card'>
export type DraftData = Omit<Filled<'Draft'>, 'status' | 'cards' | 'account_profile' | 'source_material_revision'> & BaseData & { cards: CardData[]; account_profile?: AccountSnapshot; source_material_revision?: number }
export type PublicationContent = Filled<'PublicationContent'>
export type PublicationData = Omit<Filled<'PublicationDataResponse'>, 'status' | 'media' | 'account_id' | 'draft_snapshot' | 'draft_revision' | 'custom_content'> & BaseData & { media?: PublicationMedia[]; account_id?: string; draft_snapshot?: DraftData; draft_revision?: number; custom_content: PublicationContent }
export type WorkflowData = IdeaData | MaterialData | DraftData | PublicationData
type WorkflowWire = ApiResponse<'GET /api/v1/admin/xhs-workflow/records/{kind}/{record_id}'>
export type WorkflowRecord<T extends BaseData = WorkflowData> = Omit<WorkflowWire, 'data' | 'admin_id'> & { data: T }
export type WorkflowPage<T extends BaseData = WorkflowData> = Omit<ApiResponse<'GET /api/v1/admin/xhs-workflow/records/{kind}'>, 'items'> & { items: WorkflowRecord<T>[] }
const base = '/api/v1/admin/xhs-workflow'
export const listWorkflow = <T extends BaseData = WorkflowData>(kind: WorkflowKind, params: { q?: string; status?: string; parent_id?: string; page?: number } = {}) => request<WorkflowPage<T>>(`${base}/records/${kind}?${new URLSearchParams(Object.entries(params).map(([key, value]) => [key, String(value)]))}`)
export const getWorkflow = <T extends BaseData = WorkflowData>(kind: WorkflowKind, id: string) => request<WorkflowRecord<T>>(`${base}/records/${kind}/${encodeURIComponent(id)}`)
const mutation = (method: string, body: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export function cleanWorkflowData<T extends BaseData>(value: T): T {
  const data = JSON.parse(JSON.stringify(value)) as T & Partial<PublicationData>
  delete data.draft_snapshot; delete data.draft_revision
  return data
}
// 服务端会去除字符串首尾空白；字段顺序不影响保存结果核对。
export function workflowFingerprint(value: unknown): string {
  const normalize = (item: unknown): unknown => typeof item === 'string' ? item.trim() : Array.isArray(item) ? item.map(normalize) :
    item && typeof item === 'object' ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => [key, normalize(child)])) : item
  return JSON.stringify(normalize(value))
}
export const createWorkflow = <T extends BaseData>(kind: WorkflowKind, id: string, parent_id: string | null, data: T) => request<WorkflowRecord<T>>(`${base}/records/${kind}`, mutation('POST', { id, parent_id, data: cleanWorkflowData(data) }))
export const updateWorkflow = <T extends BaseData>(kind: WorkflowKind, record: WorkflowRecord<T>, data: T) => request<WorkflowRecord<T>>(`${base}/records/${kind}/${record.id}`, mutation('PUT', { revision: record.revision, data: cleanWorkflowData(data) }))
export const workflowVersions = <T extends BaseData>(kind: WorkflowKind, id: string, page: number) => request<{ items: { revision: number; data: T; created_at: string }[]; total: number }>(`${base}/records/${kind}/${id}/versions?page=${page}`)
export function goWorkflow(kind: WorkflowKind, id: string) { navigateAdmin(workflowTabs[kind], { id }) }
export function nextWorkflow(kind: WorkflowKind, parent: string) { navigateAdmin(workflowTabs[kind], { new: '1', parent }) }
export const newIdea = (): IdeaData => ({ title: '', status: 'inbox', grade: '一年级', subject: '数学', keyword: '', audience: '一年级家长', problem: '', angle: '', format: '分层练习', priority: 'normal', due_date: null, source_note_id: '', source_publication_id: '', notes: '' })
export const newMaterial = (): MaterialData => ({ title: '', status: 'draft', grade: '一年级', subject: '数学', keyword: '', game_type: 'fill_blank', difficulty: 'medium', question_count: 10, instructions: '', questions: [], accuracy_checked: false, scope_checked: false, layout_checked: false, review_notes: '', generation_request_id: '' })
export const newDraft = (): DraftData => ({ audience: '家长', angle: '', account_profile: emptyAccountSnapshot(), title: '', status: 'draft', headline: '', title_options: [], body: '', hashtags: '', cover_title: '', cover_subtitle: '', theme: 'green', cards: [], notes: '', generation_request_id: '', source_material_revision: 0 })
export function materialReviewFingerprint(data: MaterialData) {
  return JSON.stringify([data.grade, data.subject, data.keyword, data.game_type, data.difficulty, data.question_count, data.instructions, data.questions])
}
export const newPublication = (): PublicationData => ({ account_id: '', title: '', status: 'planned', source: 'custom', media: [], custom_content: { headline: '', body: '', hashtags: '', media_notes: '' }, account: '', scheduled_at: null, published_at: null, url: '', notes: '', conclusion: '', next_action: '', rights_checked: false, truth_checked: false, privacy_checked: false, media_checked: false, platform_checked: false, review_notes: '' })
export const statusLabels: Record<string, string> = { inbox: '待整理', planned: '已计划', creating: '制作中', done: '已完成', draft: '草稿', review: '待复核', ready: '已就绪', published: '已发布', archived: '已归档' }
export const workflowStatus = (value: string) => statusLabels[value] || value
export const workflowError = (error: unknown) => error instanceof Error ? error.message : '操作失败，请重试'
export const formatWorkflowDate = (date: string) => new Date(date).toLocaleString('zh-CN', { hour12: false })

export function useWorkflow<T extends BaseData>(kind: WorkflowKind, factory: () => T, initialize: (parent: WorkflowRecord | null, data: T) => Promise<void> | void, adminId: number) {
  const items = ref<WorkflowRecord<T>[]>([]) as Ref<WorkflowRecord<T>[]>, total = ref(0), page = ref(1), q = ref(''), filter = ref('')
  const record = ref<WorkflowRecord<T> | null>(null) as Ref<WorkflowRecord<T> | null>, data = ref(factory()) as Ref<T>
  const parent = ref<WorkflowRecord | null>(null), creating = ref(false), editing = ref(false), busy = ref(false), loading = ref(false), error = ref(''), notice = ref('')
  const baseline = ref(''), createId = ref('')
  interface SaveAttempt { id: string; revision: number; parentId: string | null; payload: T }
  const pendingSave = ref<SaveAttempt | null>(null) as Ref<SaveAttempt | null>
  const editorSession = ref(0)
  let sequence = 0, routeKey = '', appliedQuery = ''
  let savedNavigation = false
  const editorScope = ref('')
  const dirty = computed(() => editing.value && JSON.stringify(data.value) !== baseline.value)
  const backup = useXhsDraftBackup({ adminId, scope: () => `${kind}:${editorScope.value}`, enabled: () => editing.value && !loading.value,
    dirty: () => dirty.value, snapshot: () => ({ data: data.value, createId: createId.value, pendingSave: pendingSave.value }), revision: () => String(record.value?.revision || 0),
    restore: value => { data.value = { ...factory(), ...cleanWorkflowData(value.data) }; pendingSave.value = value.pendingSave || null; if (!record.value && value.createId) createId.value = value.createId } })
  const canLeave = () => {
    if (savedNavigation) return true
    if (busy.value) { error.value = '正在保存，请等待保存结果。'; return false }
    backup.persist(); return !dirty.value || window.confirm('有未保存的内容，是否离开？已成功备份的编辑可在本机恢复。')
  }
  useAdminLeaveGuard(() => adminRoute.tab !== workflowTabs[kind] || canLeave())
  async function fetchList() {
    if (adminRoute.tab !== workflowTabs[kind] || editing.value) return
    const key = ++sequence; loading.value = true; error.value = ''
    try {
      const result = await listWorkflow<T>(kind, { q: appliedQuery, status: filter.value, page: page.value })
      if (key !== sequence) return
      const lastPage = Math.max(1, Math.ceil(result.total / 20))
      if (page.value > lastPage) { page.value = lastPage; return }
      items.value = result.items; total.value = result.total
    }
    catch (cause) { if (key === sequence) error.value = workflowError(cause) }
    finally { if (key === sequence) loading.value = false }
  }
  function loadList() {
    appliedQuery = q.value.trim()
    if (page.value !== 1) { page.value = 1; return }
    return fetchList()
  }
  async function readRoute(force = false) {
    if (adminRoute.tab !== workflowTabs[kind] || !canAdmin(workflowTabs[kind])) return
    const key = adminRoute.query
    if (!force && routeKey === key) return
    if (routeKey !== key || !editorSession.value) editorSession.value++
    if (routeKey !== key) pendingSave.value = null
    routeKey = key; error.value = ''; notice.value = ''
    const params = new URLSearchParams(key), id = params.get('id'), isNew = params.get('new') === '1'
    if (isNew && !canAdmin(workflowTabs[kind], 'create')) { editing.value = false; error.value = '没有新增权限'; return }
    editorScope.value = id || `new:${params.get('parent') || ''}:${params.get('source') || ''}`
    editing.value = !!id || isNew; creating.value = isNew
    if (!editing.value) { record.value = null; baseline.value = JSON.stringify(data.value); await fetchList(); return }
    const seq = ++sequence; loading.value = true
    try {
      if (id) {
        const current = await getWorkflow<T>(kind, id)
        const parentKind = ({ materials: 'ideas', drafts: 'materials', publications: 'drafts' } as Record<string, WorkflowKind>)[kind]
        const linked = current.parent_id && parentKind && canAdmin(workflowTabs[parentKind]) ? await getWorkflow(({ materials: 'ideas', drafts: 'materials', publications: 'drafts' } as Record<string, WorkflowKind>)[kind]!, current.parent_id) : null
        if (seq !== sequence) return
        record.value = current; data.value = cleanWorkflowData(JSON.parse(JSON.stringify(current.data))); parent.value = linked
      } else {
        const parentId = params.get('parent'), expected = ({ materials: 'ideas', drafts: 'materials', publications: 'drafts' } as Record<string, WorkflowKind>)[kind]
        const linked = expected && parentId ? await getWorkflow(expected, parentId) : null
        const initial = factory(); await initialize(linked, initial)
        if (seq !== sequence) return
        record.value = null; parent.value = linked; data.value = initial; createId.value = randomId()
      }
      baseline.value = JSON.stringify(data.value)
    } catch (cause) { if (seq === sequence) { error.value = workflowError(cause); editing.value = false } }
    finally { if (seq === sequence) loading.value = false }
  }
  function open(id?: string) { navigateAdmin(workflowTabs[kind], id ? { id } : { new: '1' }) }
  function back() { navigateAdmin(workflowTabs[kind], {}) }
  function navigateSaved(id: string, replace = false) {
    savedNavigation = true
    try { navigateAdmin(workflowTabs[kind], { id }, replace) }
    finally { savedNavigation = false }
  }
  async function save() {
    if (!canAdmin(workflowTabs[kind], record.value ? 'update' : 'create')) { error.value = '没有保存权限'; return false }
    if (busy.value || loading.value || backup.recovery.value || !editing.value || adminRoute.tab !== workflowTabs[kind]) return false
    if ((kind === 'materials' || kind === 'drafts') && !parent.value && !record.value) {
      error.value = kind === 'materials' ? '请先选择关联选题' : '请先选择关联资料'; return false
    }
    const sourceRoute = adminRoute.query, session = editorSession.value
    const current = () => session === editorSession.value && adminRoute.tab === workflowTabs[kind] && adminRoute.query === sourceRoute
    function accept(saved: WorkflowRecord<T>, attempt: SaveAttempt, recovered = false) {
      if (!current()) return false
      const unchanged = workflowFingerprint(data.value) === workflowFingerprint(attempt.payload)
      backup.clear(); pendingSave.value = null
      record.value = saved; baseline.value = JSON.stringify(cleanWorkflowData(saved.data))
      if (unchanged) data.value = cleanWorkflowData(JSON.parse(JSON.stringify(saved.data)))
      creating.value = false; error.value = ''
      notice.value = dirty.value ? '原提交已保存，之后的编辑已保留，请再次保存。' : recovered ? '已查询确认原提交保存成功。' : '已保存'
      editorScope.value = saved.id
      routeKey = new URLSearchParams({ id: saved.id }).toString(); navigateSaved(saved.id, true)
      if (dirty.value) backup.persist()
      return !dirty.value
    }
    async function recover(attempt: SaveAttempt) {
      try {
        const saved = await getWorkflow<T>(kind, attempt.id)
        if (!current()) return { resolved: true, complete: false }
        if (saved.id !== attempt.id) throw new Error('原保存结果无法核对，请稍后重试。')
        const matches = workflowFingerprint(cleanWorkflowData(saved.data)) === workflowFingerprint(attempt.payload)
        if ((!attempt.revision && saved.revision === 1) || (saved.revision >= attempt.revision && matches)) {
          return { resolved: true, complete: accept(saved, attempt, true) }
        }
        if (saved.revision !== attempt.revision) throw new ApiError('内容已在其他页面更新，当前输入已保留，请核对最新版本。', 409)
        return { resolved: false, complete: false }
      } catch (cause) {
        if (!attempt.revision && cause instanceof ApiError && cause.status === 404) return { resolved: false, complete: false }
        throw cause
      }
    }
    busy.value = true; error.value = ''; notice.value = ''
    try {
      if (pendingSave.value) {
        const outcome = await recover(pendingSave.value)
        if (outcome.resolved) return outcome.complete
      }
      const attempt = pendingSave.value || { id: record.value?.id || createId.value, revision: record.value?.revision || 0,
        parentId: parent.value?.id || null, payload: cleanWorkflowData(data.value) }
      pendingSave.value = attempt; backup.persist()
      try {
        const saved = attempt.revision ? await updateWorkflow(kind, { ...record.value!, id: attempt.id, revision: attempt.revision }, attempt.payload) :
          await createWorkflow(kind, attempt.id, attempt.parentId, attempt.payload)
        return accept(saved, attempt)
      } catch (cause) {
        // 明确的校验失败可以修改后重新提交；超时与冲突先查询原记录。
        if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500 && cause.status !== 409 && cause.status !== 408) {
          pendingSave.value = null; throw cause
        }
        const outcome = await recover(attempt)
        if (outcome.resolved) return outcome.complete
        if (cause instanceof ApiError && cause.status === 409) pendingSave.value = null
        throw cause
      }
    } catch (cause) { if (current()) { error.value = workflowError(cause); backup.persist() }; return false }
    finally { busy.value = false }
  }
  async function duplicate() {
    if (!record.value || busy.value || !canAdmin(workflowTabs[kind], 'create')) return
    const sourceRoute = adminRoute.query
    busy.value = true; error.value = ''
    try {
      const copy = { ...JSON.parse(JSON.stringify(data.value)), title: (data.value.title + ' · 副本').slice(0, 120), status: kind === 'ideas' ? 'inbox' : kind === 'publications' ? 'planned' : 'draft' }
      if (kind === 'publications') Object.assign(copy, { scheduled_at: null, published_at: null, url: '', conclusion: '', next_action: '', rights_checked: false, truth_checked: false, privacy_checked: false, media_checked: false, platform_checked: false, review_notes: '' })
      const saved = await createWorkflow(kind, randomId(), record.value.parent_id, copy)
      if (adminRoute.tab !== workflowTabs[kind] || adminRoute.query !== sourceRoute) return
      baseline.value = JSON.stringify(data.value); navigateSaved(saved.id)
    } catch (cause) { error.value = workflowError(cause) } finally { busy.value = false }
  }
  watch(() => [adminRoute.tab, adminRoute.query], () => { void readRoute() })
  onActivated(() => { if (adminRoute.tab === workflowTabs[kind] && !dirty.value && !loading.value) void readRoute(true) })
  const invalidate = () => { ++sequence; loading.value = false }
  onDeactivated(invalidate)
  onBeforeUnmount(invalidate)
  watch([filter, page], ([status], [previousStatus]) => {
    if (status !== previousStatus && page.value !== 1) { page.value = 1; return }
    void fetchList()
  })
  function resetFilters() {
    q.value = ''; appliedQuery = ''
    if (filter.value || page.value !== 1) { filter.value = ''; page.value = 1 }
    else void fetchList()
  }
  return { items, total, page, q, filter, record, data, parent, creating, editing, busy, loading, error, notice, dirty, backup, editorSession, resetFilters, loadList, readRoute, open, back, save, duplicate }
}

export interface MetricData { checkpoint: 1 | 3 | 7; revision: number; measured_at: string; views: number; likes: number; saves: number; comments: number; follows: number | null; downloads: number | null; notes: string }
export interface AnalyticsRecord extends WorkflowRecord<PublicationData> { metric: MetricData | null; due_at: string; needs_recording: boolean; save_rate: number | null; interaction_rate: number | null }
export const getMetrics = (id: string) => request<{ items: MetricData[] }>(`${base}/metrics/${id}`)
export const putMetric = (id: string, data: MetricData) => request<{ items: MetricData[] }>(`${base}/metrics/${id}`, mutation('PUT', data))
export interface ReviewSave { revision: number; metric: MetricData; conclusion: string; next_action: string }
export const saveReview = (id: string, data: ReviewSave) => request<{ record: WorkflowRecord<PublicationData>; items: MetricData[] }>(`${base}/reviews/${id}`, mutation('PUT', data))
export type AnalyticsSort = 'published_at' | 'save_rate' | 'interaction_rate' | 'views'
export interface AnalyticsFilters { account?: string; start?: string; end?: string; sort?: AnalyticsSort }
export const getAnalytics = (checkpoint: number, q: string, page: number, filters: AnalyticsFilters = {}) => request<{ items: AnalyticsRecord[]; total: number; accounts?: {id: string; name: string}[] }>(`${base}/analytics?${new URLSearchParams({ checkpoint: String(checkpoint), q, page: String(page), ...filters })}`)

export function dateTimeLocal(value: string | null) { if (!value) return ''; const d = new Date(value); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16) }
export const isoDateTime = (value: string) => value ? new Date(value).toISOString() : null
