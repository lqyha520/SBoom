import { expect, it } from 'vitest'
import JSZip from 'jszip'
import { createWord, richRuns } from '../word-export'
import { DEFAULT_LAYOUT, TEMPLATES } from '../constants'
import type { PaperData, PaperStyle } from '../types'

const style: PaperStyle = { bg: 'none', bgOpacity: 0, banner: false, secColor: false, frame: 'none', encourage: false, reward: false, kidFont: 'off', exportBg: false, titleScale: 1, titleOffsetY: 0 }
const paper: PaperData = { title: '单元练习', grade: '小学三年级', subject: '数学', keyword: '综合练习', difficulty: 'medium', day: 2, sections: [
  { type: 'quiz', layout: { ...DEFAULT_LAYOUT, qCols: 1, optCols: 2 }, data: { questions: [{ stem: '哪个字母在前？', options: ['A. 甲', 'B. 乙'], _optsHtml: ['<b>A. 甲</b>', '<i>乙</i>'], answer: 0, analysis: '解析只属于答案页' }] } },
  { type: 'oral_math', layout: { ...DEFAULT_LAYOUT, qCols: 2 }, data: { questions: [{ stem: '1−1=', answer: 0, analysis: '相同的数相减得零' }, { stem: '2²=', _stemHtml: '2<sup>2</sup> =', answer: 4 }] } },
  { type: 'number_split', layout: { ...DEFAULT_LAYOUT }, data: { questions: [{ top: 8, left: 3, right: '', answer: 5 }] } },
  { type: 'compare', layout: { ...DEFAULT_LAYOUT }, data: { questions: [{ left_expr: '2+3', right_expr: '8−4', answer: '>' }] } },
  { type: 'match_pair', layout: { ...DEFAULT_LAYOUT }, data: { questions: [{ stem: '连一连', left_items: ['太阳', '月亮'], right_items: ['夜晚', '白天'], answer: [[0, 1], [1, 0]] }] } },
  { type: 'reading', layout: { ...DEFAULT_LAYOUT }, data: { passage: '小雨走进图书馆。\n她找到了一本书。', questions: [{ stem: '小雨去了哪里？', answer: '图书馆', analysis: '依据第一句话' }] } },
] }
async function contents(mode: 'student' | 'withAnswers' | 'answersOnly', value = paper) {
  const file = await createWord([value], TEMPLATES[0], style, { mode, addDay: true })
  const zip = await JSZip.loadAsync(await file.arrayBuffer())
  const xml = await zip.file('word/document.xml')!.async('string')
  const doc = new DOMParser().parseFromString(xml, 'application/xml')
  expect(doc.querySelector('parsererror')).toBeNull()
  const text = Array.from(doc.getElementsByTagName('w:t')).map(node => node.textContent).join(' ')
  return { zip, xml, text }
}

it('导出真实 Word 文本与表格，学生卷保留所有题型且没有答案解析', async () => {
  const { zip, xml, text } = await contents('student')
  expect(zip.file('[Content_Types].xml')).toBeTruthy()
  expect(Object.keys(zip.files).some(name => name.includes('media/'))).toBe(false)
  for (const value of ['单元练习', '第2天', '8 分成 3 和 （　　）', '2 + 3 ○ 8 − 4', '小雨走进图书馆。', '夜晚']) expect(text).toContain(value)
  expect(text).not.toContain('参考答案'); expect(text).not.toContain('解析只属于答案页')
  expect(text).not.toContain('A. A.'); expect(text).not.toContain('B. B.')
  expect(xml).toContain('<w:tbl>'); expect(xml).toContain('superscript')
  expect(xml).not.toContain('<w:drawing>')
})
it('答案另起一页，保留零值、选项答案、连线关系与解析', async () => {
  const { text, xml } = await contents('withAnswers')
  for (const value of ['参考答案', '1. 0', 'A（甲）', '（1）→（2）', '8 分成 3 和 5', '解析：依据第一句话']) expect(text).toContain(value)
  expect(xml).toContain('<w:br w:type="page"/>')
  const answers = await contents('answersOnly')
  expect(answers.text).not.toContain('小雨走进图书馆。')
  expect(answers.text).toContain('图书馆')
})
it('隐藏卷头页脚与批量顺序生效；导出不改写原始题目', async () => {
  const source = JSON.stringify(paper)
  const hidden = await contents('student', { ...paper, hiddenElements: ['banner', 'footer'] })
  expect(hidden.text).not.toContain('单元练习')
  const blob = await createWord([paper, { ...paper, title: '第二套' }], TEMPLATES[0], style, { mode: 'student' })
  const zip = await JSZip.loadAsync(await blob.arrayBuffer())
  const xml = await zip.file('word/document.xml')!.async('string')
  expect(xml.indexOf('单元练习')).toBeLessThan(xml.indexOf('第二套'))
  expect(JSON.stringify(paper)).toBe(source)
})
it('富文本净化后输出，保留上下标和换行，不产生外链或可执行内容', () => {
  const xml = richRuns('<b>粗体</b><br><sub>2</sub><script>secret()</script><img src="https://bad.test">&lt;安全&gt;', '')
  expect(xml).toContain('<w:b/>'); expect(xml).toContain('<w:br/>'); expect(xml).toContain('subscript')
  expect(xml).toContain('&lt;安全&gt;'); expect(xml).not.toMatch(/secret|bad.test|<script|drawing/)
})
it('取消与过量导出会停止，不产生残缺文件', async () => {
  const controller = new AbortController(); controller.abort()
  await expect(createWord([paper], TEMPLATES[0], style, { mode: 'student', signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
  await expect(createWord([], TEMPLATES[0], style, { mode: 'student' })).rejects.toThrow('1 至 100')
})
