export function formatDate(seconds: number) {
  const date = new Date(seconds * 1000)
  return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, '0')}.${String(date.getDate()).padStart(2, '0')}`
}
export function fileSize(bytes: number) { return bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB` }
export function fileStatus(status: string) { return ({ pending: '文件待上传', uploading: '文件上传中', failed: '文件未就绪', ready: '已归档' } as Record<string, string>)[status] || status }
