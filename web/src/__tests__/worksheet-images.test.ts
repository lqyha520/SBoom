import { expect, it } from 'vitest'
import JSZip from 'jszip'
import { imageBlob, type WorksheetImage } from '../image-generation'
import { buildWorksheetImagesZip } from '../worksheet-images'

const png = 'iVBORw0KGgoAAAANSUhEUgAAABgAAAAgCAIAAACHPC9vAAAAMElEQVR4nO3QMQEAAAiEwNf+nTUCi4MDF4CBmtzoo04MMR8xHzEfMR8xHzEfsX+PFkOXAT/05ckTAAAAAElFTkSuQmCC'
const widePng = 'iVBORw0KGgoAAAANSUhEUgAAACAAAAAYCAIAAAAUMWhjAAAAM0lEQVR4nO3RwQ0AMAjDwJT9d6YjmE9+vgGCZF6yaZrqejxw4A+QiZCJkImQiZCJUD3RB+/KAS9SCGTbAAAAAElFTkSuQmCC'
const image = (b64_json = png): WorksheetImage => ({ request_id: 'test', b64_json, mime_type: 'image/png', width: 24, height: 32, prompt: 'offline fixture' })

it('packages original PNG bytes from legacy results and cached blobs, preserving gaps and sortable page numbers', async () => {
  const cached = { ...image(widePng), b64_json: undefined, blob: imageBlob(image(widePng)) }
  const pages = [image(), null, cached, ...Array<null>(6).fill(null), image()]
  const done: number[] = []
  const blob = await buildWorksheetImagesZip(pages, count => done.push(count))
  expect(blob.type).toBe('application/zip')
  const zip = await JSZip.loadAsync(await blob.arrayBuffer())
  const names = Object.keys(zip.files)
  expect(names).toEqual(['习题图片-第01张.png', '习题图片-第03张.png', '习题图片-第10张.png'])
  expect([...names].sort()).toEqual(names)
  expect(await zip.file(names[0])!.async('base64')).toBe(png)
  expect(await zip.file(names[1])!.async('base64')).toBe(widePng)
  expect(await zip.file(names[2])!.async('base64')).toBe(png)
  expect(done).toEqual([1, 2, 3])
})

it('exports a single completed image without including queued pages', async () => {
  const blob = await buildWorksheetImagesZip([null, image(), null])
  const zip = await JSZip.loadAsync(await blob.arrayBuffer())
  expect(Object.keys(zip.files)).toEqual(['习题图片-第02张.png'])
})

it('rejects empty, oversized and invalid image batches without returning an incomplete archive', async () => {
  await expect(buildWorksheetImagesZip([])).rejects.toThrow('1 至 100')
  await expect(buildWorksheetImagesZip([null, null])).rejects.toThrow('1 至 100')
  await expect(buildWorksheetImagesZip(Array.from({ length: 101 }, () => image()))).rejects.toThrow('1 至 100')
  await expect(buildWorksheetImagesZip([image(), image('')])).rejects.toThrow('图片数据无效')
})

it('keeps all hundred original images sorted by page number', async () => {
  const blob = await buildWorksheetImagesZip(Array.from({ length: 100 }, () => image()))
  const zip = await JSZip.loadAsync(await blob.arrayBuffer())
  const names = Object.keys(zip.files)
  expect(names).toHaveLength(100)
  expect(names).toEqual([...names].sort())
  expect(names[0]).toBe('习题图片-第001张.png')
  expect(names[99]).toBe('习题图片-第100张.png')
  expect(await zip.file(names[99])!.async('base64')).toBe(png)
})

it('rejects oversized source bytes before building an archive', async () => {
  const blob = new Blob(['fixture'], { type: 'image/png' })
  Object.defineProperty(blob, 'size', { value: 8 * 1024 * 1024 })
  await expect(buildWorksheetImagesZip(Array.from({ length: 17 }, () => ({ ...image(), blob })))).rejects.toThrow('128 MB')
})

it('stops exporting when the page or account becomes inactive, including after the last image', async () => {
  await expect(buildWorksheetImagesZip([image()], undefined, () => true)).rejects.toThrow('已停止导出')
  let cancelled = false
  await expect(buildWorksheetImagesZip([image()], () => { cancelled = true }, () => cancelled)).rejects.toThrow('已停止导出')
})
