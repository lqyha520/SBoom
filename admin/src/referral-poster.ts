import { computed, ref, watch } from 'vue'
import { ApiError, request } from './api'
import { randomId } from '../../shared/webcrypto'

export type PosterStyle = 'editorial' | 'playful' | 'minimal'
export interface PosterDraft { title: string; caption: string; style: PosterStyle; direction: string; version: string }
export interface PosterAsset { asset_id: string; request_id: string; expires_at: number }
interface Job { id: string; draft: PosterDraft; result?: PosterAsset; ended?: boolean }
export const posterStyles: { value: PosterStyle; label: string; description: string }[] = [
  { value: 'editorial', label: '暖调杂志', description: '纸艺 · 奶油白 · 朱砂橙' },
  { value: 'playful', label: '童趣绘本', description: '黏土 · 浅草绿 · 柔和光影' },
  { value: 'minimal', label: '极简几何', description: '立体静物 · 冰蓝 · 留白' },
]

/** 每个账号、活动独立保存请求；查询原任务不会重新调用图片模型。 */
export function useReferralPoster(actor: () => number, campaign: () => string) {
  const key = computed(() => `lc-referral-poster:${actor()}:${campaign()}`)
  const job = ref<Job | null>(null), busy = ref(false), error = ref('')
  const pending = computed(() => !!job.value && !job.value.result && !job.value.ended)
  let epoch = 0
  watch(key, () => {
    epoch++; busy.value = false; error.value = ''; job.value = null
    if (!campaign()) return
    try {
      const saved = JSON.parse(localStorage.getItem(key.value) || 'null') as Job | null
      if (saved && typeof saved.id === 'string' && saved.draft && posterStyles.some(style => style.value === saved.draft.style)) job.value = saved
    } catch { error.value = '本机海报记录读取失败' }
  }, { immediate: true })
  function save(value: Job) { localStorage.setItem(key.value, JSON.stringify(value)); job.value = value }
  function updateDraft(draft: PosterDraft) {
    if (job.value && !pending.value) {
      try { save({ ...job.value, draft: { ...draft } }) } catch { error.value = '文案暂未保存到本机，请先下载海报' }
    }
  }
  async function generate(draft: PosterDraft) {
    if (busy.value || pending.value) return
    const current = epoch, campaignId = campaign()
    busy.value = true; error.value = ''
    try {
      const options = await request<{ timeout_ms: number; revision: string }>('/api/v1/generation/options?kind=image')
      if (current !== epoch) return
      const value: Job = { id: randomId(), draft: { ...draft } }
      save(value)
      const result = await request<PosterAsset>('/api/v1/admin/referrals/poster', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Request-ID': value.id, 'X-Model-Config-Revision': options.revision },
        body: JSON.stringify({ campaign_id: campaignId, title: draft.title, style: draft.style, direction: draft.direction }),
      }, 'json', options.timeout_ms)
      if (current !== epoch) return
      job.value = { ...value, result }; save(job.value)
    } catch (cause) {
      if (current !== epoch) return
      error.value = cause instanceof Error ? cause.message : '海报生成失败，请查询原请求'
    } finally { if (current === epoch) busy.value = false }
  }
  async function recover() {
    if (!job.value || busy.value) return
    const current = epoch, value = job.value
    busy.value = true; error.value = ''
    try {
      const status = await request<{ status: string; result: PosterAsset | null; cache_expired: boolean; error?: { error?: string } }>(`/api/v1/me/generations/${encodeURIComponent(value.id)}`)
      if (current !== epoch) return
      if (status.status === 'succeeded' && status.result) { job.value = { ...value, result: status.result }; save(job.value) }
      else if (status.status === 'failed' || status.cache_expired) {
        save({ ...value, ended: true }); error.value = status.cache_expired ? '原图已过保存期，请重新生成' : status.error?.error || '原请求失败，可以重新生成'
      } else error.value = status.status === 'running' ? '原图仍在生成中，稍后查询即可。' : '原请求结果尚不确定，正在尝试找回原图，请稍后再查询。'
    } catch (cause) {
      if (current !== epoch) return
      if (cause instanceof ApiError && cause.status === 404) { save({ ...value, ended: true }); error.value = '没有找到原请求，可以重新生成' }
      else error.value = cause instanceof Error ? cause.message : '查询失败，请重试'
    } finally { if (current === epoch) busy.value = false }
  }
  function abandon() {
    if (busy.value || !job.value || !window.confirm('原请求可能仍在生成。放弃跟踪后再次生成会发起新的模型请求，是否继续？')) return
    try { save({ ...job.value, ended: true }); error.value = '' }
    catch { error.value = '本机记录更新失败，请继续查询原请求' }
  }
  return { job, busy, error, pending, generate, recover, abandon, updateDraft }
}

export function posterArtwork(asset: PosterAsset) {
  if (!/^[a-f0-9]{32}$/.test(asset.asset_id)) throw new Error('原图标识无效，请查询原请求')
  return request<Blob>('/api/v1/image-generation/assets/' + asset.asset_id, undefined, 'blob')
}
