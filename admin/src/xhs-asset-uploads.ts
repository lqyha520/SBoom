import { onBeforeUnmount, ref } from 'vue'
import { uploadAsset, type Asset } from './xhs-workspace'
export interface AssetUpload { file: File; status: 'pending' | 'uploading' | 'done' | 'duplicate' | 'failed'; message: string; asset?: Asset }
export function useXhsAssetUploads(refresh: (rows: AssetUpload[]) => Promise<void>) {
  const rows = ref<AssetUpload[]>([]), uploading = ref(false), stopped = ref(false), error = ref('')
  let active = true
  function validation(file: File) {
    return !['image/png', 'image/jpeg', 'image/webp', 'video/mp4'].includes(file.type) || !file.size || file.size > (file.type === 'video/mp4' ? 40 : 10) * 1024 * 1024 ? '请选择有效图片（最多 10 MB）或 MP4（最多 40 MB）。' : ''
  }
  async function run(retry = false) {
    if (uploading.value) return
    uploading.value = true; stopped.value = false; error.value = ''
    try {
      for (const row of rows.value) {
        if (!active || stopped.value) break
        if (row.status !== 'pending' && !(retry && row.status === 'failed')) continue
        const invalid = validation(row.file)
        if (invalid) { row.status = 'failed'; row.message = invalid; continue }
        row.status = 'uploading'; row.message = ''
        try { row.asset = await uploadAsset(row.file); row.status = row.asset.duplicate ? 'duplicate' : 'done'; row.message = row.asset.duplicate ? '已存在，沿用原记录和来源信息' : '已上传，待补充来源' }
        catch (cause) { row.status = 'failed'; row.message = cause instanceof Error ? cause.message : '上传失败，可重试此文件' }
      }
      if (active) { try { await refresh(rows.value) } catch { error.value = '上传结果已保留，素材列表刷新失败，请点击搜索重新读取。' } }
    } finally { uploading.value = false }
  }
  async function choose(files: File[]) {
    if (uploading.value) return
    error.value = ''
    if (files.length > 20 || files.reduce((sum, file) => sum + file.size, 0) > 200 * 1024 * 1024) { error.value = '每批最多 20 个文件，合计最多 200 MB，请分批选择。'; return }
    rows.value = files.map(file => ({ file, status: 'pending', message: '' }))
    await run()
  }
  onBeforeUnmount(() => { active = false; stopped.value = true; rows.value = [] })
  return { rows, uploading, stopped, error, choose, run, stop: () => { stopped.value = true } }
}
