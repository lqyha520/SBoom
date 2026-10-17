import { ApiError, apiUrl, authGeneration, authHeaders, handleAuthFailure } from './api'
import { createFilePool, type DownloadedFile, type FileHandle, type RegisterDownloadCancel } from './file-pool'
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
  pdfFiles.clear()
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
let backgroundDownloads = 0
interface DownloadWaiter { priority: () => number; start: () => void }
const downloadWaiters: DownloadWaiter[] = []
function pumpDownloads() {
  while (activeDownloads < MAX_CONCURRENT_DOWNLOADS) {
    // 普通图片最多占 3 个槽，为当前阅读页 / 主动下载留一个槽。
    let best = -1
    for (let index = 0; index < downloadWaiters.length; index++) {
      const priority = downloadWaiters[index]!.priority()
      if (backgroundDownloads >= MAX_CONCURRENT_DOWNLOADS - 1 && priority < 2) continue
      if (best < 0 || priority > downloadWaiters[best]!.priority()) best = index
    }
    if (best < 0) return
    const next = downloadWaiters.splice(best, 1)[0]!
    activeDownloads++
    next.start()
  }
}

function downloadAsset(path: string, progress: (percent: number) => void, registerCancel: RegisterDownloadCancel, priority: () => number): Promise<DownloadedFile> {
  const pdf = path.startsWith('pdf:')
  const byteSize = pdf ? Number(path.split(':', 2)[1]) || 0 : 0
  if (pdf) path = path.slice(path.indexOf(':', 4) + 1)
  const epoch = authGeneration(), queuedAt = Date.now()
  return new Promise((resolve, reject) => {
    let task: UniApp.DownloadTask | undefined
    let settled = false, started = false, background = false, bytes = byteSize
    let startedAt = queuedAt
    const finish = (run: () => void) => {
      if (settled) return
      settled = true
      const index = downloadWaiters.indexOf(waiter)
      if (index >= 0) downloadWaiters.splice(index, 1)
      if (started) activeDownloads = Math.max(0, activeDownloads - 1)
      if (background) backgroundDownloads = Math.max(0, backgroundDownloads - 1)
      run()
      pumpDownloads()
    }
    const waiter: DownloadWaiter = { priority, start: () => {
      started = true
      background = priority() < 2
      if (background) backgroundDownloads++
      startedAt = Date.now()
      uni.$emit?.('lc-performance', { kind: 'asset_wait', value: startedAt - queuedAt })
      try {
        task = uni.downloadFile({
          url: apiUrl(path), header: authHeaders(), timeout: pdf ? pdfTimeout(byteSize) : 20000,
          success(result) {
            if (settled) { release(result.tempFilePath); return }
            if (epoch !== authGeneration()) { release(result.tempFilePath); finish(() => reject(new ApiError('登录状态已变化'))); return }
            if (result.statusCode !== 200) {
              release(result.tempFilePath)
              handleAuthFailure(result.statusCode, result.statusCode === 409 ? 'account_changed' : '')
              finish(() => reject(new ApiError('文件暂不可用，请重试', result.statusCode)))
              return
            }
            uni.$emit?.('lc-performance', { kind: 'asset_download', value: Date.now() - startedAt })
            if (bytes > 0) uni.$emit?.('lc-performance', { kind: 'asset_bytes', value: bytes })
            finish(() => resolve({ path: result.tempFilePath, bytes }))
          },
          fail() { finish(() => reject(new ApiError('文件下载失败，请检查网络'))) },
        })
        task.onProgressUpdate?.(event => {
          bytes = Math.max(bytes, event.totalBytesWritten || 0, event.totalBytesExpectedToWrite || 0)
          progress(event.progress)
        })
      } catch (error) { finish(() => reject(error)) }
    } }
    downloadWaiters.push(waiter)
    registerCancel(() => {
      finish(() => reject(new ApiError('下载已取消')))
      task?.abort()
    })
    pumpDownloads()
  })
}

const files = createFilePool(downloadAsset, release, { maxIdleBytes: 12 * 1024 * 1024 })
const pdfFiles = createFilePool(downloadAsset, release, { maxIdle: 1, graceMs: 10_000, maxIdleBytes: 32 * 1024 * 1024 })
uni.$on?.('lc-memory-warning', () => { files.trim(); pdfFiles.trim() })
export function acquireAsset(path: string, priority = 1) {
  const handle = files.acquire(path, undefined, priority)
  // 同一 URL 从预取变成当前页时提升优先级，复用在途下载。
  pumpDownloads()
  return { ...handle, prioritize(value: number) { handle.prioritize?.(value); pumpDownloads() } }
}
export function assetCacheStats() { return { images: files.stats(), pdf: pdfFiles.stats(), activeDownloads, queued: downloadWaiters.length } }

export function pdfTimeout(bytes: number) {
  // 按 64 KiB/s 预留传输时间和握手余量，最大允许 10 分钟。
  return Math.max(60_000, Math.min(600_000, 20_000 + Math.ceil((Number(bytes) || 0) / 65536) * 1000))
}

export async function openPdf(asset: Asset, title: string, progress?: (percent: number) => void) {
  // #ifdef MP-WEIXIN
  const openedAt = Date.now()
  // #endif
  const handle = pdfFiles.acquire('pdf:' + (asset.byte_size || 0) + ':' + asset.url, progress, 3)
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
      success() {
        uni.$emit?.('lc-performance', { kind: 'pdf_open', value: Date.now() - openedAt })
        resolve()
      }, fail() { reject(new ApiError('无法打开 PDF，请重试')) },
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
