import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createArchiveBundle, exportBatch, exportPDF, exportPNG } from '../exporter'
import { captureCollection, captureSnapshot } from '../library'
import { ExportBudget } from '../export-budget'
import { DEFAULT_LAYOUT, TEMPLATES } from '../constants'
import { STYLE_DEFAULTS } from '../stores/exam-local'
import type { PaperData } from '../types'

const state = vi.hoisted(() => ({ pages: 2, canvases: [] as HTMLCanvasElement[], rendered: vi.fn(), mounted: vi.fn(), file: vi.fn(), pack: vi.fn(), abort: undefined as AbortController | undefined }))
const pdf = vi.hoisted(() => ({ addImage: vi.fn(), addPage: vi.fn(), save: vi.fn(), documents: [] as { count: number }[] }))
vi.mock('../components/PaperView.vue', () => ({ default: defineComponent({ props: ['paper'], setup: props => {
  state.mounted(JSON.parse(JSON.stringify(props.paper)))
  return () => h('div', { class: 'paper-stack' }, Array.from({ length: state.pages }, () => h('div', { class: 'paper' },
    (props.paper as PaperData).sections.flatMap(section => section.data.questions.map(() => h('div', { class: 'q' }))))))
} }) }))
vi.mock('html2canvas', () => ({ default: async (page: HTMLElement, options: { ignoreElements: (element: HTMLElement) => boolean }) => {
  state.rendered()
  expect(options.ignoreElements(page)).toBe(false)
  expect(options.ignoreElements(page.parentElement!)).toBe(false)
  expect([...page.parentElement!.children].filter(el => options.ignoreElements(el as HTMLElement))).toHaveLength(state.pages - 1)
  if (state.canvases.length) expect(state.canvases.at(-1)!.width).toBe(0)
  const canvas = document.createElement('canvas'); canvas.width = 100; canvas.height = 140
  canvas.toBlob = (callback, type, quality) => {
    if (type === 'image/jpeg') expect(quality).toBe(0.92)
    callback(new Blob(['image'], { type }))
  }
  canvas.toDataURL = () => { throw new Error('不应使用同步 Base64 编码') }
  state.canvases.push(canvas)
  state.abort?.abort()
  return canvas
} }))
vi.mock('jszip', () => ({ default: class { file = state.file; generateAsync = state.pack } }))
vi.mock('jspdf', () => ({ jsPDF: class {
  count = 0
  constructor() { pdf.documents.push(this) }
  addImage(...args: unknown[]) { this.count++; pdf.addImage(...args) }
  addPage = pdf.addPage; save = pdf.save
  getNumberOfPages() { return state.pages }
  output() { return new ArrayBuffer(3) }
  setFont() {}; setFontSize() {}; setPage() {}; text() {}
} }))

const paper: PaperData = { grade: '小学三年级', subject: '数学', keyword: '加法', difficulty: 'medium', sections: [], title: '逐页测试' }
beforeEach(() => {
  state.pages = 2; state.canvases = []; state.abort = undefined
  state.file.mockReset(); state.pack.mockReset().mockResolvedValue(new Blob(['zip']))
  pdf.addImage.mockReset(); pdf.addPage.mockReset(); pdf.save.mockReset()
  pdf.documents = []
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 1 })
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ fillText: vi.fn(), drawImage: vi.fn() } as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((callback, type) => callback(new Blob(['preview'], { type })))
})
it('PDF 保持 JPEG 质量，直接复用二进制数据并逐页释放', async () => {
  await exportPDF(paper, TEMPLATES[0], STYLE_DEFAULTS, 'student')
  expect(pdf.addImage).toHaveBeenCalledTimes(2)
  expect(pdf.addImage.mock.calls[0][0]).toBeInstanceOf(Uint8Array)
  expect(new TextDecoder().decode(pdf.addImage.mock.calls[0][0])).toBe('image')
  expect(pdf.addPage).toHaveBeenCalledOnce()
  expect(pdf.save).toHaveBeenCalledOnce()
  expect(state.canvases.every(canvas => canvas.width === 0 && canvas.height === 0)).toBe(true)
})
afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = '' })

it('多页 PNG 逐页释放画布，仅打包下载一次', async () => {
  await exportPNG(paper, TEMPLATES[0], STYLE_DEFAULTS)
  expect(state.rendered).toHaveBeenCalledTimes(2)
  expect(state.canvases.every(canvas => canvas.width === 0 && canvas.height === 0)).toBe(true)
  expect(state.file).toHaveBeenCalledTimes(2)
  expect(state.pack).toHaveBeenCalledOnce()
  expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce()
  expect(document.querySelector('.paper-stack')).toBeNull()
})
it('超过 40 页在开始截图前拒绝', async () => {
  state.pages = 41
  await expect(exportPNG(paper, TEMPLATES[0], STYLE_DEFAULTS)).rejects.toThrow('1 至 40 页')
  expect(state.rendered).not.toHaveBeenCalled()
  expect(document.querySelector('.paper-stack')).toBeNull()
})
it('取消后释放当前画布并停止下一页及下载', async () => {
  state.abort = new AbortController()
  await expect(exportPNG(paper, TEMPLATES[0], STYLE_DEFAULTS, state.abort.signal)).rejects.toMatchObject({ name: 'AbortError' })
  expect(state.rendered).toHaveBeenCalledOnce()
  expect(state.canvases[0].width).toBe(0)
  expect(state.pack).not.toHaveBeenCalled()
  expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
  expect(document.querySelector('.paper-stack')).toBeNull()
})

it('合并导出达到整批页数上限后，在下一份截图前停止且不下载残卷', async () => {
  state.pages = 40
  await expect(exportBatch([paper, paper, paper, paper], TEMPLATES[0], STYLE_DEFAULTS, { addDay: false, mergeOnly: true })).rejects.toThrow('容量上限')
  expect(state.rendered).toHaveBeenCalledTimes(120)
  expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
  expect(document.querySelector('[data-export-holder]')).toBeNull()
})

it('ZIP 学生卷、合并卷、答案和序列化文件均计入同一预算', async () => {
  const retain = vi.spyOn(ExportBudget.prototype, 'retain')
  const reserve = vi.spyOn(ExportBudget.prototype, 'reservePages')
  await exportBatch([paper], TEMPLATES[0], STYLE_DEFAULTS, { addDay: false })
  expect(reserve.mock.calls).toEqual([[2], [2]])
  expect(retain.mock.calls).toEqual([[10], [10], [3], [5], [5], [3], [3]])
  expect(state.file).toHaveBeenCalledTimes(3)
  expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce()
})

it('编码预算超限后释放画布，不开始下一页、合成或下载', async () => {
  vi.spyOn(ExportBudget.prototype, 'retain').mockImplementation(() => { throw new Error('容量上限') })
  await expect(exportBatch([paper], TEMPLATES[0], STYLE_DEFAULTS, { addDay: false })).rejects.toThrow('容量上限')
  expect(state.rendered).toHaveBeenCalledOnce()
  expect(state.canvases[0].width).toBe(0)
  expect(state.pack).not.toHaveBeenCalled()
  expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
  expect(document.querySelector('[data-export-holder]')).toBeNull()
})

it('二十份含答案试卷生成一份 PDF 和连续 80 页预览，逐页释放画布', async () => {
  const { snapshot } = await captureCollection(Array.from({ length: 20 }, () => ({ ...paper })), TEMPLATES[0], STYLE_DEFAULTS, 'withAnswers', false, '合订本')
  await createArchiveBundle(snapshot)
  expect(pdf.addImage).toHaveBeenCalledTimes(80)
  expect(pdf.addPage).toHaveBeenCalledTimes(79)
  expect(state.file.mock.calls.map(call => call[0])).toEqual([...Array.from({ length: 80 }, (_, i) => `page-${i + 1}.jpg`), 'paper.pdf'])
  expect(state.pack).toHaveBeenCalledOnce()
  expect(state.canvases.every(canvas => canvas.width === 0)).toBe(true)
  expect(document.querySelector('[data-export-holder]')).toBeNull()
})

it('合订本超过整批页数限制时不打包残卷，单份归档仍限制 40 页', async () => {
  const { snapshot } = await captureCollection(Array.from({ length: 4 }, () => ({ ...paper })), TEMPLATES[0], STYLE_DEFAULTS, 'student', false, '')
  state.pages = 40
  await expect(createArchiveBundle(snapshot)).rejects.toThrow('容量上限')
  expect(state.rendered).toHaveBeenCalledTimes(120)
  expect(state.pack).not.toHaveBeenCalled()
  expect(document.querySelector('[data-export-holder]')).toBeNull()
})

it('二十份分开保存为两个 PDF，仅学生卷生成预览，所有标题与内容保持一致', async () => {
  state.pages = 1
  const papers = Array.from({ length: 20 }, (_, index) => ({ ...paper, title: '原标题' + index }))
  const { snapshot } = await captureCollection(papers, TEMPLATES[0], STYLE_DEFAULTS, 'withAnswers', false, '同一套', true)
  await createArchiveBundle(snapshot)
  expect(pdf.documents.map(doc => doc.count)).toEqual([20, 20])
  expect(state.file.mock.calls.map(call => call[0])).toEqual([...Array.from({ length: 20 }, (_, i) => `page-${i + 1}.jpg`), 'paper.pdf', 'answers.pdf'])
  expect(state.mounted.mock.calls.filter((_, i) => i % 2 === 0).map(([value]) => value)).toEqual(papers)
  expect(state.canvases.every(canvas => canvas.width === 0)).toBe(true)
})

it('分开的两个 PDF 仍共同计入每份 40 页上限，超限不上传残卷', async () => {
  state.pages = 21
  await expect(createArchiveBundle(captureSnapshot(paper, TEMPLATES[0], STYLE_DEFAULTS, 'withAnswers', false, true))).rejects.toThrow('1 至 40 页')
  expect(state.pack).not.toHaveBeenCalled()
  expect(document.querySelector('[data-export-holder]')).toBeNull()
})

it.each(['student', 'withAnswers', 'answersOnly'] as const)('合并 %s 与逐份导出使用完全相同的标题、富文本和内容', async mode => {
  const papers: PaperData[] = ['自定标题', '另一份原标题'].map((title, index) => ({ ...paper, title, titleHtml: `<b>${title}</b>`, day: index + 1,
    archiveSourceId: 'original-' + index, footerOverride: '自定页脚', hiddenElements: ['reward'],
    sections: [{ type: 'quiz', layout: { ...DEFAULT_LAYOUT }, data: { questions: [{ stem: '8 + 7 = ?', _stemHtml: '<b>8</b> + 7 = ?', answer: 15, analysis: '8 + 2 = 10，10 + 5 = 15。' }] } }] }))
  const original = structuredClone(papers)
  const { snapshot } = await captureCollection(papers, TEMPLATES[0], STYLE_DEFAULTS, mode, false, '仅文件名')
  await createArchiveBundle(snapshot)
  const merged = state.mounted.mock.calls.map(([value]) => value)
  state.mounted.mockClear()
  for (const value of papers) await createArchiveBundle(captureSnapshot(value, TEMPLATES[0], STYLE_DEFAULTS, mode, false))
  expect(merged).toEqual(state.mounted.mock.calls.map(([value]) => value))
  expect(papers).toEqual(original)
})
