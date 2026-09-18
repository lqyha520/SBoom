export interface DownloadSettings {
  download_mode?: 'pdf' | 'external'
  external_url?: string
  external_code?: string
}
export const defaultDownloadSettings = () => ({ download_mode: 'pdf' as const, external_url: '', external_code: '' })
export function downloadSettingsIssue(value: DownloadSettings) {
  if (value.download_mode !== 'external') return ''
  const raw = value.external_url?.trim() || ''
  if (!raw) return '请填写网盘链接'
  try {
    const url = new URL(raw)
    if (!/^https?:\/\//i.test(raw) || !['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password
      || /[\s\\\x00-\x1f\x7f]/.test(raw) || raw.length > 2000) throw new Error()
  } catch { return '请填写完整的 http:// 或 https:// 网盘链接，提取码请单独填写' }
  if ((value.external_code || '').length > 100 || /[\x00-\x1f\x7f]/.test(value.external_code || '')) return '提取码格式无效'
  return ''
}
export function downloadPayload(value: DownloadSettings) {
  return value.download_mode === 'external'
    ? { download_mode: 'external' as const, external_url: value.external_url?.trim() || '', external_code: value.external_code?.trim() || '' }
    : defaultDownloadSettings()
}
