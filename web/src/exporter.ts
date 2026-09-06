/**
 * 导出：PDF / PNG / 批量 ZIP / 合并 PDF
 * 全部从数据离屏渲染（mount PaperView 等分页完成再截图），不依赖预览 DOM。
 */
import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import JSZip from 'jszip'
import { createApp, h } from 'vue'
import type { PaperData, PaperStyle, PaperTemplate } from './types'
import { answerOf, cirNum } from './utils'
import { TYPE_NAME } from './constants'
import PaperView from './components/PaperView.vue'

/** 容器 → A4 页画布数组（在元素边界处断页）；按需关闭彩色装饰（省墨） */
async function canvasesOf(holder: HTMLElement, style?: PaperStyle): Promise<HTMLCanvasElement[]> {
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
  }
  return pages
}

/* ── 答案页 DOM 构建 ── */
export function buildAnswerDOM(paper: PaperData, template: PaperTemplate): HTMLElement {
  const wrap = document.createElement('div')
  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // 注意：不带 .measure 类（canvasesOf 会跳过 measure 纸），高度自适应由内联样式控制
  // display:block 覆盖 .paper 的 flex（html2canvas 对 auto 高度 flex 容器渲染异常）
  let html = `<div class="paper" data-frame="none" data-encourage="0" data-reward="0" data-kid="0" data-seccolor="0" style="height:auto;overflow:visible;display:block"><div class="exam" style="display:block">`
  html += `<h1 style="font-size:16pt;text-align:center;font-family:'SimHei','Microsoft YaHei',sans-serif;letter-spacing:2px;margin-bottom:4mm;">参考答案与解析</h1>`
  paper.sections.forEach(sec => {
    const qs = sec.data.questions || []
    if (!qs.length) return
    html += `<h2 class="sec">${TYPE_NAME[sec.type] || sec.type}</h2>`
    qs.forEach((q, qi) => {
      html += `<div style="margin-bottom:3mm"><b>${cirNum(qi + 1)}</b> `
      const a = answerOf(q)
      html += a ? `答案：${esc(a)}` : '<span style="color:#999">（暂无答案）</span>'
      if (q.analysis) html += `<br><span style="color:#666;font-size:9pt">解析：${esc(q.analysis)}</span>`
      html += `</div>`
    })
  })
  html += `</div></div>`
  wrap.innerHTML = html
  return wrap
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
  const dom = buildAnswerDOM(paper, template)
  const holder = makeHolder()
  holder.firstElementChild!.appendChild(dom)
  document.body.appendChild(holder)
  try {
    // 等两帧 + 字体就绪，确保答案 DOM 完成布局
    try { await (document as any).fonts?.ready } catch { /* ignore */ }
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))
    return await canvasesOf(holder, style)
  } finally {
    document.body.removeChild(holder)
  }
}

/* ── 画布 → PDF ── */
function pagesToPDF(pages: HTMLCanvasElement[]): jsPDF {
  const doc = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' })
  pages.forEach((pc, i) => {
    if (i) doc.addPage()
    doc.addImage(pc.toDataURL('image/jpeg', 0.92), 'JPEG', 0, 0, 210, 297)
  })
  const total = pages.length
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
  _studentStack: HTMLElement,
  mode: 'student' | 'withAnswers' | 'answersOnly',
): Promise<void> {
  const parts: HTMLCanvasElement[] = []
  if (mode !== 'answersOnly') parts.push(...(await studentCanvases(paper, template, style, true)))
  if (mode !== 'student') parts.push(...(await answerCanvases(paper, template, style)))
  const doc = pagesToPDF(parts)
  const suffix = mode === 'answersOnly' ? '（答案）' : mode === 'withAnswers' ? '（含答案）' : ''
  doc.save(`${baseTitle(paper, template)}${suffix}.pdf`)
}

export async function exportPNG(
  paper: PaperData,
  template: PaperTemplate,
  style: PaperStyle,
  _studentStack: HTMLElement,
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
  _studentStack: HTMLElement,
  opts: { addDay: boolean; mergeOnly?: boolean },
  onProgress?: (msg: string) => void,
): Promise<void> {
  const zip = opts.mergeOnly ? null : new JSZip()
  const mergePages: HTMLCanvasElement[] = []
  const title = baseTitle(papers[0], template)

  for (let k = 0; k < papers.length; k++) {
    onProgress?.(`正在处理第 ${k + 1}/${papers.length} 份…`)
    const paper = papers[k]
    const stuPages = await studentCanvases(paper, template, style, opts.addDay)
    mergePages.push(...stuPages)
    if (zip) {
      const suffix = opts.addDay && papers.length > 1 ? `-第${k + 1}天` : `-第${k + 1}份`
      zip.file(`${title}${suffix}-学生卷.pdf`, pagesToPDF(stuPages).output('arraybuffer'))
      onProgress?.(`正在生成第 ${k + 1} 份答案…`)
      const ansPages = await answerCanvases(paper, template, style)
      zip.file(`${title}${suffix}-答案.pdf`, pagesToPDF(ansPages).output('arraybuffer'))
    }
  }

  onProgress?.('正在合并 PDF…')
  const merged = pagesToPDF(mergePages)
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

export function printStack(studentStack: HTMLElement) {
  document.body.classList.add('printing')
  window.print()
  const cleanup = () => {
    document.body.classList.remove('printing')
    window.removeEventListener('afterprint', cleanup)
  }
  window.addEventListener('afterprint', cleanup)
  setTimeout(cleanup, 60000)
}
