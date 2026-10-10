import { describe, expect, it } from 'vitest'
import { previewSampleData } from '../preview-samples'

describe('preview format samples', () => {
  it.each([
    'quiz', 'fill_blank', 'true_false', 'match_pair', 'oral_math', 'vertical_calc',
    'recursive_calc', 'smart_calc', 'number_split', 'compare', 'word_problem', 'challenge', 'reading',
  ])('provides a sample for %s', type => {
    const data = previewSampleData(type, 4, 's1')
    expect(data.questions).toHaveLength(4)
    expect(data.questions.every(question => question._preview)).toBe(true)
    expect(data.questions.every(question => question._qid?.startsWith('preview-s1-'))).toBe(true)
  })

  it('preserves the visual fields needed by each special layout', () => {
    expect(previewSampleData('quiz', 1).questions[0].options).toHaveLength(4)
    expect(previewSampleData('fill_blank', 1).questions[0].stem).not.toContain('____')
    expect(previewSampleData('oral_math', 1).questions[0].stem).not.toContain('____')
    expect(previewSampleData('match_pair', 1).questions[0].left_items).toHaveLength(3)
    expect(previewSampleData('number_split', 1).questions[0]).toMatchObject({ top: 10, left: 6, right: 4 })
    expect(previewSampleData('compare', 1).questions[0]).toMatchObject({ left_expr: '3/4', right_expr: '2/3' })
    expect(previewSampleData('reading', 1).passage).toContain('春天')
  })

  it('limits samples and falls back to a normal question for unknown types', () => {
    expect(previewSampleData('fill_blank', 0).questions).toHaveLength(1)
    expect(previewSampleData('unknown', 20).questions).toHaveLength(20)
    expect(previewSampleData('unknown', 31).questions).toHaveLength(30)
    expect(previewSampleData('unknown', 1).questions[0].stem).toContain('请根据所学知识')
  })
})
