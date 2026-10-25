import { describe, expect, it } from 'vitest'
import { englishWords } from '../games/english-words'
import {
  advanceMarket, answerMarket, MARKET_QUESTIONS, marketStars, newMarket, restoreMarket,
  switchMarketDifficulty, type MarketDifficulty, type MarketSave,
} from '../games/word-market'

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
const difficulties: MarketDifficulty[] = ['starter', 'explorer', 'master']

describe('单词集市', () => {
  it.each(difficulties)('%s 难度生成八个不重复单词和同难度干扰项', difficulty => {
    for (let seed = 1; seed <= 8; seed++) {
      const round = newMarket(difficulty, seeded(seed)).round
      expect(round.questions).toHaveLength(MARKET_QUESTIONS)
      expect(new Set(round.questions.map(question => question.wordId)).size).toBe(MARKET_QUESTIONS)
      for (const question of round.questions) {
        expect(question.options).toHaveLength(4)
        expect(new Set(question.options).size).toBe(4)
        expect(question.options).toContain(question.wordId)
        expect(question.options.every(word => englishWords[difficulty].some(item => item.word === word))).toBe(true)
        expect(englishWords[difficulty].some(item => item.word === question.wordId)).toBe(true)
      }
    }
  })

  it('答错记录错误，答过之后不能重复作答', () => {
    const save = newMarket('starter', seeded(3))
    const question = save.round.questions[0]
    const wrong = question.options.find(word => word !== question.wordId)!
    expect(answerMarket(save, wrong)).toBe(false)
    expect(save.round).toMatchObject({ answered: wrong, mistakes: 1, correct: 0 })
    expect(answerMarket(save, question.wordId)).toBeNull()
    expect(advanceMarket(save)).toBe('next')
    expect(save.round).toMatchObject({ index: 1, answered: null })
  })

  it('完成八题后结算星星、最佳记录和累计数据', () => {
    const save = newMarket('starter', seeded(5))
    for (let index = 0; index < MARKET_QUESTIONS; index++) {
      const question = save.round.questions[save.round.index]
      if (index === 0) {
        expect(answerMarket(save, question.options.find(word => word !== question.wordId)!)).toBe(false)
      } else {
        expect(answerMarket(save, question.wordId)).toBe(true)
      }
      const result = advanceMarket(save)
      expect(result).toBe(index === MARKET_QUESTIONS - 1 ? 'finished' : 'next')
    }
    expect(save.round.finished).toBe(true)
    expect(marketStars(save.round)).toBe(2)
    expect(save.best.starter).toBe(2)
    expect(save.totalCorrect).toBe(MARKET_QUESTIONS - 1)
    expect(save.rounds).toBe(1)
    expect(answerMarket(save, 'cat')).toBeNull()
    expect(advanceMarket(save)).toBeNull()
  })

  it.each([[0, 3], [1, 2], [2, 1], [7, 1]] as const)('错 %i 题得 %i 颗星', (mistakes, stars) => {
    expect(marketStars({ mistakes })).toBe(stars)
  })

  it('切换难度生成对应单词库并保留历史最佳', () => {
    const save = newMarket('starter', seeded(8))
    save.best.starter = 3
    switchMarketDifficulty(save, 'master', seeded(9))
    expect(save.difficulty).toBe('master')
    expect(save.round.difficulty).toBe('master')
    expect(save.round.questions.every(question => englishWords.master.some(item => item.word === question.wordId))).toBe(true)
    expect(save.best.starter).toBe(3)
    expect(save.best.master).toBe(0)
  })

  it('进行中、已选择和已完成状态都能恢复，损坏数据会被忽略', () => {
    const base = newMarket('explorer', seeded(11))
    expect(restoreMarket(JSON.stringify(base))).toEqual(base)

    const answered = copy(base)
    expect(answerMarket(answered, answered.round.questions[0].options.find(word => word !== answered.round.questions[0].wordId)!)).toBe(false)
    expect(restoreMarket(JSON.stringify(answered))).toEqual(answered)

    const finished = finishedSave()
    expect(restoreMarket(JSON.stringify(finished))).toEqual(finished)

    const missingAnswer = copy(base)
    const sourceWord = missingAnswer.round.questions[0].wordId
    missingAnswer.round.questions[0].options = missingAnswer.round.questions[0].options
      .map(word => word === sourceWord ? missingAnswer.round.questions[0].options.find(item => item !== sourceWord)! : word)
    const duplicateOptions = copy(base)
    duplicateOptions.round.questions[0].options[1] = duplicateOptions.round.questions[0].options[0]
    const crossTier = copy(base)
    crossTier.round.questions[0].options[0] = 'elephant'
    const badAnswered = copy(answered)
    badAnswered.round.answered = 'missing'
    const badCounters = copy(answered)
    badCounters.round.correct = 5
    const badBest = copy(finished)
    badBest.best.explorer = 0
    for (const value of [
      null, 'broken', { ...base, version: 2 }, { ...base, difficulty: 'expert' },
      { ...base, round: { ...base.round, difficulty: 'master' } }, missingAnswer,
      duplicateOptions, crossTier, badAnswered, badCounters, badBest,
      { ...finished, totalCorrect: -1 }, { ...finished, rounds: 1.5 },
      { ...base, round: { ...base.round, questions: base.round.questions.slice(0, 7) } },
    ] as unknown[]) expect(restoreMarket(typeof value === 'string' ? value : JSON.stringify(value))).toBeNull()
  })
})

function finishedSave(): MarketSave {
  const save = newMarket('explorer', seeded(12))
  for (let index = 0; index < MARKET_QUESTIONS; index++) {
    answerMarket(save, save.round.questions[save.round.index].wordId)
    advanceMarket(save)
  }
  return save
}
