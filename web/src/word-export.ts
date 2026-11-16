/** 将结构化试卷写成可编辑的 WordprocessingML；复用 JSZip，不依赖截图或在线转换。 */
import type { PaperData, PaperSection, PaperStyle, PaperTemplate, Question } from './types'
import { answerOf, computeScores, gradeNumOf, isBlankVal, secTitle, spaceOps, stripOptPrefix, tfStem } from './utils'
import { DIFF_NAME } from './constants'
import { downloadBlob } from '../../shared/download'

export type WordMode = 'student' | 'withAnswers' | 'answersOnly'
export interface WordOptions { mode: WordMode; addDay?: boolean; signal?: AbortSignal }
const NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
const XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
const PAGE_WIDTH = 9638 // A4，左右各 20 mm
const MAX_BYTES = 8 * 1024 * 1024

function xml(value: unknown): string {
  return String(value ?? '').replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFE\uFFFF]/g, '')
    .replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' }[char]!))
}
function run(text: unknown, properties = ''): string {
  return String(text ?? '').split(/\r?\n/).map((part, index) => `${index ? '<w:r><w:br/></w:r>' : ''}<w:r>${properties ? `<w:rPr>${properties}</w:rPr>` : ''}<w:t xml:space="preserve">${xml(part)}</w:t></w:r>`).join('')
}
function paragraph(content: string, properties = ''): string {
  return `<w:p><w:pPr>${properties}<w:spacing w:after="120" w:line="300" w:lineRule="auto"/><w:widowControl/></w:pPr>${content}</w:p>`
}
function fontSize(value: string, fallback: number): number {
  const match = value.match(/^(\d+(?:\.\d+)?)(pt|px)$/)
  return match ? Math.max(16, Math.min(72, Math.round(Number(match[1]) * (match[2] === 'px' ? 1.5 : 2)))) : fallback
}

function richRoot(html: string): HTMLElement {
  // 没有浏览上下文的惰性文档；只提取文字和白名单样式，不把任何 HTML 放入页面或文件。
  const root = document.implementation.createHTMLDocument('').body
  root.innerHTML = html
  root.querySelectorAll('script,style,iframe,object,embed,template,svg,.sort-handle,.el-del').forEach(node => node.remove())
  return root
}
/** 保留教师编辑的加粗、斜体、下划线、颜色、字号和上下标；所有文字逐项 XML 转义。 */
export function richRuns(html: string | undefined, fallback: string, size = 24): string {
  if (!html) return run(fallback, `<w:sz w:val="${size}"/>`)
  const root = richRoot(html)
  const visit = (node: Node, inherited: Record<string, string> = {}): string => {
    if (node.nodeType === Node.TEXT_NODE) return run(node.textContent, Object.values(inherited).join(''))
    if (!(node instanceof HTMLElement)) return ''
    const tag = node.tagName.toLowerCase()
    if (tag === 'br') return '<w:r><w:br/></w:r>'
    const props = { ...inherited }
    if (['b', 'strong'].includes(tag) || ['bold', '700', '800', '900'].includes(node.style.fontWeight)) props.bold = '<w:b/>'
    if (['i', 'em'].includes(tag) || node.style.fontStyle === 'italic') props.italic = '<w:i/>'
    if (tag === 'u' || node.style.textDecoration.includes('underline')) props.underline = '<w:u w:val="single"/>'
    if (tag === 's' || node.style.textDecoration.includes('line-through')) props.strike = '<w:strike/>'
    if (tag === 'sub' || tag === 'sup') props.position = `<w:vertAlign w:val="${tag === 'sub' ? 'subscript' : 'superscript'}"/>`
    if (node.style.fontSize) props.size = `<w:sz w:val="${fontSize(node.style.fontSize, size)}"/>`
    if (tag === 'font' && node.getAttribute('size')) props.size = `<w:sz w:val="${[16, 20, 24, 28, 36, 48, 72][Math.max(0, Math.min(6, Number(node.getAttribute('size')) - 1))] || size}"/>`
    const color = node.style.color || node.getAttribute('color') || ''
    const rgb = color.match(/^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/)
    if (rgb) props.color = `<w:color w:val="${rgb.slice(1).map(n => Math.min(255, Number(n)).toString(16).padStart(2, '0')).join('')}"/>`
    else if (/^#[0-9a-f]{6}$/i.test(color)) props.color = `<w:color w:val="${color.slice(1)}"/>`
    const content = Array.from(node.childNodes).map(child => visit(child, props)).join('')
    const prefix = tag === 'li' ? run(node.parentElement?.tagName.toLowerCase() === 'ol' ? `${Array.from(node.parentElement.children).indexOf(node) + 1}. ` : '• ') : ''
    return prefix + content + (['td', 'th'].includes(tag) && node.nextSibling ? '<w:r><w:tab/></w:r>' : '') + (['p', 'div', 'li', 'tr'].includes(tag) && node !== root && node.nextSibling ? '<w:r><w:br/></w:r>' : '')
  }
  return visit(root, { size: `<w:sz w:val="${size}"/>` }) || run(fallback)
}

function table(rows: string[][], columns: number, border: 'none' | 'solid' | 'dashed' = 'none', width = PAGE_WIDTH): string {
  const cellWidth = Math.floor(width / columns)
  const edges = ['top', 'left', 'bottom', 'right', 'insideH', 'insideV'].map(side => `<w:${side} w:val="${border === 'none' ? 'nil' : border === 'solid' ? 'single' : 'dashed'}" w:sz="4" w:color="808080"/>`).join('')
  return `<w:tbl><w:tblPr><w:tblW w:w="${width}" w:type="dxa"/><w:tblBorders>${edges}</w:tblBorders><w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="80" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>${Array.from({ length: columns }, () => `<w:gridCol w:w="${cellWidth}"/>`).join('')}</w:tblGrid>${rows.map(row => `<w:tr>${Array.from({ length: columns }, (_, index) => `<w:tc><w:tcPr><w:tcW w:w="${cellWidth}" w:type="dxa"/><w:vAlign w:val="top"/></w:tcPr>${row[index] || '<w:p/>'}${row[index]?.endsWith('</w:tbl>') ? '<w:p/>' : ''}</w:tc>`).join('')}</w:tr>`).join('')}</w:tbl>`
}

function questionBody(q: Question, index: number, section: PaperSection, size: number, width: number): string {
  const label = section.layout.showNo === false ? '' : `${index + 1}. `
  let content = ''
  if (q.top != null) {
    const value = (part: unknown) => isBlankVal(part) ? '（　　）' : String(part)
    content = paragraph(run(`${label}${value(q.top)} 分成 ${value(q.left)} 和 ${value(q.right)}`, `<w:sz w:val="${size}"/>`))
  } else if (q.left_expr != null) {
    content = paragraph(run(`${label}${spaceOps(q.left_expr)} ○ ${spaceOps(q.right_expr)}`, `<w:sz w:val="${size}"/>`))
  } else {
    const stem = q.type === 'true_false' || section.type === 'true_false' ? tfStem(q.stem || '') : spaceOps(q.stem)
    content = paragraph(run(label) + richRuns(q._stemHtml, stem, size))
    if (q.options?.length) {
      // 编辑器的选项富文本可能已经带 A. 前缀，避免重复编号。
      const options = q.options.map((option, i) => {
        const html = q._optsHtml?.[i]
        const text = html ? richRoot(html).textContent || '' : ''
        const hasLabel = new RegExp(`^\\s*${String.fromCharCode(65 + i)}[.．、:：)）]`).test(text)
        return paragraph((hasLabel ? '' : run(`${String.fromCharCode(65 + i)}. `)) + richRuns(html, spaceOps(stripOptPrefix(option)), size))
      })
      const cols = Math.max(1, Math.min(4, section.layout.optCols || 1))
      const rows = Array.from({ length: Math.ceil(options.length / cols) }, (_, i) => options.slice(i * cols, (i + 1) * cols))
      content += cols > 1 ? table(rows, cols, 'none', width) + '<w:p/>' : options.join('')
    } else if (q.left_items) {
      const left = q.left_items, right = q.right_items || []
      content += table(Array.from({ length: Math.max(left.length, right.length) }, (_, i) => [
        paragraph(run(left[i] == null ? '' : `（${i + 1}）${left[i]}`)), paragraph(run(right[i] == null ? '' : `（${i + 1}）${right[i]}`)),
      ]), 2, 'none', width) + '<w:p/>'
    }
    if (q.type === 'word_problem' || section.type === 'word_problem') {
      const lines = Math.max(0, Math.min(10, section.layout.answerLines ?? 3))
      content += Array.from({ length: lines }, () => '<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="454" w:lineRule="exact"/></w:pPr></w:p>').join('')
    }
  }
  return content
}

function paperBody(paper: PaperData, template: PaperTemplate, style: PaperStyle, options: WordOptions, answers: boolean): string {
  const hidden = new Set(paper.hiddenElements || [])
  const title = paper.title || (template.titlePrefix ? `${template.titlePrefix} · ${paper.grade}${paper.subject}${template.titleSuffix || ''}` : `${paper.grade}${paper.subject}${template.titleSuffix || '测试卷'}`)
  const size = style.kidFont === 'on' || style.kidFont === 'auto' && gradeNumOf(paper.grade) <= 2 ? 30 : 24
  const titleText = title + (options.addDay && paper.day ? `（第${paper.day}天）` : '') + (answers ? ' · 参考答案' : '')
  let content = ''
  if (answers || !hidden.has('banner') && !hidden.has('title')) {
    content += paragraph(answers ? run(titleText) : richRuns(paper.titleHtml, title, Math.round(44 * (style.titleScale || 1))) + run(options.addDay && paper.day ? `（第${paper.day}天）` : ''), '<w:pStyle w:val="Title"/><w:jc w:val="center"/><w:keepNext/>')
  }
  if (!answers && !hidden.has('banner')) {
    if (!hidden.has('subline')) content += paragraph(run([template.headerExtra, '范围：' + paper.keyword, '难度：' + (DIFF_NAME[paper.difficulty as keyof typeof DIFF_NAME] || paper.difficulty), template.showScore ? '满分 100 分' : ''].filter(Boolean).join(' ｜ ')), '<w:jc w:val="center"/>')
    if (template.showInfoRow && !hidden.has('inforow')) content += paragraph(run('姓名：____________　班级：____________　学号：________　得分：________'))
  }
  if (!answers && template.showNotice && !hidden.has('notice')) content += paragraph(run('注意事项：① 答题前请将姓名、班级填写清楚；② 选择题答案填入答题卡；③ 保持卷面整洁，字迹工整。'))
  const scores = computeScores(paper.sections)
  paper.sections.forEach((section, si) => {
    const questions = section.data.questions
    const score = !answers && template.showScore ? `（共 ${questions.reduce((sum, q) => sum + (scores.get(q) || 0), 0)} 分）` : ''
    content += paragraph(run(secTitle(section.type, si, section.name) + score), '<w:pStyle w:val="Heading1"/><w:keepNext/>')
    if (answers) {
      questions.forEach((q, index) => {
        content += paragraph(run(`${index + 1}. ${answerOf(q)}`, '<w:b/>'))
        if (q.analysis) content += paragraph(run(`解析：${q.analysis}`))
      })
    } else {
      if (section.data.passage) content += paragraph(run(section.data.passage, `<w:sz w:val="${size}"/>`))
      const cols = Math.max(1, Math.min(4, section.layout.qCols || 1))
      const items = questions.map((q, index) => questionBody(q, index, section, fontSize(section.layout.fontSize, size), Math.floor(PAGE_WIDTH / cols) - 200))
      const rows = Array.from({ length: Math.ceil(items.length / cols) }, (_, i) => items.slice(i * cols, (i + 1) * cols))
      content += cols > 1 || section.layout.tableBorder !== 'none' ? table(rows, cols, section.layout.tableBorder) + '<w:p/>' : items.join('')
    }
  })
  if (!answers && style.reward && !hidden.has('reward')) content += paragraph(run('今天的表现：☆ ☆ ☆'))
  if (!answers && !hidden.has('footer')) content += paragraph(run(paper.footerOverride ?? template.footer), '<w:jc w:val="center"/>')
  return content
}

export async function createWord(papers: PaperData[], template: PaperTemplate, style: PaperStyle, options: WordOptions): Promise<Blob> {
  options.signal?.throwIfAborted()
  if (!papers.length || papers.length > 100 || papers.reduce((n, p) => n + p.sections.reduce((s, x) => s + x.data.questions.length, 0), 0) > 15000) throw new Error('请每次选择 1 至 100 份试卷，合计不超过 15000 道题')
  if (new TextEncoder().encode(JSON.stringify(papers)).length > MAX_BYTES) throw new Error('试卷内容过大，请减少导出数量')
  const { default: JSZip } = await import('jszip')
  const bodies: string[] = []
  for (const paper of papers) {
    options.signal?.throwIfAborted()
    if (options.mode !== 'answersOnly') bodies.push(paperBody(paper, template, style, options, false))
    if (options.mode !== 'student') bodies.push(paperBody(paper, template, style, options, true))
    await new Promise(resolve => setTimeout(resolve, 0))
  }
  const content = bodies.join('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
  if (new TextEncoder().encode(content).length > 32 * 1024 * 1024) throw new Error('Word 内容超过容量上限，请分批导出')
  const zip = new JSZip()
  zip.file('[Content_Types].xml', XML + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
  zip.file('_rels/.rels', XML + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
  zip.file('word/_rels/document.xml.rels', XML + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
  zip.file('word/styles.xml', XML + `<w:styles xmlns:w="${NS}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="宋体"/><w:color w:val="000000"/><w:sz w:val="24"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN"/></w:rPr></w:rPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="44"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style></w:styles>`)
  zip.file('word/document.xml', XML + `<w:document xmlns:w="${NS}"><w:body>${content}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr></w:body></w:document>`)
  const result = await zip.generateAsync({ type: 'blob', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', compression: 'DEFLATE' }, () => options.signal?.throwIfAborted())
  options.signal?.throwIfAborted()
  return result
}

export async function exportWord(papers: PaperData[], template: PaperTemplate, style: PaperStyle, options: WordOptions): Promise<void> {
  const blob = await createWord(papers, template, style, options)
  options.signal?.throwIfAborted()
  const name = (papers[0]?.title || '练习卷').replace(/[\\/:*?"<>|\u0000-\u001F]/g, '_').trim().slice(0, 100) || '练习卷'
  downloadBlob(blob, `${name}${papers.length > 1 ? '-合集' : ''}${options.mode === 'student' ? '-学生卷' : options.mode === 'answersOnly' ? '-答案与解析' : '-试卷与答案'}.docx`)
}
