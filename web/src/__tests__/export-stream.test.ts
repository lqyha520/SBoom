import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { exportBatch, exportPDF, exportPNG } from '../exporter'
import { ExportBudget } from '../export-budget'
import { TEMPLATES } from '../constants'
import { STYLE_DEFAULTS } from '../stores/exam-local'
import type { PaperData } from '../types'

const state = vi.hoisted(() => ({ pages: 2, canvases: [] as HTMLCanvasElement[], rendered: vi.fn(), file: vi.fn(), pack: vi.fn(), abort: undefined as AbortController | undefined }))
const pdf = vi.hoisted(() => ({ addImage: vi.fn(), addPage: vi.fn(), save: vi.fn() }))
vi.mock('../components/PaperView.vue', () => ({ default: defineComponent({ setup: () => () => h('div', { class: 'paper-stack' }, Array.from({ length: state.pages }, () => h('div', { class: 'paper' }))) }) }))
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
  addImage = pdf.addImage; addPage = pdf.addPage; save = pdf.save
  getNumberOfPages() { return state.pages }
  output() { return new ArrayBuffer(3) }
  setFont() {}; setFontSize() {}; setPage() {}; text() {}
} }))

const paper: PaperData = { grade: '小学三年级', subject: '数学', keyword: '加法', difficulty: 'medium', sections: [], title: '逐页测试' }
beforeEach(() => {
  state.pages = 2; state.canvases = []; state.abort = undefined
  state.file.mockReset(); state.pack.mockReset().mockResolvedValue(new Blob(['zip']))
  pdf.addImage.mockReset(); pdf.addPage.mockReset(); pdf.save.mockReset()
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 1 })
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
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
