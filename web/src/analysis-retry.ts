import type { Question } from './types'

function snapshot(question: Question): string {
  return JSON.stringify(Object.fromEntries(Object.entries(question).filter(([key]) => !key.startsWith('_')).sort(([a], [b]) => a.localeCompare(b))))
}

/** 仅替换未编辑、未锁定、未人工确认的同一道题的解析及复核结论。 */
export function applyAnalysis(target: Question, original: Question, reviewed: Question): boolean {
  if (!target._qid || target._qid !== original._qid || target._locked || target._manualReview
    || target._stemHtml || target._optsHtml || snapshot(target) !== snapshot(original)) return false
  target.analysis = reviewed.analysis
  target.quality_status = reviewed.quality_status
  target.quality_issues = reviewed.quality_issues ? [...reviewed.quality_issues] : []
  return true
}
