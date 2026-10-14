import type { PaperData, Question } from './types'

export function invalidateQuestionReview(question: Question) {
  delete question._manualReview
  question.quality_status = 'needs_review'
  question.quality_issues = ['题目内容已修改，请重新核对答案与解析']
}

function reviewContent(question: Question, passage: string) {
  const fields = ['type', 'stem', 'options', 'answer', 'acceptable_answers', 'analysis', 'left_items', 'right_items', 'top', 'left', 'right', 'left_expr', 'right_expr'] as const
  return JSON.stringify([passage, fields.map(field => question[field] ?? null)])
}

export function isManuallyReviewed(question: Question, passage = ''): boolean {
  return !!question._manualReview && question._manualReview === reviewContent(question, passage)
}

export function confirmQuestionReview(question: Question, passage = '') {
  if (question.answer == null || String(question.answer).trim() === '') throw new Error('请先填写答案')
  if (!question.analysis?.trim()) throw new Error('请先补充解析，再确认核对结果')
  question._manualReview = reviewContent(question, passage)
}

export function reviewText(value: unknown): string {
  return String(value ?? '').replace(/[！-～]/g, char => String.fromCharCode(char.charCodeAt(0) - 0xfee0))
    .replace(/[−×÷]/g, char => ({ '−': '-', '×': '*', '÷': '/' })[char]!)
    .replace(/\[/g, '(').replace(/\]/g, ')').replace(/\s+/g, ' ').trim()
    .replace(/\s*([+*/=<>≤≥≠-])\s*/g, '$1')
}

export function questionKey(question: Question, passage = ''): string {
  const fields = ['type', 'stem', 'options', 'left_items', 'right_items', 'top', 'left', 'right', 'left_expr', 'right_expr'] as const
  const normalize = (value: unknown): unknown => Array.isArray(value) ? value.map(normalize) : reviewText(value)
  return JSON.stringify([normalize(passage), fields.map(field => normalize(question[field]))])
}

export function questionConcerns(question: Question, passage = ''): string[] {
  const manual = isManuallyReviewed(question, passage)
  const issues = manual ? [] : [...(question.quality_issues || [])]
  if (question._manualReview && !manual) issues.push('题目或阅读正文已变化，请重新核对')
  if (!manual && question.quality_status !== 'passed' && !issues.length) issues.push('尚未完成独立复核')
  if (!question.analysis?.trim()) issues.push('缺少解析，请核对解题依据')
  return [...new Set(issues)]
}

export function paperQuality(paper: PaperData) {
  const seen = new Set<string>()
  return paper.sections.map((section, sectionIndex) => {
    const questions = section.data.questions.flatMap((question, index) => {
      const issues = questionConcerns(question, section.data.passage)
      const key = questionKey(question, section.data.passage)
      if (seen.has(key)) issues.push('与本卷前面的题目完全重复')
      seen.add(key)
      return issues.length ? [{ index, issues }] : []
    })
    const missing = section.data.missing_count || 0
    return { sectionIndex, sectionId: section._sid || String(sectionIndex), questions, missing,
      // 已处理的生成期告警保留在原数据中，不再当作当前待办。
      warning: questions.length || missing || !section.data.questions.length ? section.warn || '' : '' }
  })
}
