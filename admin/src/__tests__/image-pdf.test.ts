import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { buildImagePdf, imageFileIssue, imagePageLayout, useImagePdfComposer } from '../image-pdf'

// Real tiny JPEG: canvas is stubbed, while PDF page assembly uses the actual jsPDF library.
const jpeg = '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAADAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q=='
const bytes = Uint8Array.from(atob(jpeg), char => char.charCodeAt(0))
const file = (name: string) => new File(['image'], name, { type: 'image/jpeg' })
const draw = vi.fn(), rotate = vi.fn(), close = vi.fn(), revoke = vi.fn()
beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('createImageBitmap', vi.fn(async (source: File) => {
    if (source.name === 'broken.png') throw new Error('decode')
    return { width: source.name.startsWith('wide') ? 2000 : 1000, height: 1500, name: source.name, close }
  }))
  vi.spyOn(URL, 'createObjectURL').mockImplementation(() => 'blob:' + crypto.randomUUID())
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(revoke)
  const original = document.createElement.bind(document)
  vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => tag !== 'canvas' ? original(tag) : {
    width: 0, height: 0,
    getContext: () => ({ fillRect: vi.fn(), translate: vi.fn(), rotate, drawImage: draw }),
    toBlob: (callback: (blob: Blob) => void) => callback(new Blob([bytes], { type: 'image/jpeg' })),
  }) as typeof document.createElement)
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('横竖图片使用相应 A4 页面，等比居中且不越过页边', () => {
  for (const [width, height] of [[1000, 2000], [3000, 1000], [1000, 1000]]) {
    const layout = imagePageLayout(width, height)
    expect(layout.width / layout.height).toBeCloseTo(width / height)
    expect(layout.x).toBeGreaterThanOrEqual(4.99); expect(layout.y).toBeGreaterThanOrEqual(4.99)
    expect(layout.orientation).toBe(width > height ? 'landscape' : 'portrait')
  }
  expect(() => imagePageLayout(0, 1)).toThrow('尺寸无效')
})
it('限制图片格式、空文件和大小，损坏图片阻止合并', async () => {
  expect(imageFileIssue(file('file.svg'))).toContain('仅支持')
  expect(imageFileIssue(new File([], 'empty.png'))).toContain('为空')
  const large = file('large.jpg'); Object.defineProperty(large, 'size', { value: 21 * 1024 * 1024 })
  expect(imageFileIssue(large)).toContain('20 MB')
  const composer = useImagePdfComposer()
  await composer.add([file('good.jpg'), file('broken.png')])
  expect(composer.ready).toBe(false); expect(composer.pages[1].error).toContain('无法读取')
  composer.remove(composer.pages[1].id); expect(composer.ready).toBe(true)
  composer.dispose()
})
it('图片顺序和旋转进入真正的 PDF，N 张图仅生成 N 页', async () => {
  const composer = useImagePdfComposer()
  await composer.add([file('tall.jpg'), file('wide.jpg')])
  composer.move(1, -1); composer.rotate(composer.pages[0].id)
  draw.mockClear(); rotate.mockClear()
  composer.title = '数学/练习'
  const pdf = await composer.build()
  expect(pdf?.name).toBe('数学_练习.pdf')
  const content = await pdf!.text()
  expect(content.startsWith('%PDF-')).toBe(true)
  expect(content.match(/\/Type \/Page\b/g)).toHaveLength(2)
  expect(content).toContain('/Count 2')
  expect(draw.mock.calls.map(call => call[0].name)).toEqual(['wide.jpg', 'tall.jpg'])
  expect(rotate.mock.calls.map(call => call[0])).toEqual([Math.PI / 2, 0])
  const boxes = [...content.matchAll(/\/MediaBox \[([^\]]+)\]/g)].map(match => match[1].split(' ').map(Number))
  expect(boxes).toHaveLength(2)
  expect(boxes.every(box => box[2] < box[3])).toBe(true)
  composer.dispose(); expect(revoke).toHaveBeenCalledTimes(2)
})
it('移除和清空释放预览资源，同名图片分别排序和保留', async () => {
  const composer = useImagePdfComposer()
  await composer.add([file('same.jpg'), file('same.jpg')])
  expect(composer.pages[0].id).not.toBe(composer.pages[1].id)
  composer.remove(composer.pages[0].id); expect(composer.pages).toHaveLength(1)
  composer.clear(); expect(composer.pages).toHaveLength(0); expect(revoke).toHaveBeenCalledTimes(2)
})
it('最多 40 张，额外图片不进入清单；取消合并不返回半份 PDF', async () => {
  const composer = useImagePdfComposer()
  await composer.add(Array.from({ length: 41 }, (_, index) => file(`${index}.jpg`)))
  expect(composer.pages).toHaveLength(40); expect(composer.error).toContain('最多合并 40')
  let cancelled = false
  await expect(buildImagePdf(composer.pages, 'test', () => { cancelled = true }, () => cancelled)).rejects.toThrow('已停止合并')
  composer.dispose()
})
it('超出 PDF 大小限制时保留图片清单，允许修正后重试', async () => {
  const composer = useImagePdfComposer()
  await composer.add([file('sample.jpg')])
  const original = vi.mocked(document.createElement).getMockImplementation()!
  vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => {
    const element = original(tag) as HTMLCanvasElement
    if (tag === 'canvas') element.toBlob = callback => {
      const blob = new Blob([bytes]); Object.defineProperty(blob, 'size', { value: 33 * 1024 * 1024 }); callback(blob)
    }
    return element
  }) as typeof document.createElement)
  expect(await composer.build()).toBeUndefined(); expect(composer.error).toContain('32 MB')
  expect(composer.pages).toHaveLength(1); expect(composer.busy).toBe(false)
  composer.dispose()
})
