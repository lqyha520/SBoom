import { describe, expect, it } from 'vitest'
import { confirmQuestionReview, invalidateQuestionReview, isManuallyReviewed, paperQuality, questionConcerns, questionKey } from '../question-quality'
import { DEFAULT_LAYOUT } from '../constants'
import type { PaperData, Question } from '../types'

const reviewed = (stem = '8 × 2 ='): Question => ({ type: 'oral_math', stem, answer: 16, analysis: '8×2=16', quality_status: 'passed' })

describe('整卷质量提示', () => {
  it('人工确认独立于模型状态，内容和正文变化后不再有效', () => {
    const question: Question = { ...reviewed(), quality_status: 'needs_review', quality_issues: ['请检查单位'] }
    confirmQuestionReview(question, '原文')
    expect(question.quality_status).toBe('needs_review')
    expect(question.quality_issues).toEqual(['请检查单位'])
    expect(questionConcerns(question, '原文')).toEqual([])
    expect(isManuallyReviewed(JSON.parse(JSON.stringify(question)), '原文')).toBe(true)
    expect(questionConcerns(question, '改过的原文')).toContain('题目或阅读正文已变化，请重新核对')
    for (const change of [{ stem: '新题干' }, { answer: 18 }, { analysis: '新解析' }, { options: ['新选项'] }, { acceptable_answers: ['其他答案'] }]) {
      expect(isManuallyReviewed({ ...question, ...change }, '原文')).toBe(false)
    }
    question._locked = true; question._stemHtml = '<b>8 × 2 =</b>'
    expect(isManuallyReviewed(question, '原文')).toBe(true)
    invalidateQuestionReview(question)
    expect(question._manualReview).toBeUndefined()
    expect(questionConcerns(question)).toContain('题目内容已修改，请重新核对答案与解析')
  })

  it('缺少答案或解析不能确认，零值答案有效', () => {
    for (const answer of [undefined, '', []]) {
      expect(() => confirmQuestionReview({ ...reviewed(), answer })).toThrow('请先填写答案')
    }
    expect(() => confirmQuestionReview({ ...reviewed(), analysis: ' ' })).toThrow('请先补充解析')
    const question = { ...reviewed('8-8='), answer: 0, analysis: '8-8=0' }
    confirmQuestionReview(question)
    expect(isManuallyReviewed(question)).toBe(true)
  })

  it('人工确认消除已处理告警，但不隐藏同卷重复和缺题', () => {
    const question = { ...reviewed(), quality_status: 'unchecked' as const }
    confirmQuestionReview(question)
    const section = { _sid: 'reviewed', type: 'oral_math', layout: { ...DEFAULT_LAYOUT }, warn: '独立复核未完成',
      data: { questions: [question], quality_warnings: ['独立复核未完成'] } }
    const paper: PaperData = { grade: '小学三年级', subject: '数学', keyword: '乘法', title: '检查', difficulty: 'medium', sections: [section] }
    expect(paperQuality(paper)[0]).toMatchObject({ warning: '', questions: [], missing: 0 })
    expect(section.warn).toBe('独立复核未完成')
    paper.sections.push({ ...section, _sid: 'duplicate', data: { questions: [{ ...question }], missing_count: 2 } })
    expect(paperQuality(paper)[1]).toMatchObject({ missing: 2, questions: [{ issues: ['与本卷前面的题目完全重复'] }] })
  })

  it('旧题、缺少解析和复核失败不能显示通过', () => {
    expect(questionConcerns(reviewed())).toEqual([])
    expect(questionConcerns({ ...reviewed(), quality_status: undefined })).toContain('尚未完成独立复核')
    expect(questionConcerns({ ...reviewed(), analysis: '' })).toContain('缺少解析，请核对解题依据')
    expect(questionConcerns({ ...reviewed(), quality_status: 'unchecked', quality_issues: ['独立复核未完成'] })).toEqual(['独立复核未完成'])
  })

  it('不同正文不重复，同卷跨大题重复和缺题均可定位', () => {
    const section = (id: string, questions: Question[], passage = '') => ({
      _sid: id, type: 'oral_math', layout: { ...DEFAULT_LAYOUT }, data: { questions, passage },
    })
    const paper: PaperData = { grade: '小学三年级', subject: '数学', keyword: '乘法', title: '检查', difficulty: 'medium',
      sections: [section('first', [reviewed()]), section('second', [reviewed('８*２＝')]),
        section('passage', [reviewed()], '不同文章'), { ...section('missing', []), data: { questions: [], missing_count: 2 } }] }
    const quality = paperQuality(paper)
    expect(quality[0].questions).toEqual([])
    expect(quality[1]).toMatchObject({ sectionId: 'second', questions: [{ index: 0, issues: ['与本卷前面的题目完全重复'] }] })
    expect(quality[2].questions).toEqual([])
    expect(quality[3].missing).toBe(2)
    expect(paperQuality({ ...paper, sections: [paper.sections[1]] })[0].questions).toEqual([])
  })

  it('保留数学上下标、英文词间空格和大小写的含义', () => {
    for (const [first, second] of [['2²=___', '22=___'], ['a long', 'along'], ['US', 'us']]) {
      expect(questionKey({ stem: first })).not.toBe(questionKey({ stem: second }))
    }
    expect(questionKey(reviewed())).toBe(questionKey(reviewed('８*２＝')))
    expect(questionKey(reviewed())).not.toBe(questionKey(reviewed('2×8=')))
  })
})
