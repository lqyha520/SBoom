import { describe, expect, it } from 'vitest'
import { answerOf, spaceOps } from '../utils'
import type { Question } from '../types'

describe('spaceOps —— 算式运算符两侧补空格', () => {
  it('给漏空格的算式补空格', () => {
    expect(spaceOps('3+5=')).toBe('3 + 5 =')
    expect(spaceOps('5+____=9')).toBe('5 + ____ = 9')
    expect(spaceOps('9×7=')).toBe('9 × 7 =')
    expect(spaceOps('10÷2=5')).toBe('10 ÷ 2 = 5')
    expect(spaceOps('9-1')).toBe('9 - 1')
    expect(spaceOps('128+72×3=')).toBe('128 + 72 × 3 =')
  })

  it('已经带空格的算式保持不变（幂等）', () => {
    for (const s of ['3 + 5 =', '25 + 38 =', '5 + ____ = 9', '128 + 72 × 3 =']) {
      expect(spaceOps(s)).toBe(s)
      expect(spaceOps(spaceOps(s))).toBe(s)
    }
  })

  it('一元负号不拆成二元', () => {
    expect(spaceOps('-3+5=2')).toBe('-3 + 5 = 2')
    expect(spaceOps('7=-3+10')).toBe('7 = -3 + 10')
    expect(spaceOps('0-5=')).toBe('0 - 5 =')
  })

  it('含汉字的文本一律不动（题干描述 / 解析）', () => {
    expect(spaceOps('在横线上填 >、< 或 =。')).toBe('在横线上填 >、< 或 =。')
    expect(spaceOps('小明有 3 个苹果，吃了 1 个')).toBe('小明有 3 个苹果，吃了 1 个')
    expect(spaceOps('5+2=7，7小于8')).toBe('5+2=7，7小于8')
  })

  it('含 HTML 标签的富文本一律不动（属性里的 - 不能被碰）', () => {
    const html = '<b style="color:#c0392b;font-size:9.5pt">3+5=</b>'
    expect(spaceOps(html)).toBe(html)
  })

  it('空值安全', () => {
    expect(spaceOps('')).toBe('')
    expect(spaceOps(null)).toBe('')
    expect(spaceOps(undefined)).toBe('')
    expect(spaceOps('25')).toBe('25')
  })
})

describe('answerOf —— 答案卷里的算式也带空格', () => {
  it('比大小答案', () => {
    const q: Question = { type: 'compare', left_expr: '5+2', right_expr: '8', answer: '<' }
    expect(answerOf(q)).toBe('5 + 2 ○ 8 → <')
  })

  it('数是分成答案不受影响', () => {
    const q: Question = { type: 'number_split', top: 9, left: 5, right: '__', answer: 4 }
    expect(answerOf(q)).toBe('9 分成 5 和 4')
  })

  it('计算类答案里的算式也补空格', () => {
    const q: Question = { type: 'oral_math', stem: '3+5=', answer: '3+5=8' }
    expect(answerOf(q)).toBe('3 + 5 = 8')
  })
})
