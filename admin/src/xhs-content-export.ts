import { downloadBlob } from '../../shared/download'
import type { DraftData, MaterialData } from './xhs-workflow'

export function wrapCanvasText(context: CanvasRenderingContext2D, text: string, width: number): string[] {
  const result: string[] = []
  for (const paragraph of text.split('\n')) {
    let line = ''
    for (const char of Array.from(paragraph)) {
      if (line && context.measureText(line + char).width > width) { result.push(line); line = char }
      else line += char
    }
    result.push(line)
  }
  return result
}
function canvas(width: number, height: number, color = '#ffffff') {
  const value = document.createElement('canvas'); value.width = width; value.height = height
  const ctx = value.getContext('2d'); if (!ctx) throw new Error('当前浏览器无法生成图片')
  ctx.fillStyle = color; ctx.fillRect(0, 0, width, height); ctx.textBaseline = 'top'
  return { value, ctx }
}
const png = (value: HTMLCanvasElement) => new Promise<Blob>((resolve, reject) => value.toBlob(blob => blob ? resolve(blob) : reject(new Error('图片导出失败')), 'image/png'))
const safeFilename = (value: string) => value.replace(/[<>:"/\\|?*\x00-\x1f]/g, '-').slice(0, 80) || '学习资料'

export async function materialDocument(data: MaterialData, answers: boolean, preview = false): Promise<{ pdf: Blob; pages: string[] }> {
  if (!data.questions.length) throw new Error('请先添加题目')
  for (const [index, question] of data.questions.entries()) {
    if (!question.stem.trim()) throw new Error(`第 ${index + 1} 题还没有题干，请补全后预览或导出`)
    if (answers && (!question.answer.trim() || !question.analysis.trim())) throw new Error(`第 ${index + 1} 题的答案或讲解未补全，请完善后导出答案卷`)
  }
  const { jsPDF } = await import('jspdf')
  const pdf = new jsPDF({ unit: 'mm', format: 'a4', compress: true })
  const pages: string[] = []
  let sheet = canvas(1240, 1754), y = 80, number = 0
  const flush = (next = true) => {
    const page = sheet.value.toDataURL('image/jpeg', 0.92)
    if (preview) pages.push(page)
    if (number) pdf.addPage()
    pdf.addImage(page, 'JPEG', 0, 0, 210, 297); sheet.value.width = 0; number++
    if (next) { sheet = canvas(1240, 1754); y = 80 }
  }
  const text = (value: string, size = 28, bold = false) => {
    sheet.ctx.font = `${bold ? 'bold ' : ''}${size}px "Microsoft YaHei", sans-serif`
    const lines = wrapCanvasText(sheet.ctx, value, 1080)
    for (const line of lines) {
      if (y + size * 1.6 > 1630) { flush(); sheet.ctx.font = `${bold ? 'bold ' : ''}${size}px "Microsoft YaHei", sans-serif` }
      sheet.ctx.fillStyle = '#233e31'; sheet.ctx.fillText(line, 80, y); y += size * 1.6
    }
  }
  text(data.title + (answers ? ' · 答案与讲解' : ''), 38, true)
  text(`${data.grade} · ${data.subject} · ${data.keyword}`, 24); y += 15
  if (data.instructions) text(data.instructions, 24)
  if (!answers) text('姓名：________________    日期：________________', 24)
  for (const [index, item] of data.questions.entries()) {
    y += 25; text(`${index + 1}. ${item.stem}`, 28, true)
    if (answers) { text(`答案：${item.answer}`, 26); text(`讲解：${item.analysis}`, 26) }
    else { for (const [i, option] of item.options.entries()) text(`${String.fromCharCode(65 + i)}. ${option}`, 26); y += 60 }
  }
  flush(false)
  return { pdf: pdf.output('blob'), pages }
}
export async function materialPdf(data: MaterialData, answers: boolean): Promise<Blob> { return (await materialDocument(data, answers)).pdf }
export const materialFilename = (data: MaterialData, answers: boolean) => `${safeFilename(data.title)}${answers ? '-答案讲解' : '-学生练习'}.pdf`
export async function exportMaterial(data: MaterialData, answers: boolean) { downloadBlob(await materialPdf(data, answers), materialFilename(data, answers), 2000) }
export function materialMarkdown(data: MaterialData) { return `# ${data.title}\n\n${data.grade} · ${data.subject} · ${data.keyword}\n\n${data.instructions}\n\n` + data.questions.map((q, i) => `## ${i + 1}. ${q.stem}\n\n${q.options.map((o, n) => `${String.fromCharCode(65 + n)}. ${o}`).join('\n')}\n\n答案：${q.answer}\n\n讲解：${q.analysis}`).join('\n\n') }
export async function draftImages(data: DraftData): Promise<Blob[]> {
  if (!(data.cover_title || data.headline).trim()) throw new Error('请先填写封面主标题或发布标题')
  for (const [index, card] of data.cards.entries()) {
    if (!card.heading.trim() && !card.body.trim()) throw new Error(`第 ${index + 1} 张内页没有内容，请补充文字或删除空白内页`)
  }
  const theme = { green: ['#eef7f0', '#195d40'], orange: ['#fff5e6', '#8b4b17'], blue: ['#eef4ff', '#28558b'] }[data.theme]
  const pages = [{ heading: data.cover_title || data.headline, body: data.cover_subtitle }, ...data.cards]
  const blobs: Blob[] = []
  for (const [index, page] of pages.entries()) {
    const { value, ctx } = canvas(1080, 1440, theme[0])
    ctx.fillStyle = theme[1]!; ctx.font = 'bold 26px "Microsoft YaHei", sans-serif'; ctx.fillText(index ? '学习资料 · 使用指南' : '原创学习资料', 84, 85)
    let size = index ? 54 : 78, heading: string[] = [], body: string[] = []
    while (size >= 26) {
      ctx.font = `bold ${size}px "Microsoft YaHei", sans-serif`; heading = wrapCanvasText(ctx, page.heading, 900)
      ctx.font = `${Math.round(size * 0.62)}px "Microsoft YaHei", sans-serif`; body = wrapCanvasText(ctx, page.body, 900)
      if (heading.length * size * 1.45 + body.length * size * 0.95 < 1070) break
      size -= 2
    }
    if (size < 26) { value.width = 0; throw new Error(`第 ${index + 1} 张内容过多，请拆成更多内页后导出`) }
    let y = index ? 200 : 300
    ctx.font = `bold ${size}px "Microsoft YaHei", sans-serif`
    for (const line of heading) { ctx.fillText(line, 84, y); y += size * 1.45 }
    y += 36; ctx.font = `${Math.round(size * 0.62)}px "Microsoft YaHei", sans-serif`
    for (const line of body) { ctx.fillText(line, 84, y); y += size * 0.95 }
    if (y > 1340) { value.width = 0; throw new Error(`第 ${index + 1} 张内容超出页面，请缩短或拆页`) }
    ctx.font = '24px "Microsoft YaHei", sans-serif'; ctx.fillText(`${String(index + 1).padStart(2, '0')} / ${String(pages.length).padStart(2, '0')}`, 860, 1355)
    blobs.push(await png(value)); value.width = 0
  }
  return blobs
}
export function draftText(data: DraftData) { return `${data.headline}\n\n${data.body}\n\n${data.hashtags}` }
export async function exportDraft(data: DraftData) {
  if (!data.headline.trim() || !data.body.trim()) throw new Error('请先补全发布标题和正文，再导出发布素材')
  const { default: JSZip } = await import('jszip')
  const zip = new JSZip(); zip.file('笔记文案.txt', draftText(data))
  const images = await draftImages(data)
  for (const [index, blob] of images.entries()) zip.file(`${String(index + 1).padStart(2, '0')}-${index === 0 ? '封面' : '内页'}.png`, await blob.arrayBuffer())
  downloadBlob(await zip.generateAsync({ type: 'blob' }), `${safeFilename(data.title)}-发布素材.zip`, 2000)
}
