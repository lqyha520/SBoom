/**
 * 工作台与管理后台共用的文件下载触发。
 *
 * 关键点：`<a>` 必须挂进文档后再 `click()`。只设置 href/download 的分离节点
 * 在 Firefox 上不会触发下载（PNG/ZIP/CSV 导出会静默失效），所以这里统一
 * append → click → remove，并可选地延迟释放 object URL。
 */

/** 触发一次下载；url 为已存在的地址（含 object URL）。 */
export function triggerDownload(url: string, name: string): void {
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.append(link)
  link.click()
  link.remove()
}

/** 由 Blob 生成 object URL 下载，并在延迟后释放，避免长时间占用内存。 */
export function downloadBlob(blob: Blob, name: string, revokeDelayMs = 5000): void {
  const url = URL.createObjectURL(blob)
  triggerDownload(url, name)
  setTimeout(() => URL.revokeObjectURL(url), revokeDelayMs)
}