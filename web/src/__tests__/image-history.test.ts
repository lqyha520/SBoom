import 'fake-indexeddb/auto'
import { Blob as NativeBlob } from 'node:buffer'
import { beforeEach, expect, it, vi } from 'vitest'
import { useImageBatch } from '../image-batch'
import { fetchImageStatus, generateWorksheetImage, type ImageWorksheetParams } from '../image-generation'
vi.mock('../image-generation', async original => ({ ...await original<typeof import('../image-generation')>(), generateWorksheetImage: vi.fn(), fetchImageStatus: vi.fn() }))
const params: ImageWorksheetParams = { grade: '小学三年级', subject: '数学', keyword: '加法', difficulty: 'medium', items: [{ game_type: 'quiz', question_count: 4 }], style: 'clean', requirements: '' }
beforeEach(() => {
  vi.stubGlobal('Blob', NativeBlob) // fake-indexeddb uses Node structuredClone, which preserves native Blob.
  vi.resetAllMocks(); localStorage.clear()
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  vi.mocked(generateWorksheetImage).mockImplementation(async (_, id) => ({ request_id: id, b64_json: btoa('image'), mime_type: 'image/png', width: 2, height: 3, prompt: 'test' }))
})
it('keeps previous batches and recovers their images locally after reload without paid or server calls', async () => {
  const batch = useImageBatch('history-test', () => true, () => {})
  await batch.start(params, 2)
  const oldId = batch.state.pages[0].id
  await batch.start({ ...params, keyword: '减法' }, 1)
  expect(batch.history).toHaveLength(1)
  const historyId = batch.history[0].id
  batch.dispose()
  const restored = useImageBatch('history-test', () => true, () => {})
  await restored.restore()
  await restored.selectHistory(historyId)
  expect(restored.state.pages[0].id).toBe(oldId)
  expect(restored.completed).toBe(2)
  expect(restored.parameters()?.keyword).toBe('加法')
  expect(generateWorksheetImage).toHaveBeenCalledTimes(3)
  expect(fetchImageStatus).not.toHaveBeenCalled()
  restored.dispose()
})
it('does not expose another account history and bounds history to ten batches', async () => {
  const batch = useImageBatch('owner-a', () => true, () => {})
  for (let i = 0; i < 12; i++) await batch.start(params, 1)
  expect(batch.history).toHaveLength(10)
  const other = useImageBatch('owner-b', () => true, () => {})
  await other.restore()
  expect(other.history).toHaveLength(0)
  expect(other.completed).toBe(0)
  batch.dispose(); other.dispose()
})
