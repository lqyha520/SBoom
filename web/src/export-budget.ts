/** 限制保留的编码数据，不把 JS 堆预算误称为浏览器进程内存上限。 */
export const EXPORT_LIMITS = { pages: 120, bytes: 64 * 1024 * 1024, fileBytes: 40 * 1024 * 1024 } as const
const MESSAGE = '导出超过容量上限，请减少每批试卷数量，或逐份下载'

export class ExportBudget {
  private pages = 0
  private bytes = 0

  reservePages(count: number) {
    if (!Number.isSafeInteger(count) || count < 1 || this.pages + count > EXPORT_LIMITS.pages) throw new Error(MESSAGE)
    this.pages += count
  }

  retain(bytes: number) {
    if (!Number.isSafeInteger(bytes) || bytes < 0 || this.bytes + bytes > EXPORT_LIMITS.bytes) throw new Error(MESSAGE)
    this.bytes += bytes
  }

  checkFile(bytes: number) {
    if (!Number.isSafeInteger(bytes) || bytes < 0 || bytes > EXPORT_LIMITS.fileBytes) throw new Error(MESSAGE)
  }
}
