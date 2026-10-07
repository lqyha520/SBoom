import { afterEach, expect, it, vi } from 'vitest'
import { uploadPdf } from '../catalog'
import { AUTH_EXPIRED_EVENT, AuthError } from '../api'
class UploadMock {
  static current: UploadMock
  upload: { onprogress?: (event: any) => void; onload?: () => void } = {}
  timeout = 0; status = 201; responseText = '{"id":"created"}'
  onload!: () => void; onerror!: () => void; ontimeout!: () => void; onabort!: () => void
  getResponseHeader = vi.fn(() => '0'); abort = vi.fn(); open = vi.fn(); setRequestHeader = vi.fn(); send = vi.fn()
  constructor() { UploadMock.current = this }
}
afterEach(() => vi.unstubAllGlobals())
it('上传使用管理员身份边界并报告实际字节进度，上传后等待处理响应', async () => {
  vi.stubGlobal('XMLHttpRequest', UploadMock)
  const progress = vi.fn(), file = new File(['%PDF-'], 'sample.pdf')
  const result = uploadPdf('/api/v1/admin/catalog/import', 7, file, progress), xhr = UploadMock.current
  expect(xhr.setRequestHeader).toHaveBeenCalledWith('X-Workspace-User', '7')
  expect(xhr.send).toHaveBeenCalledWith(file)
  xhr.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 }); xhr.upload.onload?.()
  expect(progress.mock.calls).toEqual([[50], [100]])
  xhr.onload(); await expect(result).resolves.toEqual({ id: 'created' })
})
it('登录失效即使返回非 JSON 也触发退出处理', async () => {
  vi.stubGlobal('XMLHttpRequest', UploadMock)
  const expired = vi.fn(); window.addEventListener(AUTH_EXPIRED_EVENT, expired)
  try {
    const result = uploadPdf('/api/v1/admin/catalog/import', 7, new File([], 'sample.pdf'))
    UploadMock.current.status = 401; UploadMock.current.responseText = 'Unauthorized'; UploadMock.current.onload()
    await expect(result).rejects.toBeInstanceOf(AuthError); expect(expired).toHaveBeenCalledTimes(1)
  } finally { window.removeEventListener(AUTH_EXPIRED_EVENT, expired) }
})

it('上传完成后独立计算处理超时，不会用上传耗时挤占处理时间', async () => {
  vi.useFakeTimers(); vi.stubGlobal('XMLHttpRequest', UploadMock)
  try {
    const pending = uploadPdf('/api/v1/admin/catalog/import', 7, new File(['%PDF-'], 'sample.pdf'))
    const xhr = UploadMock.current
    await vi.advanceTimersByTimeAsync(110000); xhr.upload.onload?.()
    await vi.advanceTimersByTimeAsync(120000)
    expect(xhr.abort).not.toHaveBeenCalled()
    xhr.onload(); await expect(pending).resolves.toEqual({ id: 'created' })
  } finally { vi.useRealTimers() }
})
it('429 按 Retry-After 安全重试一次，409 不自动重复写入', async () => {
  vi.useFakeTimers(); vi.stubGlobal('XMLHttpRequest', UploadMock)
  try {
    const pending = uploadPdf('/api/v1/admin/catalog/import', 7, new File(['%PDF-'], 'sample.pdf'))
    const first = UploadMock.current; first.status = 429; first.onload()
    await vi.advanceTimersByTimeAsync(500)
    const second = UploadMock.current; expect(second).not.toBe(first); second.onload()
    await expect(pending).resolves.toEqual({ id: 'created' })
    const conflict = uploadPdf('/api/v1/admin/catalog/import', 7, new File(['%PDF-'], 'sample.pdf'))
    UploadMock.current.status = 409; UploadMock.current.onload()
    await expect(conflict).rejects.toMatchObject({ status: 409 })
  } finally { vi.useRealTimers() }
})
