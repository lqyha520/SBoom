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
import { answerOf, escHtml } from './utils'

/** 容器 → A4 页画布数组（在元素边界处断页）；按需关闭彩色装饰（省墨） */
async function canvasesOf(holder: HTMLElement, style?: PaperStyle): Promise<HTMLCanvasElement[]> {
  const { default: html2canvas } = await import('html2canvas')
  if (style && !style.exportBg) {
    holder.querySelectorAll('.paper').forEach(p => {
      p.querySelectorAll('.paper-bg-layer').forEach(el => ((el as HTMLElement).style.display = 'none'))
      p.querySelectorAll('.exam-head').forEach(el => el.setAttribute('data-plain', '1'))
      p.setAttribute('data-seccolor', '0')
      p.setAttribute('data-frame', 'none')
      p.setAttribute('data-encourage', '0')
      p.setAttribute('data-reward', '0')
      p.querySelectorAll('.paper-frame-layer').forEach(el => ((el as HTMLElement).style.display = 'none'))
    })
  }
  const pages: HTMLCanvasElement[] = []
  for (const paper of Array.from(holder.querySelectorAll('.paper:not(.measure)'))) {
    const canvas = await html2canvas(paper as HTMLElement, { scale: 3, backgroundColor: '#ffffff' })
    const W = canvas.width
    const pageH = Math.round(W * 297 / 210)

    const scale = W / (paper as HTMLElement).offsetWidth
    const breaks: number[] = []
    ;(paper as HTMLElement).querySelectorAll('.exam > *').forEach(el => {
      breaks.push(Math.round((el as HTMLElement).offsetTop * scale) + Math.round((el as HTMLElement).offsetHeight * scale))
    })
    breaks.sort((a, b) => a - b)

    let y = 0
    while (y < canvas.height - 2) {
      let cut = y + pageH
      if (cut < canvas.height) {
        const ok = breaks.filter(b => b > y + pageH * 0.55 && b <= cut)
        if (ok.length) cut = ok[ok.length - 1]
      } else {
        cut = canvas.height
      }
      const h = cut - y
      const page = document.createElement('canvas')
      page.width = W
      page.height = pageH
      const ctx = page.getContext('2d')!
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, W, pageH)
      ctx.drawImage(canvas, 0, y, W, h, 0, 0, W, h)
      pages.push(page)
      y = cut
    }
    // 长图已切页，立即释放整卷大画布
    canvas.width = canvas.height = 0
  }
  return pages
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
  holder.style.cssText = 'position:absolute;left:0;top:0;width:0;height:0;overflow:hidden;'
  const inner = document.createElement('div')
  inner.style.cssText = 'position:absolute;left:0;top:0;background:#fff;'
  holder.appendChild(inner)
  return holder
}

async function answerCanvases(paper: PaperData, template: PaperTemplate, style: PaperStyle): Promise<HTMLCanvasElement[]> {
  // 答案卷与学生卷同一渲染管线（同版式、块级分页不切断单条答案）
  const ansPaper = buildAnswerPaper(paper)
  return renderPaperCanvases(ansPaper, template, style, { addDay: false })
}

/* ── 画布 ↔ JPEG：立即转 dataURL 并释放画布（批量导出防内存峰值） ── */
function canvasesToJpegs(pages: HTMLCanvasElement[], quality = 0.92): string[] {
  const imgs = pages.map(pc => pc.toDataURL('image/jpeg', quality))
  // 归零宽高可立刻释放 RGBA 缓冲（比等 GC 确定性高）
  pages.forEach(pc => { pc.width = pc.height = 0 })
  return imgs
}

/* ── JPEG dataURL → PDF（增量添加，画布侧已释放；jspdf 动态加载，模块缓存命中时零开销） ── */
type jsPDF = import('jspdf').jsPDF
async function imagesToPDF(images: string[]): Promise<jsPDF> {
  const { jsPDF: JsPDF } = await import('jspdf')
  const doc = new JsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' })
  images.forEach((img, i) => {
    if (i) doc.addPage()
    doc.addImage(img, 'JPEG', 0, 0, 210, 297)
  })
  const total = images.length
  doc.setFont('times', 'normal')
  doc.setFontSize(9)
  for (let i = 1; i <= total; i++) {
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

/* ── 单份导出 ── */
export async function exportPDF(
  paper: PaperData,
  template: PaperTemplate,
  style: PaperStyle,
  mode: 'student' | 'withAnswers' | 'answersOnly',
): Promise<void> {
  const images: string[] = []
  if (mode !== 'answersOnly') images.push(...canvasesToJpegs(await studentCanvases(paper, template, style, true)))
  if (mode !== 'student') images.push(...canvasesToJpegs(await answerCanvases(paper, template, style)))
  const doc = await imagesToPDF(images)
  const suffix = mode === 'answersOnly' ? '（答案）' : mode === 'withAnswers' ? '（含答案）' : ''
  doc.save(`${baseTitle(paper, template)}${suffix}.pdf`)
}

export async function exportPNG(
  paper: PaperData,
  template: PaperTemplate,
  style: PaperStyle,
): Promise<void> {
  const pages = await studentCanvases(paper, template, style, true)
  const title = baseTitle(paper, template)
  pages.forEach((pc, i) => {
    pc.toBlob(blob => blob && download(blob, `${title}_第${i + 1}页.png`))
  })
}

/* ── 批量导出（全部 ZIP / 仅合并 PDF） ── */
export async function exportBatch(
  papers: PaperData[],
  template: PaperTemplate,
  style: PaperStyle,
  opts: { addDay: boolean; mergeOnly?: boolean },
  onProgress?: (msg: string) => void,
): Promise<void> {
  const { default: JSZip } = await import('jszip')
  const zip = opts.mergeOnly ? null : new JSZip()
  // 合并卷不再累积画布：逐份转 JPEG（每份处理完即释放 RGBA 内存）
  const mergedImages: string[] = []
  const title = baseTitle(papers[0], template)

  for (let k = 0; k < papers.length; k++) {
    onProgress?.(`正在处理第 ${k + 1}/${papers.length} 份…`)
    const paper = papers[k]
    const stuImgs = canvasesToJpegs(await studentCanvases(paper, template, style, opts.addDay))
    mergedImages.push(...stuImgs)
    if (zip) {
      const suffix = opts.addDay && papers.length > 1 ? `-第${k + 1}天` : `-第${k + 1}份`
      zip.file(`${title}${suffix}-学生卷.pdf`, (await imagesToPDF(stuImgs)).output('arraybuffer'))
      onProgress?.(`正在生成第 ${k + 1} 份答案…`)
      const ansImgs = canvasesToJpegs(await answerCanvases(paper, template, style))
      zip.file(`${title}${suffix}-答案.pdf`, (await imagesToPDF(ansImgs)).output('arraybuffer'))
    }
  }

  onProgress?.('正在合并 PDF…')
  const merged = await imagesToPDF(mergedImages)
  if (!zip) {
    merged.save(`${title}-全部${papers.length}份合并.pdf`)
    return
  }
  zip.file(`${title}-全部${papers.length}份合并.pdf`, merged.output('arraybuffer'))
  onProgress?.('正在打包…')
  const blob = await zip.generateAsync({ type: 'blob' })
  download(blob, `${title}-${papers.length}份.zip`)
}

/** 数据 → 离屏渲染一份学生卷并出画布（确定性等待渲染完成后再截图） */
async function renderPaperCanvases(
  paper: PaperData,
  template: PaperTemplate,
  style: PaperStyle,
  opts: { addDay: boolean },
): Promise<HTMLCanvasElement[]> {
  const { default: PaperView } = await import('./components/PaperView.vue')
  const holder = makeHolder()
  const mountPoint = holder.firstElementChild as HTMLElement
  document.body.appendChild(holder)

  const app = createApp({
    render: () =>
      h(PaperView, {
        paper,
        template,
        style,
        editable: false,
        addDay: opts.addDay,
      }),
  })
  app.mount(mountPoint)
  try {
    const totalQ = paper.sections.reduce((s, x) => s + (x.data.questions?.length || 0), 0)
    const deadline = Date.now() + 10000
    let lastSig = ''
    let stableFrames = 0
    // 等待：纸页出现、题数齐全、连续 3 帧签名不变（分页/字体/布局全部稳定）
    while (Date.now() < deadline) {
      await new Promise(r => requestAnimationFrame(r))
      const papers = holder.querySelectorAll('.paper-stack .paper')
      const qs = holder.querySelectorAll('.paper-stack .q')
      const sig = `${papers.length}|${qs.length}|${(holder.firstElementChild as HTMLElement).offsetHeight}`
      if (papers.length > 0 && qs.length >= totalQ && sig === lastSig) {
        stableFrames++
        if (stableFrames >= 3) break
      } else {
        stableFrames = 0
        lastSig = sig
      }
    }
    return await canvasesOf(holder, style)
  } finally {
    app.unmount()
    document.body.removeChild(holder)
  }
}

/** 学生卷从数据渲染导出（不再克隆预览 DOM，避开 zoom/克隆态问题） */
async function studentCanvases(
  paper: PaperData,
  template: PaperTemplate,
  style: PaperStyle,
  addDay: boolean,
): Promise<HTMLCanvasElement[]> {
  return renderPaperCanvases(paper, template, style, { addDay })
}

/** 打印预览栈（打印样式由 CSS @media print 控制；无需额外的 body 标记类） */
export function printStack(_studentStack: HTMLElement) {
  window.print()
}
