import { openDB } from 'idb'
import { computed, reactive, shallowRef } from 'vue'
import { ApiError } from './api'
import { randomId } from '../../shared/webcrypto'
import { fetchImageStatus, generateWorksheetImage, imageBlob, imageWorksheetTitle, loadImageBlob, type ImageWorksheetParams, type WorksheetImage } from './image-generation'

export const MAX_WORKSHEET_IMAGES = 10
type PageState = 'queued' | 'running' | 'unknown' | 'failed' | 'ready' | 'expired'
export interface GeneratedPage { id: string; state: PageState; error: string; image: WorksheetImage | null; url: string }
const validId = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(value)
const imageCache = async () => openDB('lc-worksheet-images', 1, { upgrade(db) { db.createObjectStore('images') } })
const states: PageState[] = ['queued', 'running', 'unknown', 'failed', 'ready', 'expired']
const MAX_RECOVERY_QUERIES = 120

/** Each page keeps its own paid request ID. Reloads only query; resuming needs a click. */
export function useImageBatch(storageKey: string, current: () => boolean, onImage: (index: number) => void) {
  const state = reactive({ pages: [] as GeneratedPage[], busy: false, checking: false, error: '', paused: false })
  const history = reactive<{ id: string; title: string; savedAt: number; snapshot: string }[]>([])
  const storageError = shallowRef('')
  const historyKey = storageKey + '_history'
  const input = shallowRef<ImageWorksheetParams | null>(null)
  const reads = new AbortController()
  let recoveryTimer: ReturnType<typeof setTimeout> | undefined
  let recoveryQueries = 0
  let disposed = false
  const active = () => !disposed && current()
  const unresolved = computed(() => state.pages.some(page => page.state === 'running' || page.state === 'unknown'))
  const completed = computed(() => state.pages.filter(page => !!page.image).length)
  const remaining = computed(() => state.pages.filter(page => page.state !== 'ready').length)
  const canContinue = computed(() => !!input.value && remaining.value > 0 && !unresolved.value && !state.busy && !state.checking)
  const visibleOnline = () => document.visibilityState !== 'hidden' && navigator.onLine !== false
  function cancelRecovery() {
    clearTimeout(recoveryTimer); recoveryTimer = undefined
  }
  function scheduleRecovery() {
    cancelRecovery()
    if (!active() || !unresolved.value || state.busy || state.checking || !visibleOnline() || recoveryQueries >= MAX_RECOVERY_QUERIES) return
    // 只查询原 ID；逐步降到每 30 秒一次，后台页和离线时暂停。
    const delay = Math.min(5_000 * 2 ** Math.min(recoveryQueries, 3), 30_000)
    recoveryTimer = setTimeout(() => {
      recoveryTimer = undefined
      if (!active() || !visibleOnline()) return
      recoveryQueries++
      void recover()
    }, delay)
  }
  function resumeRecovery() {
    if (active() && visibleOnline() && unresolved.value && !state.busy && !state.checking) {
      recoveryQueries = 0
      void recover()
    }
  }
  document.addEventListener('visibilitychange', resumeRecovery)
  window.addEventListener('online', resumeRecovery)
  function persist(): boolean {
    try {
      localStorage.setItem(storageKey, JSON.stringify({ version: 1, input: input.value, pages: state.pages.map(({ id, state }) => ({ id, state })) }))
      if (storageError.value.startsWith('请求记录保存失败')) storageError.value = ''
      return true
    } catch {
      storageError.value = '请求记录保存失败，暂未发送新的生图请求；请恢复浏览器存储后重试，已有图片请及时下载。'
      return false
    }
  }
  async function show(page: GeneratedPage, image: WorksheetImage, index: number, cached = false) {
    if (!active()) return
    const blob = await loadImageBlob(image, reads.signal)
    if (!active()) return
    // IndexedDB stores structured Blob values; never duplicate base64 in state.
    const { b64_json: _legacy, ...metadata } = image
    const stored = { ...metadata, blob }
    const url = URL.createObjectURL(blob)
    if (page.url) URL.revokeObjectURL(page.url)
    page.image = stored; page.url = url; page.state = 'ready'; page.error = ''
    if (!cached) await imageCache().then(async db => {
      try {
        const owner = storageKey.match(/^lc_u([^_]+)_/)?.[1]
        if (active() && (!owner || !localStorage.getItem('lc_purge:' + owner))) await db.put('images', stored, storageKey + ':' + page.id)
      } finally { db.close() }
    }).catch(() => { if (active()) storageError.value = '图片未能保存到本机，请及时下载。' })
    if (active()) onImage(index)
  }
  function release() { state.pages.forEach(page => { if (page.url) URL.revokeObjectURL(page.url) }) }
  async function run() {
    if (!active() || !canContinue.value || !input.value) return
    cancelRecovery(); recoveryQueries = 0
    state.busy = true; state.paused = false; state.error = ''
    try {
      for (const [index, page] of state.pages.entries()) {
        if (!active() || state.paused) break
        if (page.state === 'ready') continue
        // Retrying a completed failure is explicit; successful pages are never regenerated.
        if (page.state !== 'queued') page.id = randomId()
        page.state = 'running'; page.error = ''
        if (!persist()) {
          // 尚未发送，恢复为可重试状态并保留这次 ID。
          page.state = 'queued'; page.error = storageError.value; state.error = page.error
          break
        }
        let generated = false
        try {
          const image = await generateWorksheetImage({ ...input.value, image_count: state.pages.length, image_index: index + 1 }, page.id)
          generated = true
          if (!active()) break
          await show(page, image, index)
        } catch (cause) {
          if (!active()) break
          // 只有明确的 4xx 拒绝可以判定为失败，其余异常均先查询，避免重复计费。
          const rejected = cause instanceof ApiError && cause.status >= 400 && cause.status < 500 && cause.code !== 'generation_pending'
          page.state = generated || !rejected ? 'unknown' : 'failed'
          page.error = cause instanceof Error ? cause.message : '生成失败'
          state.error = `第 ${index + 1} 张：${page.error}`
          break
        } finally { if (active()) persist() }
      }
    } finally { state.busy = false; scheduleRecovery() }
  }
  async function start(params: ImageWorksheetParams, count: number) {
    if (!active() || state.busy || state.checking || unresolved.value) return
    if (!Number.isInteger(count) || count < 1 || count > MAX_WORKSHEET_IMAGES) throw new Error('请选择 1 至 10 张图片')
    const snapshot = JSON.parse(JSON.stringify(params)) as ImageWorksheetParams
    archiveCurrent()
    release(); input.value = snapshot
    state.pages = Array.from({ length: count }, () => ({ id: randomId(), state: 'queued', error: '', image: null, url: '' }))
    await run()
  }
  async function recover() {
    if (!active() || state.busy || state.checking) return
    cancelRecovery()
    state.checking = true; state.error = ''
    try {
      for (const [index, page] of state.pages.entries()) {
        if (!active()) break
        if (page.image || page.state === 'queued' || page.state === 'expired') continue
        try {
          let cached: WorksheetImage | undefined
          try {
            const db = await imageCache()
            try {
              cached = await db.get('images', storageKey + ':' + page.id)
              if (cached) {
                try {
                  if (cached.request_id !== page.id) throw new Error('缓存请求不匹配')
                  imageBlob(cached)
                } catch {
                  cached = undefined
                  await db.delete('images', storageKey + ':' + page.id)
                }
              }
            } finally { db.close() }
          } catch { /* Server recovery remains available. */ }
          if (!active()) break
          if (cached) { await show(page, cached, index, true); if (active()) persist(); continue }
          const value = await fetchImageStatus(page.id, reads.signal)
          if (!active()) break
          if (value.kind !== 'image') throw new Error('该请求不是图片生成任务')
          if (value.status === 'succeeded' && value.result) await show(page, value.result, index)
          else {
            page.state = value.status === 'running' ? 'running' : value.cache_expired ? 'expired' : 'failed'
            page.error = page.state === 'running' ? '' : value.cache_expired ? '图片缓存已过期' : value.error?.error || '本次未取得图片'
            if (value.status === 'unknown') page.error += '；再次生成可能产生新的费用'
          }
        } catch (cause) {
          if (!active()) break
          page.state = cause instanceof ApiError && cause.status === 404 ? 'failed' : 'unknown'
          page.error = cause instanceof Error ? cause.message : '查询失败'
        }
        if (active()) persist()
      }
    } finally { state.checking = false; scheduleRecovery() }
  }
  function archiveCurrent() {
    if (!state.pages.length || !input.value) return
    const id = state.pages.map(page => page.id).join(',')
    const snapshot = JSON.stringify({ version: 1, input: input.value, pages: state.pages.map(({ id, state }) => ({ id, state })) })
    const existing = history.findIndex(item => item.id === id)
    if (existing >= 0) history.splice(existing, 1)
    history.unshift({ id, title: input.value.keyword || imageWorksheetTitle(input.value), savedAt: Date.now(), snapshot })
    const removed = history.splice(10)
    const retained = new Set([...state.pages.map(page => page.id), ...history.flatMap(item => JSON.parse(item.snapshot).pages.map((page: { id: string }) => page.id))])
    void imageCache().then(async db => {
      for (const entry of removed) for (const page of JSON.parse(entry.snapshot).pages) if (!retained.has(page.id)) await db.delete('images', storageKey + ':' + page.id)
      db.close()
    }).catch(() => {})
    try { localStorage.setItem(historyKey, JSON.stringify(history)) } catch { storageError.value = '历史记录未能保存到本机，请及时下载。' }
  }
  async function selectHistory(id: string) {
    if (!active() || state.busy || state.checking || unresolved.value) return
    const entry = history.find(item => item.id === id)
    if (!entry) return
    history.splice(history.indexOf(entry), 1)
    archiveCurrent()
    try { localStorage.setItem(storageKey, entry.snapshot) } catch { storageError.value = '无法打开本机历史记录'; return }
    release(); state.pages = []; state.error = ''; state.paused = false
    await restore()
  }
  async function restore() {
    try {
      let savedHistory: unknown
      try { savedHistory = JSON.parse(localStorage.getItem(historyKey) || '[]') } catch { savedHistory = [] }
      if (Array.isArray(savedHistory)) {
        history.splice(0, history.length, ...savedHistory.filter(item => {
          try { const data = JSON.parse(item.snapshot); return typeof item.id === 'string' && typeof item.title === 'string' && Number.isFinite(item.savedAt) && data.version === 1 && Array.isArray(data.pages) && data.pages.length <= 10 && data.pages.every((page: { id: unknown }) => validId(page.id)) } catch { return false }
        }).slice(0, 10))
      }
      const raw = localStorage.getItem(storageKey)
      if (!raw || !active()) return
      if (validId(raw)) { // Previous single-image requests remain recoverable.
        state.pages = [{ id: raw, state: 'unknown', error: '', image: null, url: '' }]
      } else {
        const saved = JSON.parse(raw)
        if (saved.version !== 1 || !Array.isArray(saved.pages) || !saved.pages.length || saved.pages.length > MAX_WORKSHEET_IMAGES
          || saved.pages.some((page: { id: string; state: PageState }) => !page || !validId(page.id) || !states.includes(page.state))
          || new Set(saved.pages.map((page: { id: string }) => page.id)).size !== saved.pages.length) return
        input.value = saved.input && typeof saved.input.grade === 'string' && typeof saved.input.subject === 'string'
          && typeof saved.input.keyword === 'string' && Array.isArray(saved.input.items) ? saved.input : null
        state.pages = saved.pages.map((page: { id: string; state: PageState }) => ({ id: page.id, state: page.state, error: '', image: null, url: '' }))
      }
      await recover()
    } catch { /* Ignore malformed local state; never turn it into a generation request. */ }
  }
  return reactive({ state, history, storageError, selectHistory, completed, remaining, unresolved, canContinue, start, run, recover, restore,
    parameters: () => input.value ? JSON.parse(JSON.stringify(input.value)) as ImageWorksheetParams : null,
    pause: () => { state.paused = true }, dispose: () => {
      disposed = true; cancelRecovery(); reads.abort()
      document.removeEventListener('visibilitychange', resumeRecovery)
      window.removeEventListener('online', resumeRecovery)
      release()
    } })
}
