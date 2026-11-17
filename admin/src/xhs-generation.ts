import { computed, ref, watch } from 'vue'
import { ApiError, request } from './api'
import { randomId } from '../../shared/webcrypto'
import { workflowError } from './xhs-workflow'

interface Pending { id: string; path: string; body: unknown; context?: { revision: number; fingerprint: string } }
export function generationGrade(grade: string, subject: string, available: Record<string, string[]>) {
  return Object.keys(available).find(value => value.replace(/^小学/, '') === grade.replace(/^小学/, '') && available[value]?.includes(subject))
}
/** 先保存请求编号，刷新后查原结果；不会因网络异常自动启动新的付费请求。 */
export function useXhsGeneration<T>(adminId: number, recordId: () => string, kind: string) {
  const busy = ref(false), error = ref(''), pending = ref<Pending | null>(null), result = ref<T | null>(null)
  const storageKey = computed(() => `lc-xhs-generation:${adminId}:${kind}:${recordId()}`)
  const finished = new Set<string>()
  function read() {
    error.value = ''; result.value = null
    try { pending.value = finished.has(storageKey.value) ? null : JSON.parse(localStorage.getItem(storageKey.value) || 'null') }
    catch { pending.value = null }
  }
  watch(storageKey, read, { immediate: true })
  async function send(value: Pending) {
    const options = await request<{ timeout_ms: number; revision: string }>('/api/v1/generation/options?kind=text')
    return request<T>(value.path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Request-ID': value.id, 'X-Model-Config-Revision': options.revision }, body: JSON.stringify(value.body) }, 'json', options.timeout_ms)
  }
  async function generate(path: string, body: unknown, revision?: number, editor?: unknown) {
    if (busy.value || pending.value) return null
    const sourceKey = storageKey.value
    busy.value = true; error.value = ''; result.value = null
    try {
      const value: Pending = { id: randomId(), path, body: JSON.parse(JSON.stringify(body)),
        ...(revision === undefined ? {} : { context: { revision, fingerprint: JSON.stringify(editor) } }) }
      localStorage.setItem(storageKey.value, JSON.stringify(value)); finished.delete(storageKey.value); pending.value = value
      const output = await send(value)
      if (sourceKey !== storageKey.value) return null
      result.value = output; return output
    } catch (cause) { if (sourceKey === storageKey.value) error.value = workflowError(cause); return null }
    finally { busy.value = false }
  }
  async function recover() {
    if (!pending.value || busy.value) return null
    const sourceKey = storageKey.value
    busy.value = true; error.value = ''
    try {
      const status = await request<{ status: string; result: T | null; error?: { error?: string }; cache_expired: boolean }>(`/api/v1/me/generations/${pending.value.id}`)
      if (sourceKey !== storageKey.value) return null
      if (status.status === 'succeeded' && status.result) { result.value = status.result; return status.result }
      error.value = status.status === 'running' ? '生成仍在进行中，稍后再查询。' : status.cache_expired ? '原结果已过保存期，可以结束此请求后重新生成。' : status.error?.error || '原请求未完成，可结束此请求后重新生成。'
      return null
    } catch (cause) {
      if (sourceKey !== storageKey.value) return null
      if (cause instanceof ApiError && cause.status === 404) error.value = '服务端没有此请求记录，可结束此请求后重新生成。'
      else error.value = workflowError(cause)
      return null
    } finally { busy.value = false }
  }
  function finish() {
    finished.add(storageKey.value)
    pending.value = null; result.value = null; error.value = ''
    try { localStorage.removeItem(storageKey.value) }
    catch { error.value = '请求已在本页结束，但本机记录未能清除；刷新后请先查询旧请求，再决定是否重新生成。' }
  }
  function abandon() { if (!busy.value && window.confirm('结束本地跟踪不会取消服务端生成。再次生成会发起新的模型请求，是否继续？')) finish() }
  // 历史请求没有版本快照时也要求核对，不能把“当前没有未保存修改”等同于输入未变化。
  function matches(revision: number, editor: unknown) {
    return pending.value?.context?.revision === revision && pending.value.context.fingerprint === JSON.stringify(editor)
  }
  return { busy, error, pending, result, generate, recover, finish, abandon, matches }
}
