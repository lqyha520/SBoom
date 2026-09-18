import { afterEach, expect, it, vi } from 'vitest'
import { uploadPdf } from '../catalog'
import { AUTH_EXPIRED_EVENT, AuthError } from '../api'
class UploadMock {
  static current: UploadMock
  upload: { onprogress?: (event: any) => void; onload?: () => void } = {}
  timeout = 0; status = 201; responseText = '{"id":"created"}'
  onload!: () => void; onerror!: () => void; ontimeout!: () => void; onabort!: () => void
  open = vi.fn(); setRequestHeader = vi.fn(); send = vi.fn()
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
