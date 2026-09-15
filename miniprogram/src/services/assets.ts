import { ApiError, apiUrl, authGeneration, authHeaders, handleAuthFailure } from './api'
import { createFilePool, type FileHandle } from './file-pool'
import type { Asset } from '../types'

let pdfHandle: FileHandle | null = null

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
}

function downloadAsset(path: string): Promise<string> {
  const epoch = authGeneration()
  return new Promise<string>((resolve, reject) => {
    let url: string
    try { url = apiUrl(path) } catch (error) { reject(error); return }
    uni.downloadFile({
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
  })
}

const files = createFilePool(downloadAsset, release)
export function acquireAsset(path: string) { return files.acquire(path) }

export async function openPdf(asset: Asset, title: string) {
  const handle = acquireAsset(asset.url)
  pdfHandle?.release()
  pdfHandle = handle
  try {
    const path = await handle.ready
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
    handle.invalidate()
    handle.release()
    if (pdfHandle === handle) pdfHandle = null
    throw error
  }
}
