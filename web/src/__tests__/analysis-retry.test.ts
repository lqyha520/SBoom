import { describe, expect, it } from 'vitest'
import { applyAnalysis } from '../analysis-retry'
import type { Question } from '../types'
const original: Question = { _qid: 'q1', stem: '2 + 3 =', answer: 5, analysis: '', quality_status: 'unchecked' }
const reviewed: Question = { ...original, analysis: '2 + 3 = 5', quality_status: 'passed' }
describe('补全解析保留人工修改', () => {
  it('只更新原题的解析和复核结论', () => {
    const target = { ...original }
    expect(applyAnalysis(target, original, reviewed)).toBe(true)
    expect(target).toEqual({ ...reviewed, quality_issues: [] })
  })
  it.each([{ stem: '3 + 3 =' }, { answer: 6 }, { _locked: true }, { _manualReview: 'confirmed' }, { _stemHtml: '<b>2 + 3</b>' }, { _qid: 'q2' }])('保留变动 %j', patch => {
    const target = { ...original, ...patch }, before = { ...target }
    expect(applyAnalysis(target, original, reviewed)).toBe(false)
    expect(target).toEqual(before)
  })
})
