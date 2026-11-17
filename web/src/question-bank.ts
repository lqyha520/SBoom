import { request } from './api'
import { DEFAULT_LAYOUT, TYPE_NAME } from './constants'
import { MAX_PAPER_QUESTIONS, MAX_PAPER_SECTIONS } from './generation-limits'
import { deepClone, ensureQids, uid } from './utils'
import type { BankItem, BankPage } from '../../shared/teaching'
import type { Difficulty, PaperData, PaperSection, Question } from './types'

export const bankList = (params: Record<string, string | number>, signal?: AbortSignal) => request<BankPage>('/api/v1/question-bank?' + new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])), { signal })
export const bankSelect = (ids: string[], signal?: AbortSignal) => request<BankPage>('/api/v1/question-bank/selection', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }), signal })
export const bankRemove = (item: BankItem) => request<void>(`/api/v1/question-bank/${item.id}?revision=${item.revision}`, { method: 'DELETE' })
export const bankEdit = (item: BankItem, title: string, topic: string, difficulty: Difficulty) => request<BankItem>(`/api/v1/question-bank/${item.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision: item.revision, title, topic, difficulty }) })

export const bankQuestionCount = (items: BankItem[]) => items.reduce((count, item) => count + item.questions.length, 0)

export function bankSelectionIssue(items: BankItem[]): string {
  if (!items.length) return ''
  if (items.some(item => item.grade !== items[0].grade || item.subject !== items[0].subject)) return '请选择同一年级、同一学科的题目'
  if (bankQuestionCount(items) > Math.min(300, MAX_PAPER_QUESTIONS)) return '一次组卷最多 300 道题，请拆分试卷'
  if (items.length > 100) return '一次最多选择 100 条收藏，请先移除部分题目'
  const sections = items.filter(item => item.section_type === 'reading').length + new Set(items.filter(item => item.section_type !== 'reading').map(item => item.section_type)).size
  if (sections > MAX_PAPER_SECTIONS) return `一次组卷最多 ${MAX_PAPER_SECTIONS} 个大题，请拆分试卷`
  return ''
}

export function saveBankQuestion(grade: string, subject: string, topic: string, difficulty: Difficulty, section: { type: string; data?: { passage?: string; questions: Question[] } | null }, question: Question) {
  const reading = section.type === 'reading'
  const questions = reading ? section.data?.questions || [] : [question]
  if (!grade || !subject) throw new Error('请先选择年级和学科')
  if (questions.some(q => q._preview || q._replacement) || !questions.length) throw new Error('格式示例或正在替换的题目不能保存')
  const title = (reading ? topic || '阅读理解' : question.stem || [question.left_expr, question.right_expr].filter(Boolean).join(' ○ ') || [question.top, question.left, question.right].filter(v => v != null).join(' / ')).slice(0, 240)
  return request<BankItem>('/api/v1/question-bank', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: title || TYPE_NAME[section.type] || '习题', grade, subject, topic: topic.slice(0, 200), difficulty, section_type: section.type, passage: reading ? section.data?.passage || '' : '', questions }) })
}

export function assembleBankPaper(items: BankItem[], title: string): PaperData {
  if (!items.length) throw new Error('请先选择题目')
  const issue = bankSelectionIssue(items)
  if (issue) throw new Error(issue)
  const sections: PaperSection[] = []
  for (const item of items) {
    let section = item.section_type === 'reading' ? undefined : sections.find(s => s.type === item.section_type)
    if (!section) {
      section = { type: item.section_type, _sid: uid(), layout: { ...DEFAULT_LAYOUT }, data: { passage: item.passage || undefined, questions: [] } }
      sections.push(section)
    }
    // 每份组卷拥有独立对象和新题号，核对标记不会从旧试卷或题库继承。
    const questions = deepClone(item.questions) as Question[]
    questions.forEach(q => { delete q._manualReview; delete q._qid; q.quality_status = 'unchecked'; q.quality_issues = [] })
    section.data.questions.push(...questions)
    section.requestedCount = section.data.questions.length
    ensureQids(section.data)
  }
  if (sections.length > MAX_PAPER_SECTIONS || sections.reduce((n, s) => n + s.data.questions.length, 0) > Math.min(300, MAX_PAPER_QUESTIONS)) throw new Error('一次组卷最多 300 道题，请拆分试卷')
  return { grade: items[0].grade, subject: items[0].subject, keyword: [...new Set(items.map(i => i.topic).filter(Boolean))].join('、').slice(0, 100), title: title.trim() || '题库组卷', difficulty: items[0].difficulty, sections }
}
