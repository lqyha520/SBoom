import { describe, expect, it } from 'vitest'
import {
  advanceClock, answerClock, clockExplanation, clockStars, CLOCK_QUESTIONS, formatClock,
  newClock, restoreClock, switchClockDifficulty, type ClockDifficulty, type ClockSave,
} from '../games/clock-town'

function seeded(seed: number) {
  return () => {
    seed = (seed + 0x6D2B79F5) >>> 0
    let value = seed
    value = Math.imul(value ^ (value >>> 15), value | 1)
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61)
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296
  }
}
function copy<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
const difficulties: ClockDifficulty[] = ['starter', 'explorer', 'master']
const allowed: Record<ClockDifficulty, number[]> = {
  starter: [0],
  explorer: [0, 15, 30, 45],
  master: [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55],
}

describe('时钟小镇', () => {
  it('整点时间会补零显示', () => {
    expect(formatClock(3, 0)).toBe('3:00')
    expect(formatClock(12, 5)).toBe('12:05')
  })

  it.each(difficulties)('%s 难度生成八个不同时间、合法选项和正确答案', difficulty => {
    for (let seed = 1; seed <= 10; seed++) {
      const round = newClock(difficulty, seeded(seed)).round
      expect(round.questions).toHaveLength(CLOCK_QUESTIONS)
      expect(new Set(round.questions.map(question => question.answer)).size).toBe(CLOCK_QUESTIONS)
      for (const question of round.questions) {
        expect(question.hour).toBeGreaterThanOrEqual(1)
        expect(question.hour).toBeLessThanOrEqual(12)
        expect(allowed[difficulty]).toContain(question.minute)
        expect(question.answer).toBe(formatClock(question.hour, question.minute))
        expect(question.options).toHaveLength(4)
        expect(new Set(question.options).size).toBe(4)
        expect(question.options).toContain(question.answer)
        for (const option of question.options) {
          expect(option).toMatch(/^([1-9]|1[0-2]):[0-5]\d$/)
          expect(allowed[difficulty]).toContain(Number(option.split(':')[1]))
        }
      }
    }
  })

  it('答错记录错误，答过之后不能重复作答', () => {
    const save = newClock('explorer', seeded(3))
    const question = save.round.questions[0]
    const wrong = question.options.find(option => option !== question.answer)!
    expect(answerClock(save, wrong)).toBe(false)
    expect(save.round).toMatchObject({ answered: wrong, mistakes: 1, correct: 0 })
    expect(answerClock(save, question.answer)).toBeNull()
    expect(advanceClock(save)).toBe('next')
    expect(save.round).toMatchObject({ index: 1, answered: null })
  })

  it('完成八题后结算星星、最佳记录和累计数据', () => {
    const save = newClock('master', seeded(5))
    for (let index = 0; index < CLOCK_QUESTIONS; index++) {
      const question = save.round.questions[save.round.index]
      expect(answerClock(save, question.answer)).toBe(true)
      const result = advanceClock(save)
      expect(result).toBe(index === CLOCK_QUESTIONS - 1 ? 'finished' : 'next')
    }
    expect(save.round.finished).toBe(true)
    expect(clockStars(save.round)).toBe(3)
    expect(save.best.master).toBe(3)
    expect(save.totalCorrect).toBe(CLOCK_QUESTIONS)
    expect(save.rounds).toBe(1)
    expect(answerClock(save, '3:00')).toBeNull()
    expect(advanceClock(save)).toBeNull()
  })

  it.each([[0, 3], [1, 2], [2, 1], [7, 1]] as const)('错 %i 题得 %i 颗星', (mistakes, stars) => {
    expect(clockStars({ mistakes })).toBe(stars)
  })

  it('读时解释会说明时针和分针的位置', () => {
    expect(clockExplanation({ hour: 7, minute: 0, answer: '7:00' })).toBe('分针指向 12，时针指向 7，是 7:00。')
    expect(clockExplanation({ hour: 12, minute: 30, answer: '12:30' })).toBe('时针在 12 和 1 之间，分针指向 6，是 12:30。')
    expect(clockExplanation({ hour: 4, minute: 55, answer: '4:55' })).toBe('时针在 4 和 5 之间，分针指向 11，是 4:55。')
  })

  it('切换难度生成对应时间粒度并保留最佳记录', () => {
    const save = newClock('starter', seeded(8))
    save.best.starter = 3
    switchClockDifficulty(save, 'explorer', seeded(9))
    expect(save.difficulty).toBe('explorer')
    expect(save.round.difficulty).toBe('explorer')
    expect(save.round.questions.every(question => [0, 15, 30, 45].includes(question.minute))).toBe(true)
    expect(save.best.starter).toBe(3)
    expect(save.best.explorer).toBe(0)
  })

  it('进行中、已回答和已完成状态都能恢复，损坏数据会被忽略', () => {
    const base = newClock('starter', seeded(11))
    expect(restoreClock(JSON.stringify(base))).toEqual(base)

    const answered = copy(base)
    expect(answerClock(answered, answered.round.questions[0].answer)).toBe(true)
    expect(restoreClock(JSON.stringify(answered))).toEqual(answered)

    const finished = finishedSave()
    expect(restoreClock(JSON.stringify(finished))).toEqual(finished)

    const badAnswer = copy(base)
    badAnswer.round.questions[0].answer = '13:00'
    const badMinute = copy(base)
    badMinute.round.questions[0].options[0] = '3:05'
    const duplicateOptions = copy(base)
    duplicateOptions.round.questions[0].options[1] = duplicateOptions.round.questions[0].options[0]
    const duplicateTimes = copy(base)
    duplicateTimes.round.questions[1] = copy(duplicateTimes.round.questions[0])
    const badAnswered = copy(answered)
    badAnswered.round.answered = '9:99'
    const badCounters = copy(answered)
    badCounters.round.mistakes = 3
    const badBest = copy(finished)
    badBest.best.starter = 0
    for (const value of [
      null, 'broken', { ...base, version: 2 }, { ...base, difficulty: 'expert' },
      { ...base, round: { ...base.round, difficulty: 'master' } }, badAnswer, badMinute,
      duplicateOptions, duplicateTimes, badAnswered, badCounters, badBest,
      { ...finished, totalCorrect: -1 }, { ...finished, rounds: 1.5 },
      { ...base, round: { ...base.round, questions: base.round.questions.slice(0, 7) } },
    ] as unknown[]) expect(restoreClock(typeof value === 'string' ? value : JSON.stringify(value))).toBeNull()
  })
})

function finishedSave(): ClockSave {
  const save = newClock('starter', seeded(12))
  for (let index = 0; index < CLOCK_QUESTIONS; index++) {
    answerClock(save, save.round.questions[save.round.index].answer)
    advanceClock(save)
  }
  return save
}
