import { describe, expect, it } from 'vitest'
import {
  advanceRocket, answerRocket, newRocket, restartRocket, restoreRocket, rocketStars,
  ROCKET_QUESTIONS, switchRocketDifficulty, type RocketDifficulty, type RocketSave,
} from '../games/rocket-math'

function seeded(seed: number) {
  return () => {
    seed = (seed + 0x6D2B79F5) >>> 0
    let value = seed
    value = Math.imul(value ^ (value >>> 15), value | 1)
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61)
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296
  }
}
const copy = (save: RocketSave): RocketSave => JSON.parse(JSON.stringify(save))
const difficulties: RocketDifficulty[] = ['starter', 'explorer', 'pilot']

describe('口算火箭', () => {
  it.each(difficulties)('%s 难度生成算式、唯一选项和正确答案', difficulty => {
    for (let seed = 1; seed <= 12; seed++) {
      const flight = newRocket(difficulty, seeded(seed)).flight
      expect(flight.version).toBe(1)
      expect(flight.questions).toHaveLength(ROCKET_QUESTIONS)
      expect(new Set(flight.questions.map(question => question.expression)).size).toBe(ROCKET_QUESTIONS)
      for (const question of flight.questions) {
        const expected = question.operator === '+' ? question.left + question.right
          : question.operator === '-' ? question.left - question.right : question.left * question.right
        expect(question.answer).toBe(expected)
        expect(question.options).toHaveLength(4)
        expect(new Set(question.options).size).toBe(4)
        expect(question.options).toContain(question.answer)
        if (difficulty === 'starter') {
          expect(question.answer).toBeGreaterThanOrEqual(1)
          expect(question.answer).toBeLessThanOrEqual(20)
        }
        if (difficulty === 'explorer') {
          expect(question.answer).toBeGreaterThanOrEqual(1)
          expect(question.answer).toBeLessThanOrEqual(100)
        }
        if (difficulty === 'pilot') {
          expect(question.operator).toBe('×')
          expect(question.left).toBeGreaterThanOrEqual(2)
          expect(question.left).toBeLessThanOrEqual(9)
          expect(question.right).toBeGreaterThanOrEqual(2)
          expect(question.right).toBeLessThanOrEqual(9)
        } else {
          expect(['+', '-']).toContain(question.operator)
        }
      }
    }
  })

  it('答错记录错误并清空连对，答过之后不能重复作答', () => {
    const save = newRocket('starter', seeded(3))
    const question = save.flight.questions[0]
    const wrong = question.options.find(value => value !== question.answer)!
    expect(answerRocket(save, wrong)).toBe(false)
    expect(save.flight).toMatchObject({ mistakes: 1, correct: 0, streak: 0, answered: wrong })
    expect(answerRocket(save, question.answer)).toBeNull()
    expect(save.flight.mistakes).toBe(1)
    expect(advanceRocket(save)).toBe('next')
    expect(save.flight).toMatchObject({ index: 1, answered: null, bestStreak: 0 })
  })

  it('完成八题后结算星星、最佳记录和累计数据', () => {
    const saved = newRocket('starter', seeded(5))
    const firstQuestion = saved.flight.questions[0]
    expect(answerRocket(saved, firstQuestion.options.find(value => value !== firstQuestion.answer)!)).toBe(false)
    expect(advanceRocket(saved)).toBe('next')
    for (let index = 1; index < ROCKET_QUESTIONS; index++) {
      expect(answerRocket(saved, saved.flight.questions[index].answer)).toBe(true)
      const result = advanceRocket(saved)
      expect(result).toBe(index === ROCKET_QUESTIONS - 1 ? 'finished' : 'next')
    }
    expect(saved.flight.finished).toBe(true)
    expect(saved.flight.bestStreak).toBe(ROCKET_QUESTIONS - 1)
    expect(rocketStars(saved.flight)).toBe(2)
    expect(saved.best.starter).toBe(2)
    expect(saved.totalCorrect).toBe(ROCKET_QUESTIONS - 1)
    expect(saved.flights).toBe(1)
    expect(answerRocket(saved, 1)).toBeNull()
    expect(advanceRocket(saved)).toBeNull()

    restartRocket(saved, seeded(6))
    expect(saved.flight.finished).toBe(false)
    expect(saved.flight.index).toBe(0)
    expect(saved.best.starter).toBe(2)
    expect(saved.flights).toBe(1)
  })

  it.each([[0, 3], [1, 2], [2, 1], [5, 1]] as const)('错 %i 题得 %i 颗星', (mistakes, stars) => {
    expect(rocketStars({ mistakes })).toBe(stars)
  })

  it('切换难度会生成对应题型，并保留历史最佳', () => {
    const save = newRocket('starter', seeded(8))
    save.best.starter = 3
    switchRocketDifficulty(save, 'pilot', seeded(9))
    expect(save.difficulty).toBe('pilot')
    expect(save.flight.difficulty).toBe('pilot')
    expect(save.flight.questions.every(question => question.operator === '×')).toBe(true)
    expect(save.best.starter).toBe(3)
    expect(save.best.pilot).toBe(0)
  })

  it('进行中和已完成状态都能恢复，损坏数据会被忽略', () => {
    const save = newRocket('explorer', seeded(11))
    answerRocket(save, save.flight.questions[0].answer)
    expect(restoreRocket(JSON.stringify(save))).toEqual(save)
    advanceRocket(save)
    expect(restoreRocket(JSON.stringify(save))).toEqual(save)

    const finished = newRocket('starter', seeded(12))
    for (let index = 0; index < ROCKET_QUESTIONS; index++) {
      answerRocket(finished, finished.flight.questions[index].answer)
      advanceRocket(finished)
    }
    expect(restoreRocket(JSON.stringify(finished))).toEqual(finished)

    const base = newRocket('starter', seeded(13))
    const answeredBase = copy(base)
    answerRocket(answeredBase, answeredBase.flight.questions[0].answer)
    const badQuestion = copy(base)
    badQuestion.flight.questions[0].answer++
    const duplicateOption = copy(base)
    duplicateOption.flight.questions[0].options[1] = duplicateOption.flight.questions[0].options[0]
    const badAnswer = copy(answeredBase)
    badAnswer.flight.answered = 9999
    const badCounters = copy(answeredBase)
    badCounters.flight.mistakes = 3
    const badFinished = copy(finished)
    badFinished.best.starter = 1
    for (const value of [
      null, 'broken', { ...base, version: 2 }, { ...base, difficulty: 'expert' },
      { ...base, flight: { ...base.flight, difficulty: 'pilot' } }, badQuestion,
      duplicateOption, badAnswer, badCounters, badFinished,
      { ...finished, totalCorrect: -1 }, { ...finished, flights: 1.5 },
    ]) expect(restoreRocket(typeof value === 'string' ? value : JSON.stringify(value))).toBeNull()
  })
})
