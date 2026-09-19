import { computed, reactive, ref } from 'vue'
import { AuthError } from './api'
import { defaultDownloadSettings, downloadPayload, downloadSettingsIssue, type DownloadSettings } from './download-settings'
import { attachImportedEdition, importPublication, type CatalogDetail, type CatalogImportMeta } from './catalog'
// crypto.randomUUID / crypto.subtle 都是 [SecureContext] 限定 API，http://内网IP 下不存在
import { randomId, sha256Hex } from '../../shared/webcrypto'

export type ImportFields = Pick<CatalogImportMeta, 'title' | 'grade' | 'subject' | 'category_id' | 'mode'> & DownloadSettings
export type ImportShared = Pick<CatalogImportMeta, 'description' | 'view_access' | 'download_access'>
export interface ImportRow {
  id: string; file: File; digest: string; fileError: string; meta: ImportFields
  state: 'checking' | 'queued' | 'uploading' | 'processing' | 'succeeded' | 'failed'
  progress: number; error: string; created?: CatalogDetail
  answer?: File; answerError: string; answerState: 'none' | 'queued' | 'uploading' | 'processing' | 'succeeded' | 'failed'
  answerProgress: number; answerFileError: string
}
const message = (cause: unknown) => cause instanceof Error ? cause.message : '导入失败，请重试'
export async function inspectPdf(file: File) {
  if (!/\.pdf$/i.test(file.name)) throw new Error('仅支持 PDF 文件')
  if (!file.size) throw new Error('文件为空，请重新选择')
  if (file.size > 32 * 1024 * 1024) throw new Error('文件超过 32 MB，请先压缩或拆分')
  const bytes = await file.arrayBuffer()
  if (new TextDecoder().decode(bytes.slice(0, 5)) !== '%PDF-') throw new Error('文件内容不是 PDF，请检查后重新选择')
  return sha256Hex(bytes)
}
export function importRowIssue(row: ImportRow) {
  return row.fileError || row.answerFileError || (!row.meta.title.trim() ? '请填写公开标题' : '')
    || (!row.meta.grade ? '请选择年级' : '') || (!row.meta.subject ? '请选择科目' : '')
    || (!row.meta.category_id ? '请选择分类' : '') || downloadSettingsIssue(row.meta)
}

export function useCatalogImportQueue(userId: number, created: (paper: CatalogDetail) => void) {
  const rows = ref<ImportRow[]>([]), running = ref(false), checking = ref(false), stopped = ref(false)
  const busy = computed(() => running.value || checking.value)
  const pending = computed(() => rows.value.filter(row => row.state === 'queued' && !importRowIssue(row)))
  const failed = computed(() => rows.value.filter(row => row.state === 'failed' && !importRowIssue(row)))
  const succeeded = computed(() => rows.value.filter(row => !!row.created).length)

  async function add(files: File[], defaults: Omit<ImportFields, 'title'>) {
    if (busy.value) return
    checking.value = true
    try {
      for (const file of files) {
        const row = reactive<ImportRow>({ id: randomId(), file, digest: '', fileError: '',
          meta: { ...defaultDownloadSettings(), ...defaults, title: file.name.replace(/\.pdf$/i, '').slice(0, 240) },
          state: 'checking', progress: 0, error: '', answerError: '', answerState: 'none', answerProgress: 0, answerFileError: '' })
        rows.value.push(row)
        try {
          row.digest = await inspectPdf(file)
          const duplicate = rows.value.find(item => item.id !== row.id && item.digest === row.digest && !item.fileError)
          if (duplicate) row.fileError = `与「${duplicate.file.name}」内容相同，请移除此重复文件`
        } catch (cause) { row.fileError = message(cause) }
        row.state = 'queued'
      }
    } finally { checking.value = false }
  }
  function remove(id: string) {
    if (busy.value) return
    rows.value = rows.value.filter(row => row.id !== id)
    const seen = new Map<string, string>()
    rows.value.forEach(row => {
      if (!row.digest) return
      row.fileError = seen.has(row.digest) ? `与「${seen.get(row.digest)}」内容相同，请移除此重复文件` : ''
      seen.set(row.digest, row.file.name)
    })
  }
  function apply(fields: Partial<Omit<ImportFields, 'title'>>) {
    if (busy.value) return
    rows.value.filter(row => !row.created).forEach(row => Object.assign(row.meta, fields))
  }
  async function setAnswer(id: string, file?: File) {
    if (busy.value) return
    const row = rows.value.find(item => item.id === id)
    if (!row || row.answerState === 'succeeded') return
    row.answer = file; row.answerError = ''; row.answerFileError = ''; row.answerState = file ? 'queued' : 'none'
    if (!file) return
    checking.value = true
    try { await inspectPdf(file) } catch (cause) { row.answerFileError = message(cause) }
    finally { checking.value = false }
  }
  async function attachAnswer(row: ImportRow) {
    if (!row.created || !row.answer || row.answerFileError || row.answerState === 'succeeded') return
    row.answerState = 'uploading'; row.answerProgress = 0; row.answerError = ''
    try {
      const result = await attachImportedEdition(userId, row.created.id, row.created.revision, 'answers', row.answer, percent => {
        row.answerProgress = percent; row.answerState = percent === 100 ? 'processing' : 'uploading'
      })
      row.created.revision = result.revision; row.answerState = 'succeeded'; created(row.created)
    } catch (cause) {
      row.answerState = 'failed'; row.answerError = message(cause)
      if (cause instanceof AuthError) stopped.value = true
    }
  }
  async function retryAnswer(id: string) {
    if (busy.value) return
    const row = rows.value.find(item => item.id === id)
    if (!row) return
    running.value = true
    try { await attachAnswer(row) } finally { running.value = false }
  }
  async function run(shared: ImportShared, retry = false, id?: string) {
    if (busy.value) return
    const jobs = (retry ? failed.value : pending.value).filter(row => !id || row.id === id)
    if (!jobs.length) return
    const metadata = { ...shared }
    running.value = true; stopped.value = false
    try {
      for (const row of jobs) {
        if (stopped.value) break
        row.state = 'uploading'; row.progress = 0; row.error = ''
        try {
          row.created = await importPublication(userId, row.file, { ...metadata, ...row.meta, ...downloadPayload(row.meta), title: row.meta.title.trim() }, percent => {
            row.progress = percent; row.state = percent === 100 ? 'processing' : 'uploading'
          })
          row.state = 'succeeded'; created(row.created)
          if (!stopped.value) await attachAnswer(row)
        } catch (cause) {
          row.state = 'failed'; row.error = message(cause)
          if (cause instanceof AuthError) stopped.value = true
        }
      }
    } finally { running.value = false }
  }
  function reset() { if (!busy.value) { rows.value = []; stopped.value = false } }
  return reactive({ rows, running, checking, busy, stopped, pending, failed, succeeded, add, remove, apply, setAnswer, retryAnswer, run, reset,
    stop: () => { stopped.value = true } })
}
export type CatalogImportQueue = ReturnType<typeof useCatalogImportQueue>
