import { ApiError, apiUrl, authGeneration, authHeaders, handleAuthFailure } from './api'
import { createFilePool, type FileHandle, type RegisterDownloadCancel } from './file-pool'
import type { Asset } from '../types'

let pdfHandle: FileHandle | null = null
let pendingPdf: FileHandle | null = null

function release(path: string) {
  if (!path) return
  // #ifdef H5
  if (path.startsWith('blob:')) URL.revokeObjectURL(path)
  // #endif
  // #ifdef MP-WEIXIN
  uni.getFileSystemManager().unlink({ filePath: path, fail() {} })
  // #endif
}

export function clearAssetCache() {
  files.clear()
  pdfHandle = null
  pendingPdf = null
}

export function cancelPdfDownload() {
  const handle = pendingPdf
  if (!handle) return
  pendingPdf = null
  if (pdfHandle === handle) pdfHandle = null
  handle.release()
}

// 微信把 wx.request / wx.downloadFile / wx.uploadFile 挤在同一个并发池里（约 10 个）。
// 列表缩略图必须带鉴权头，只能走 downloadFile 一张张下；弱网时这些下载会占着连接槽直到
// 60 秒超时，把随后 fetchCatalog 之类的接口请求全部堵在队列里，页面就像“卡住一分钟”。
// 这里给资源下载单独限流：最多同时占 4 个槽，永远给接口请求留出余量。
const MAX_CONCURRENT_DOWNLOADS = 4
let activeDownloads = 0
const downloadWaiters: (() => void)[] = []
function freeSlot() {
  const next = downloadWaiters.shift()
  // 直接把腾出的槽交给下一个等待者，避免计数抖动。
  if (next) next(); else activeDownloads = Math.max(0, activeDownloads - 1)
}

function downloadAsset(path: string, progress: (percent: number) => void, registerCancel: RegisterDownloadCancel): Promise<string> {
  const pdf = path.startsWith('pdf:')
  const byteSize = pdf ? Number(path.split(':', 2)[1]) || 0 : 0
  if (pdf) path = path.slice(path.indexOf(':', 4) + 1)
  const epoch = authGeneration()
  let cancelled = false
  let task: UniApp.DownloadTask | undefined
  // 排队期间也要能取消：此时 task 还没创建，先置标记，轮到自己时立即放弃并让出槽。
  registerCancel(() => { cancelled = true; task?.abort() })
  return new Promise<string>((resolve, reject) => {
    // 有空槽就同步开下（保持“下一微任务即发起请求”的时序），否则排队等让出。
    const start = () => {
      if (cancelled) { reject(new ApiError('下载已取消')); freeSlot(); return }
      let url: string
      try { url = apiUrl(path) } catch (error) { reject(error); freeSlot(); return }
      const settle = (run: () => void) => { run(); freeSlot() }
      task = uni.downloadFile({
        // 缩略图/预览图没必要等满 60 秒；PDF 文件大，仍给足时间。
        url, header: authHeaders(), timeout: pdf ? pdfTimeout(byteSize) : 20000,
        success(result) {
          if (epoch !== authGeneration()) { release(result.tempFilePath); settle(() => reject(new ApiError('登录状态已变化'))); return }
          if (result.statusCode !== 200) {
            release(result.tempFilePath)
            handleAuthFailure(result.statusCode, result.statusCode === 409 ? 'account_changed' : '')
            settle(() => reject(new ApiError('文件暂不可用，请重试', result.statusCode)))
            return
          }
          settle(() => resolve(result.tempFilePath))
        },
        fail() { settle(() => reject(new ApiError('文件下载失败，请检查网络'))) },
      })
      task.onProgressUpdate?.(event => progress(event.progress))
    }
    if (activeDownloads < MAX_CONCURRENT_DOWNLOADS) { activeDownloads++; start() }
    else downloadWaiters.push(start)
  })
}

const files = createFilePool(downloadAsset, release)
uni.$on?.('lc-memory-warning', () => files.trim())
export function acquireAsset(path: string) { return files.acquire(path) }

export function pdfTimeout(bytes: number) {
  // 按 64 KiB/s 预留传输时间和握手余量，最大允许 10 分钟。
  return Math.max(60_000, Math.min(600_000, 20_000 + Math.ceil((Number(bytes) || 0) / 65536) * 1000))
}

export async function openPdf(asset: Asset, title: string, progress?: (percent: number) => void) {
  const handle = files.acquire('pdf:' + (asset.byte_size || 0) + ':' + asset.url, progress)
  uni.getNetworkType?.({ success: result => {
    if (['2g', '3g', '4g', '5g'].includes(result.networkType) && asset.byte_size > 5 * 1024 * 1024) {
      uni.showToast({ title: '正在使用移动网络下载 ' + (asset.byte_size / 1048576).toFixed(1) + ' MB', icon: 'none', duration: 3000 })
    }
  } })
  pdfHandle?.release()
  pdfHandle = handle
  pendingPdf = handle
  try {
    const path = await handle.ready
    if (pendingPdf !== handle) throw new ApiError('下载已取消')
    pendingPdf = null
    // #ifdef MP-WEIXIN
    await new Promise<void>((resolve, reject) => uni.openDocument({
      filePath: path, fileType: 'pdf', showMenu: true,
      success() { resolve() }, fail() { reject(new ApiError('无法打开 PDF，请重试')) },
    }))
    // #endif
    // #ifdef H5
    const link = document.createElement('a')
    link.href = path
    link.download = title.replace(/[\\/:*?"<>|]/g, '_') + '.pdf'
    link.hidden = true
    document.body.appendChild(link)
    link.click()
    link.remove()
    // #endif
  } catch (error) {
    if (pdfHandle === handle) handle.invalidate()
    handle.release()
    if (pdfHandle === handle) pdfHandle = null
    throw error
  } finally {
    if (pendingPdf === handle) pendingPdf = null
  }
}
