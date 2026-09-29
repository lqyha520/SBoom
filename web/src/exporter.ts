/**
 * 导出：PDF / PNG / 批量 ZIP / 合并 PDF
 * 全部从数据离屏渲染（mount PaperView 等分页完成再截图），不依赖预览 DOM。
 *
 * 性能：html2canvas / jspdf / jszip / PaperView 组件树均为动态 import——
 * 只有点导出时才加载（合计数百 KB），首屏 bundle 不再背上导出库。
 * 内存：批量导出逐份把画布立即转 JPEG dataURL 并释放，避免 20 份学生卷
 * 的 RGBA 画布同时驻留（scale:3 单页约 32MB，累积可达 GB 级）。
 */
import { createApp, h } from 'vue'
import type { PaperData, PaperStyle, PaperTemplate } from './types'
import type { ArchiveSnapshot } from './library'
import { answerOf, escHtml } from './utils'

/* ── html2canvas 字体基线探针的环境修正 ──
 *
 * html2canvas@1.4.1 自己造一个探针来量「行盒顶 → 基线」的距离：在 <body> 下插一个
 * 无 class/id 的裸 div（内联样式含 visibility:hidden、white-space:nowrap），里面放
 * 一个 span 和一个 1×1 的 <img>，用 `img.offsetTop - span.offsetTop + 2` 当作基线。
 * 这个算法只在「那个 img 是行内元素」时成立；而本项目的全局基础样式（Tailwind
 * preflight）写了 `img,svg,video,…{display:block}`，img 变成块级盒、被排到文字行下方，
 * 量出的基线被抬高约 1em（14.67px 字号下 ~21px，而真实值约 12px）。
 *
 * 后果：导出 PDF 时所有文字都比预览低。行高越紧偏移越大——普通段落约低 3~5px（不易
 * 察觉），而 .split-box / .compare-expr 这类 line-height:1 的小方框会低 9~11px，数字
 * 直接压到方框底边上（预览正常、导出错位）。
 *
 * 修法：只在导出期间给探针本身补回它预期的样式。选择器把范围卡死在
 * 「body 的直接子级、无 class/id、内联样式带 visibility:hidden + white-space:nowrap
 *  + font-family + font-size」的 div，以及它里面的 1×1 img——即 html2canvas 的探针，
 * 不会命中页面任何其它元素；导出结束（含异常）立即移除，不留残留。
 * 修好后实测残余偏移仅 +1~2px。 */
const PROBE_SEL =
  'body > div:not([class]):not([id])[style*="visibility: hidden"]' +
  '[style*="white-space: nowrap"][style*="font-family"][style*="font-size"]'
const PROBE_FIX_CSS =
  `${PROBE_SEL} { line-height: normal !important; }\n` +
  `${PROBE_SEL} > img[width="1"][height="1"] { display: inline !important; vertical-align: baseline !important; }`

/** 在 html2canvas 渲染期间挂上探针样式修正（见 PROBE_FIX_CSS），结束后必定移除 */
async function withProbeFix<T>(run: () => Promise<T>): Promise<T> {
  const style = document.createElement('style')
  style.setAttribute('data-lc-export', 'probe-fix')
  style.textContent = PROBE_FIX_CSS
  document.head.appendChild(style)
  try {
    return await run()
  } finally {
    style.remove()
  }
}

export function checkExportActive(signal?: AbortSignal, isActive = () => true) {
  if (signal?.aborted || !isActive()) throw new DOMException('操作已取消，已完成的云端内容仍保留', 'AbortError')
}
export function validateExportPageCount(count: number) {
  if (!count || count > 40) throw new Error('每份导出支持 1 至 40 页，请减少题目或答案页后重试')
}
export function exportScale(): number {
  const memory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory
  return !memory || memory <= 4 ? 2 : 3
}
type ExportControl = { signal?: AbortSignal; isActive?: () => boolean }
type PageConsumer = (page: HTMLCanvasElement, index: number, total: number) => Promise<void> | void
/** 每页截图、消费、释放后才处理下一页；页数在创建第一张画布前校验。 */
async function renderPages(paper: PaperData, template: PaperTemplate, style: PaperStyle,
  mode: 'student' | 'withAnswers' | 'answersOnly', addDay: boolean, consume: PageConsumer, control: ExportControl = {}) {
  const prepared: Awaited<ReturnType<typeof preparePaper>>[] = []
  const assertActive = () => checkExportActive(control.signal, control.isActive)
  try {
    assertActive()
    if (mode !== 'answersOnly') prepared.push(await preparePaper(paper, template, style, addDay, assertActive))
    if (mode !== 'student') prepared.push(await preparePaper(buildAnswerPaper(paper), template, style, false, assertActive))
    const pages = prepared.flatMap(value => value.pages)
    validateExportPageCount(pages.length)
    const { default: html2canvas } = await import('html2canvas')
    for (const [index, page] of pages.entries()) {
      assertActive()
      const canvas = await withProbeFix(() => html2canvas(page, { scale: exportScale(), backgroundColor: '#ffffff' }))
      try { assertActive(); await consume(canvas, index, pages.length) }
      finally { canvas.width = canvas.height = 0 }
    }
    assertActive()
  } finally { prepared.forEach(value => value.dispose()) }
}

/* ── 答案卷：与试卷同版式（同卷头/字体/分栏），题干位置换成 答案+解析 ── */
export function buildAnswerPaper(paper: PaperData): PaperData {
  return {
    ...paper,
    title: (paper.title || '试卷') + ' · 参考答案',
    titleHtml: undefined, // 答案卷标题不做富文本，避免继承（第X天）等
    sections: paper.sections.map(sec => ({
      ...sec,
      data: {
        ...sec.data,
        questions: (sec.data.questions || []).map((q, i) => {
          const a = answerOf(q)
          const stem =
            `<b style="color:#c0392b">答案：${escHtml(a || '（暂无答案）')}</b>` +
            (q.analysis ? `<br><span style="color:#555;font-size:9.5pt">解析：${escHtml(q.analysis)}</span>` : '')
          return {
            ...q,
            type: 'fill_blank',
            stem,
            // stem 是富文本 HTML，走 _stemHtml 通道渲染（QuestionItem 优先用它，渲染前会净化）
            _stemHtml: stem,
            // 清掉选项/连线等结构，只留题干文字
            options: undefined,
            left_items: undefined,
            right_items: undefined,
            left_expr: undefined,
            right_expr: undefined,
            top: undefined,
            left: undefined,
            right: undefined,
            _qid: 'ans_' + (q._qid || i),
          }
        }),
      },
    })),
  }
}

/* 离屏容器工厂：视口内 0×0 裁剪容器（html2canvas 对负偏移 fixed 元素有渲染裁剪 bug，
   子元素绝对定位溢出显示但不占布局，截图取的是子元素本身不受父 overflow 影响） */
function makeHolder(): HTMLElement {
  const holder = document.createElement('div')
  holder.setAttribute('aria-hidden', 'true')
  holder.style.cssText = 'position:absolute;left:0;top:0;width:0;height:0;overflow:hidden;'
  const inner = document.createElement('div')
  inner.style.cssText = 'position:absolute;left:0;top:0;background:#fff;'
  holder.appendChild(inner)
  return holder
}

/* ── JPEG dataURL → PDF（增量添加，画布侧已释放；jspdf 动态加载，模块缓存命中时零开销） ── */
type jsPDF = import('jspdf').jsPDF
async function imagesToPDF(images: string[], stampNumbers = true): Promise<jsPDF> {
  if (!images.length) throw new Error('试卷没有可导出的页面')
  const { jsPDF: JsPDF } = await import('jspdf')
  const doc = new JsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' })
  images.forEach((img, i) => {
    if (i) doc.addPage()
    doc.addImage(img, 'JPEG', 0, 0, 210, 297)
  })
  const total = images.length
  doc.setFont('times', 'normal')
  doc.setFontSize(9)
  for (let i = 1; stampNumbers && i <= total; i++) {
    doc.setPage(i)
    doc.text(`- ${i} / ${total} -`, 105, 292.5, { align: 'center' })
  }
  return doc
}

function download(blob: Blob, name: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 5000)
}

function baseTitle(paper: PaperData, template: PaperTemplate): string {
  return (
    paper.title ||
    (template.titlePrefix ? `${template.titlePrefix}·${paper.grade}${paper.subject}` : `${paper.grade}${paper.subject}`) + (template.titleSuffix || '测试卷')
  )
}

/** 同一页像素用于归档 PDF 和预览图，不同时保留多页 RGBA 画布。 */
export async function createArchiveBundle(snapshot: ArchiveSnapshot, progress?: (message: string) => void, control: ExportControl = {}): Promise<Blob> {
  const { paper, template, style, export_options: options } = snapshot
  const { default: JSZip } = await import('jszip')
  const zip = new JSZip()
  const images: string[] = []
  await renderPages(paper, template, style, options.mode, options.addDay, async (page, index, total) => {
    progress?.(`正在处理第 ${index + 1}/${total} 页`)
    const ctx = page.getContext('2d')!
    const pixelsPerMm = page.width / 210
    ctx.fillStyle = '#000000'
    ctx.font = `${9 * 25.4 / 72 * pixelsPerMm}px Times New Roman`
    ctx.textAlign = 'center'
    ctx.fillText(`- ${index + 1} / ${total} -`, page.width / 2, 292.5 * pixelsPerMm)
    images.push(page.toDataURL('image/jpeg', 0.92))
    const preview = document.createElement('canvas')
    preview.width = Math.min(1040, page.width)
    preview.height = Math.round(preview.width * 297 / 210)
    try {
      preview.getContext('2d')!.drawImage(page, 0, 0, preview.width, preview.height)
      zip.file(`page-${index + 1}.jpg`, await canvasBlob(preview, 'image/jpeg', 0.85))
    } finally { preview.width = preview.height = 0 }
  }, control)
  zip.file('paper.pdf', (await imagesToPDF(images, false)).output('arraybuffer'))
  images.length = 0
  const bundle = await zip.generateAsync({ type: 'blob', compression: 'STORE' }, () => checkExportActive(control.signal, control.isActive))
  checkExportActive(control.signal, control.isActive)
  if (bundle.size > 40 * 1024 * 1024) throw new Error('文件包超过 40 MB，请减少页数后重试')
  return bundle
}
function canvasBlob(canvas: HTMLCanvasElement, type = 'image/png', quality?: number): Promise<Blob> {
  return new Promise((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('图片生成失败')), type, quality))
}
async function paperImages(paper: PaperData, template: PaperTemplate, style: PaperStyle,
  mode: 'student' | 'withAnswers' | 'answersOnly', addDay: boolean, signal?: AbortSignal) {
  const images: string[] = []
  await renderPages(paper, template, style, mode, addDay, page => { images.push(page.toDataURL('image/jpeg', 0.92)) }, { signal })
  return images
}
export async function exportPDF(paper: PaperData, template: PaperTemplate, style: PaperStyle,
  mode: 'student' | 'withAnswers' | 'answersOnly', signal?: AbortSignal): Promise<void> {
  const doc = await imagesToPDF(await paperImages(paper, template, style, mode, true, signal))
  checkExportActive(signal)
  const suffix = mode === 'answersOnly' ? '（答案）' : mode === 'withAnswers' ? '（含答案）' : ''
  doc.save(`${baseTitle(paper, template)}${suffix}.pdf`)
}
export async function exportPNG(paper: PaperData, template: PaperTemplate, style: PaperStyle, signal?: AbortSignal): Promise<void> {
  const { default: JSZip } = await import('jszip')
  const zip = new JSZip()
  const title = baseTitle(paper, template)
  let single: Blob | undefined, count = 0
  await renderPages(paper, template, style, 'student', true, async (page, index, total) => {
    const blob = await canvasBlob(page)
    count = total
    if (total === 1) single = blob
    else zip.file(`${title}_第${index + 1}页.png`, blob)
  }, { signal })
  const blob = count === 1 ? single! : await zip.generateAsync({ type: 'blob' }, () => checkExportActive(signal))
  checkExportActive(signal)
  download(blob, `${title}.${count === 1 ? 'png' : 'zip'}`)
}
export async function exportBatch(papers: PaperData[], template: PaperTemplate, style: PaperStyle,
  opts: { addDay: boolean; mergeOnly?: boolean; signal?: AbortSignal }, onProgress?: (msg: string) => void): Promise<void> {
  if (!papers.length) throw new Error('试卷没有可导出的页面')
  const { default: JSZip } = await import('jszip')
  const zip = opts.mergeOnly ? null : new JSZip()
  const { jsPDF: JsPDF } = await import('jspdf')
  const merged = new JsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' })
  let mergedCount = 0
  const title = baseTitle(papers[0], template)
  for (const [index, paper] of papers.entries()) {
    checkExportActive(opts.signal)
    onProgress?.(`正在处理第 ${index + 1}/${papers.length} 份…`)
    const images = await paperImages(paper, template, style, 'student', opts.addDay, opts.signal)
    for (const image of images) {
      if (mergedCount++) merged.addPage()
      merged.addImage(image, 'JPEG', 0, 0, 210, 297)
    }
    if (zip) {
      const suffix = opts.addDay ? `-第${index + 1}天` : `-第${index + 1}份`
      zip.file(`${title}${suffix}-学生卷.pdf`, (await imagesToPDF(images)).output('arraybuffer'))
      images.length = 0
      onProgress?.(`正在生成第 ${index + 1} 份答案…`)
      zip.file(`${title}${suffix}-答案.pdf`, (await imagesToPDF(await paperImages(paper, template, style, 'answersOnly', false, opts.signal))).output('arraybuffer'))
    }
  }
  merged.setFont('times', 'normal'); merged.setFontSize(9)
  for (let page = 1; page <= mergedCount; page++) { merged.setPage(page); merged.text(`- ${page} / ${mergedCount} -`, 105, 292.5, { align: 'center' }) }
  checkExportActive(opts.signal)
  if (!zip) { merged.save(`${title}-全部${papers.length}份合并.pdf`); return }
  zip.file(`${title}-全部${papers.length}份合并.pdf`, merged.output('arraybuffer'))
  onProgress?.('正在打包…')
  const blob = await zip.generateAsync({ type: 'blob' }, () => checkExportActive(opts.signal))
  checkExportActive(opts.signal)
  download(blob, `${title}-${papers.length}份.zip`)
}
/** 只准备分页 DOM，先统计学生卷与答案总页数再开始截图。 */
async function preparePaper(paper: PaperData, template: PaperTemplate, style: PaperStyle, addDay: boolean, assertActive: () => void) {
  const { default: PaperView } = await import('./components/PaperView.vue')
  assertActive()
  const holder = makeHolder()
  document.body.appendChild(holder)
  const app = createApp({ render: () => h(PaperView, { paper, template, style, editable: false, addDay }) })
  const dispose = () => { app.unmount(); holder.remove() }
  try {
    app.mount(holder.firstElementChild as HTMLElement)
    await document.fonts?.ready
    const totalQ = paper.sections.reduce((sum, section) => sum + (section.data.questions?.length || 0), 0)
    const deadline = Date.now() + 10000
    let lastSig = '', stableFrames = 0
    while (Date.now() < deadline) {
      assertActive()
      await new Promise(resolve => requestAnimationFrame(resolve))
      const pages = holder.querySelectorAll('.paper-stack .paper')
      const questions = holder.querySelectorAll('.paper-stack .q')
      const sig = `${pages.length}|${questions.length}|${(holder.firstElementChild as HTMLElement).offsetHeight}`
      if (pages.length > 0 && questions.length >= totalQ && sig === lastSig) { if (++stableFrames >= 3) break }
      else { stableFrames = 0; lastSig = sig }
    }
    if (stableFrames < 3) throw new Error('试卷分页尚未完成，请稍后重试导出')
    const overflow = holder.querySelector<HTMLElement>('[data-pagination-error]')?.dataset.paginationError
    if (overflow) throw new Error(overflow)
    const pages = Array.from(holder.querySelectorAll<HTMLElement>('.paper-stack .paper'))
    if (!style.exportBg) for (const page of pages) {
      page.querySelectorAll<HTMLElement>('.paper-bg-layer, .paper-frame-layer').forEach(el => { el.style.display = 'none' })
      page.querySelectorAll('.exam-head').forEach(el => el.setAttribute('data-plain', '1'))
      for (const [name, value] of Object.entries({ seccolor: '0', frame: 'none', encourage: '0', reward: '0' })) page.setAttribute('data-' + name, value)
    }
    return { pages, dispose }
  } catch (error) { dispose(); throw error }
}

/** 打印预览栈（打印样式由 CSS @media print 控制；无需额外的 body 标记类） */
export function printStack(studentStack: HTMLElement) {
  const overflow = studentStack.querySelector<HTMLElement>('[data-pagination-error]')?.dataset.paginationError
  if (overflow) throw new Error(overflow)
  window.print()
}
