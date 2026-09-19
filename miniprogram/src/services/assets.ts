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

function downloadAsset(path: string, progress: (percent: number) => void, registerCancel: RegisterDownloadCancel): Promise<string> {
  const epoch = authGeneration()
  return new Promise<string>((resolve, reject) => {
    let url: string
    try { url = apiUrl(path) } catch (error) { reject(error); return }
    const task = uni.downloadFile({
      url, header: authHeaders(), timeout: 60000,
      success(result) {
        if (epoch !== authGeneration()) { release(result.tempFilePath); reject(new ApiError('登录状态已变化')); return }
        if (result.statusCode !== 200) {
          release(result.tempFilePath)
          handleAuthFailure(result.statusCode, result.statusCode === 409 ? 'account_changed' : '')
          reject(new ApiError('文件暂不可用，请重试', result.statusCode))
          return
        }
        resolve(result.tempFilePath)
      },
      fail() { reject(new ApiError('文件下载失败，请检查网络')) },
    })
    registerCancel(() => task.abort())
    task.onProgressUpdate?.(event => progress(event.progress))
  })
}

const files = createFilePool(downloadAsset, release)
export function acquireAsset(path: string) { return files.acquire(path) }

export async function openPdf(asset: Asset, title: string, progress?: (percent: number) => void) {
  const handle = files.acquire(asset.url, progress)
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
