import { describe, expect, it } from 'vitest'
import { buildAnswerPaper } from '../exporter'
import { DEFAULT_LAYOUT } from '../constants'
import type { PaperData } from '../types'

describe('answer export contract', () => {
  const paper: PaperData = {
    grade: '小学三年级', subject: '数学', keyword: '加减法', title: 'Practice', titleHtml: '<b>Practice</b>', difficulty: 'medium',
    sections: [{ type: 'quiz', layout: { ...DEFAULT_LAYOUT }, data: { questions: [{ type: 'multiple_choice', stem: 'Question', options: ['<unsafe>', '2'], answer: 0, analysis: '<script>unsafe</script>', _qid: 'q-1' }] } }],
  }
  it('builds an answer-only paper without mutating the student paper', () => {
    const result = buildAnswerPaper(paper)
    const question = result.sections[0].data.questions[0]
    expect(result.title).toContain('参考答案')
    expect(result.titleHtml).toBeUndefined()
    expect(question.options).toBeUndefined()
    expect(question.type).toBe('fill_blank')
    expect(question._qid).toBe('ans_q-1')
    expect(paper.sections[0].data.questions[0].options).toEqual(['<unsafe>', '2'])
  })
  it('escapes answer and analysis text before rich-text rendering', () => {
    const html = buildAnswerPaper(paper).sections[0].data.questions[0]._stemHtml!
    expect(html).toContain('&lt;unsafe&gt;')
    expect(html).toContain('&lt;script&gt;')
    expect(html).not.toContain('<script>')
  })
})
