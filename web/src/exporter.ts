/**
 * 导出：PDF / PNG / 批量 ZIP / 合并 PDF
 * 学生卷从当前可见 DOM 克隆（保留排版模式的自由调整），答案卷由数据渲染。
 */
import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import JSZip from 'jszip'
import { createApp, h } from 'vue'
import type { PaperData, PaperStyle, PaperTemplate } from './types'
import { answerOf, cirNum } from './utils'
import { TYPE_NAME } from './constants'
import PaperView from './components/PaperView.vue'

export interface ExportOpts {
  style: PaperStyle
}

/** 克隆并清理一个纸面容器（去掉排版工具/可编辑态，按需去掉彩色装饰） */
function cleanClone(src: HTMLElement, style: PaperStyle): HTMLElement {
  const clone = src.cloneNode(true) as HTMLElement
  clone.style.display = 'block'
  clone.querySelectorAll('.offscreen, .q-tools, .sec-tools, .sort-handle, .cell-resizer, .col-resizer, .row-resizer, .q-ans-inline').forEach(b => b.remove())
  clone.querySelectorAll('[contenteditable="true"]').forEach(el => el.removeAttribute('contenteditable'))
  clone.querySelectorAll('.paper').forEach(p => {
    ;(p as HTMLElement).style.display = 'block'
    ;(p as HTMLElement).style.visibility = 'visible'
    if (!style.exportBg) {
      p.querySelectorAll('.paper-bg-layer').forEach(el => ((el as HTMLElement).style.display = 'none'))
      p.querySelectorAll('.exam-head').forEach(el => el.setAttribute('data-plain', '1'))
      p.setAttribute('data-seccolor', '0')
      p.setAttribute('data-frame', 'none')
      p.setAttribute('data-encourage', '0')
      p.setAttribute('data-reward', '0')
      p.querySelectorAll('.paper-frame-layer').forEach(el => ((el as HTMLElement).style.display = 'none'))
    }
  })
  return clone
}

/** 容器 → A4 页画布数组（在元素边界处断页） */
async function canvasesOf(holder: HTMLElement): Promise<HTMLCanvasElement[]> {
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

/** 离屏克隆指定容器并出画布 */
async function canvasesFromDOM(src: HTMLElement, style: PaperStyle): Promise<HTMLCanvasElement[]> {
  const holder = document.createElement('div')
  holder.style.cssText = 'position:fixed;left:-99999px;top:0;background:#fff;z-index:-1;'
  holder.appendChild(cleanClone(src, style))
  document.body.appendChild(holder)
  try {
    return await canvasesOf(holder)
  } finally {
    document.body.removeChild(holder)
  }
}

/* ── 答案页 DOM 构建 ── */
export function buildAnswerDOM(paper: PaperData, template: PaperTemplate): HTMLElement {
  const wrap = document.createElement('div')
  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  let html = `<div class="paper measure" data-frame="none" data-encourage="0" data-reward="0" data-kid="0" data-seccolor="0" style="height:auto;overflow:visible"><div class="exam">`
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

async function answerCanvases(paper: PaperData, template: PaperTemplate, style: PaperStyle): Promise<HTMLCanvasElement[]> {
  const dom = buildAnswerDOM(paper, template)
  const holder = document.createElement('div')
  holder.style.cssText = 'position:fixed;left:-99999px;top:0;background:#fff;z-index:-1;'
  holder.appendChild(dom)
  document.body.appendChild(holder)
  try {
    return await canvasesOf(holder)
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
  studentStack: HTMLElement,
  mode: 'student' | 'withAnswers' | 'answersOnly',
): Promise<void> {
  const parts: HTMLCanvasElement[] = []
  if (mode !== 'answersOnly') parts.push(...(await canvasesFromDOM(studentStack, style)))
  if (mode !== 'student') parts.push(...(await answerCanvases(paper, template, style)))
  const doc = pagesToPDF(parts)
  const suffix = mode === 'answersOnly' ? '（答案）' : mode === 'withAnswers' ? '（含答案）' : ''
  doc.save(`${baseTitle(paper, template)}${suffix}.pdf`)
}

export async function exportPNG(
  paper: PaperData,
  template: PaperTemplate,
  style: PaperStyle,
  studentStack: HTMLElement,
): Promise<void> {
  const pages = await canvasesFromDOM(studentStack, style)
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
  studentStack: HTMLElement,
  opts: { addDay: boolean; mergeOnly?: boolean },
  onProgress?: (msg: string) => void,
): Promise<void> {
  const zip = opts.mergeOnly ? null : new JSZip()
  const mergePages: HTMLCanvasElement[] = []
  const title = baseTitle(papers[0], template)

  for (let k = 0; k < papers.length; k++) {
    onProgress?.(`正在处理第 ${k + 1}/${papers.length} 份…`)
    const paper = papers[k]
    // 第 1 份从可见 DOM（含编辑），其余从数据渲染
    const stuPages = k === 0
      ? await canvasesFromDOM(studentStack, style)
      : await canvasesFromDOM(await renderPaperDOM(paper, template, style, opts), style)
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

/** 数据 → 离屏渲染一份学生卷 DOM（供批量导出的第 2~N 份） */
async function renderPaperDOM(
  paper: PaperData,
  template: PaperTemplate,
  style: PaperStyle,
  opts: { addDay: boolean },
): Promise<HTMLElement> {
  const holder = document.createElement('div')
  holder.style.cssText = 'position:fixed;left:-99999px;top:0;background:#fff;z-index:-1;'
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
  app.mount(holder)
  // 等分页测量完成（测量在两帧内完成，加缓冲）
  await new Promise(r => setTimeout(r, 350))
  const el = holder.cloneNode(true) as HTMLElement
  app.unmount()
  document.body.removeChild(holder)
  return el
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
