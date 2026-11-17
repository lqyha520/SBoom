import { describe, expect, it } from 'vitest'
import { assembleBankPaper, bankQuestionCount, bankSelectionIssue } from '../question-bank'
import { paperQuality } from '../question-quality'
import type { BankItem } from '../../../shared/teaching'

function item(id: string, changes: Partial<BankItem> = {}): BankItem {
  return { id, title: '加法', grade: '小学一年级', subject: '数学', topic: '加法', difficulty: 'easy', section_type: 'oral_math', passage: '', revision: 1, created_at: 1, updated_at: 1,
    questions: [{ stem: '2 + 3 = __', answer: 5, analysis: '2 加 3 等于 5', quality_status: 'passed' }], ...changes }
}

describe('个人题库组卷', () => {
  it('按选题顺序合并普通题型，阅读文章独立保留，并重新进入核对流程', () => {
    const reading = item('reading', { section_type: 'reading', passage: '小明在读书。', questions: [{ stem: '谁在读书？', answer: '小明', analysis: '第一句' }] })
    const paper = assembleBankPaper([reading, item('first'), item('second')], '我的练习')
    expect(paper.title).toBe('我的练习')
    expect(paper.sections).toHaveLength(2)
    expect(paper.sections[0].data.passage).toBe(reading.passage)
    expect(paper.sections[1].data.questions).toHaveLength(2)
    expect(paper.sections[1].requestedCount).toBe(2)
    expect(paperQuality(paper).flatMap(section => section.questions)).toHaveLength(3)
  })
  it('新试卷不修改题库对象，题号和核对状态各自独立', () => {
    const original = item('question')
    const a = assembleBankPaper([original], ''), b = assembleBankPaper([original], '')
    a.sections[0].data.questions[0].stem = '修改新试卷'
    expect(original.questions[0].stem).toBe('2 + 3 = __')
    expect(b.sections[0].data.questions[0].stem).toBe('2 + 3 = __')
    expect(a.sections[0].data.questions[0]._qid).not.toBe(b.sections[0].data.questions[0]._qid)
    expect(original.questions[0].quality_status).toBe('passed')
  })
  it('阻止空选题、跨年级和超过题量上限的组卷', () => {
    expect(() => assembleBankPaper([], '')).toThrow('请先选择题目')
    expect(() => assembleBankPaper([item('a'), item('b', { grade: '小学二年级' })], '')).toThrow('同一年级')
    expect(() => assembleBankPaper(Array.from({ length: 301 }, (_, index) => item(String(index))), '')).toThrow('最多 300')
  })
  it('阅读收藏按实际小题计数，选题阶段提示学科、收藏条数和大题上限', () => {
    const reading = (id: string) => item(id, { section_type: 'reading', passage: '文章', questions: Array.from({ length: 30 }, () => ({ stem: '问题', answer: '答案' })) })
    const selected = Array.from({ length: 10 }, (_, index) => reading(String(index)))
    expect(bankQuestionCount(selected)).toBe(300)
    expect(bankSelectionIssue(selected)).toBe('')
    expect(bankSelectionIssue([...selected, item('extra')])).toContain('最多 300 道')
    expect(bankSelectionIssue([item('math'), item('chinese', { subject: '语文' })])).toContain('同一学科')
    expect(bankSelectionIssue(Array.from({ length: 101 }, (_, index) => item(String(index))))).toContain('100 条')
    expect(bankSelectionIssue(Array.from({ length: 61 }, (_, index) => item(String(index), { section_type: 'reading' })))).toContain('60 个大题')
  })
})
