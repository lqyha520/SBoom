import { describe, expect, it } from 'vitest'
import {
  advanceFraction, answerFraction, fractionDifficulties, fractionLabel, fractionPrompt,
  fractionReading, fractionStars, fractionValue, gcd, newFraction, restartFraction,
  restoreFraction, switchFractionDifficulty, FRACTION_QUESTIONS, type FractionDifficulty,
  type FractionSave,
} from '../games/fraction-pizza'

function seeded(seed: number) {
  return () => {
    seed = (seed + 0x6D2B79F5) >>> 0
    let value = seed
    value = Math.imul(value ^ (value >>> 15), value | 1)
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61)
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296
  }
}
const copy = (save: FractionSave): FractionSave => JSON.parse(JSON.stringify(save))
const simplify = (numerator: number, denominator: number) => {
  const divisor = gcd(numerator, denominator)
  return fractionLabel(numerator / divisor, denominator / divisor)
}
const difficulties: FractionDifficulty[] = ['starter', 'explorer', 'master']

describe('披萨分数', () => {
  it('分数工具函数读法正确', () => {
    expect(gcd(12, 18)).toBe(6)
    expect(gcd(7, 9)).toBe(1)
    expect(fractionValue('3/4')).toBe(.75)
    expect(fractionReading('3/4')).toBe('四分之三')
    expect(fractionReading('1/2')).toBe('二分之一')
    expect(fractionReading('10/12')).toBe('十二分之十')
    expect(fractionPrompt('identify')).toContain('几分之几')
    expect(fractionPrompt('simplify')).toContain('最简分数')
  })

  it.each(difficulties)('%s 难度生成合法题目，选项里只有一个等值分数', difficulty => {
    for (let seed = 1; seed <= 12; seed++) {
      const flight = newFraction(difficulty, seeded(seed)).flight
      expect(flight.questions).toHaveLength(FRACTION_QUESTIONS)
      expect(new Set(flight.questions.map(question => `${question.mode}:${question.shaded}/${question.total}`)).size).toBe(FRACTION_QUESTIONS)
      for (const question of flight.questions) {
        expect(question.total).toBeGreaterThanOrEqual(2)
        expect(question.total).toBeLessThanOrEqual(12)
        expect(question.shaded).toBeGreaterThanOrEqual(1)
        expect(question.shaded).toBeLessThan(question.total)
        const raw = fractionLabel(question.shaded, question.total)
        if (difficulty === 'starter') {
          expect(question.mode).toBe('identify')
          expect(question.total).toBeLessThanOrEqual(5)
        }
        if (difficulty === 'explorer') expect(question.total).toBeLessThanOrEqual(8)
        if (difficulty === 'master') {
          expect(question.mode).toBe('simplify')
          expect([4, 6, 8, 9, 10, 12]).toContain(question.total)
          expect(gcd(question.shaded, question.total)).toBeGreaterThan(1)
          expect(question.answer).toBe(simplify(question.shaded, question.total))
          expect(question.answer).not.toBe(raw)
        } else if (question.mode === 'identify') {
          expect(question.answer).toBe(raw)
        } else {
          expect(question.answer).toBe(simplify(question.shaded, question.total))
          expect(question.answer).not.toBe(raw)
        }
        expect(question.options).toHaveLength(4)
        expect(new Set(question.options).size).toBe(4)
        expect(question.options).toContain(question.answer)
        for (const option of question.options) {
          const [numerator, denominator] = option.split('/').map(Number)
          expect(fractionLabel(numerator, denominator)).toBe(option)
          expect(denominator).toBeGreaterThanOrEqual(2)
          expect(denominator).toBeLessThanOrEqual(12)
          expect(numerator).toBeGreaterThanOrEqual(1)
          expect(numerator).toBeLessThan(denominator)
        }
        const target = question.shaded / question.total
        const equivalent = question.options.filter(option => Math.abs(fractionValue(option) - target) < 1e-9)
        expect(equivalent).toEqual([question.answer])
      }
    }
  })

  it('答错记录尝试次数，答对推进题目，完成八题结算星星', () => {
    const save = newFraction('starter', seeded(3))
    const first = save.flight.questions[0]
    const wrong = first.options.find(option => option !== first.answer)!
    expect(answerFraction(save, wrong)).toBe(false)
    expect(save.flight).toMatchObject({ correct: 0, mistakes: 1, answered: wrong })
    expect(answerFraction(save, first.answer)).toBeNull()
    expect(advanceFraction(save)).toBe('next')
    expect(save.flight).toMatchObject({ index: 1, answered: null })
    for (let index = 1; index < FRACTION_QUESTIONS; index++) {
      expect(answerFraction(save, save.flight.questions[index].answer)).toBe(true)
      expect(advanceFraction(save)).toBe(index === FRACTION_QUESTIONS - 1 ? 'finished' : 'next')
    }
    expect(save.flight.finished).toBe(true)
    expect(fractionStars(save.flight)).toBe(2)
    expect(save.best.starter).toBe(2)
    expect(save.totalCorrect).toBe(FRACTION_QUESTIONS - 1)
    expect(save.flights).toBe(1)
    expect(answerFraction(save, '1/2')).toBeNull()

    restartFraction(save, seeded(4))
    expect(save.flight.finished).toBe(false)
    expect(save.flight.index).toBe(0)
    expect(save.best.starter).toBe(2)
    expect(save.flights).toBe(1)
  })

  it.each([[0, 3], [1, 2], [3, 1]] as const)('错 %i 题得 %i 颗星', (mistakes, stars) => {
    expect(fractionStars({ mistakes })).toBe(stars)
  })

  it('切换难度会生成最简分数题，并保留历史最佳', () => {
    const save = newFraction('starter', seeded(5))
    save.best.starter = 3
    switchFractionDifficulty(save, 'master', seeded(6))
    expect(save.difficulty).toBe('master')
    expect(save.flight.difficulty).toBe('master')
    expect(save.flight.questions.every(question => question.mode === 'simplify')).toBe(true)
    expect(save.best.starter).toBe(3)
    expect(save.best.master).toBe(0)
  })

  it('进行中和完成状态能恢复，篡改题目或进度会被忽略', () => {
    const mid = newFraction('explorer', seeded(7))
    answerFraction(mid, mid.flight.questions[0].options.find(option => option !== mid.flight.questions[0].answer)!)
    expect(restoreFraction(JSON.stringify(mid))).toEqual(mid)
    advanceFraction(mid)
    expect(restoreFraction(JSON.stringify(mid))).toEqual(mid)

    const finished = newFraction('starter', seeded(8))
    for (let index = 0; index < FRACTION_QUESTIONS; index++) {
      answerFraction(finished, finished.flight.questions[index].answer)
      advanceFraction(finished)
    }
    expect(restoreFraction(JSON.stringify(finished))).toEqual(finished)

    const base = newFraction('starter', seeded(9))
    const answered = copy(base)
    answerFraction(answered, answered.flight.questions[0].answer)
    const badAnswer = copy(base)
    badAnswer.flight.questions[0].answer = badAnswer.flight.questions[0].options.find(option => option !== badAnswer.flight.questions[0].answer)!
    const badOptions = copy(base)
    badOptions.flight.questions[0] = { total: 4, shaded: 2, mode: 'identify', answer: '2/4', options: ['1/2', '2/4', '3/4', '1/4'] }
    const duplicateOptions = copy(base)
    duplicateOptions.flight.questions[0].options[1] = duplicateOptions.flight.questions[0].options[0]
    const badCounters = copy(answered)
    badCounters.flight.correct = 4
    const badFinished = copy(finished)
    badFinished.best.starter = 1
    const unfinished = copy(finished)
    unfinished.flight.finished = false
    for (const value of [
      null, 'broken', { ...base, version: 2 }, { ...base, difficulty: 'expert' },
      { ...base, flight: { ...base.flight, difficulty: 'master' } }, badAnswer, badOptions,
      duplicateOptions, badCounters, badFinished, unfinished,
      { ...finished, flights: -1 }, { ...finished, totalCorrect: 2.5 },
    ]) expect(restoreFraction(typeof value === 'string' ? value : JSON.stringify(value))).toBeNull()
  })

  it('难度配置覆盖三档分数练习', () => {
    expect(fractionDifficulties.map(item => item.id)).toEqual(['starter', 'explorer', 'master'])
  })
})
