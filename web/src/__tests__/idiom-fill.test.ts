import { describe, expect, it } from 'vitest'
import {
  advanceIdiom, answerIdiom, idiomById, idiomDifficulties, idiomPools, idiomStars,
  IDIOM_QUESTIONS, newIdiom, restoreIdiom, switchIdiomDifficulty, type IdiomDifficulty, type IdiomSave,
} from '../games/idiom-fill'

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
const difficulties: IdiomDifficulty[] = ['starter', 'explorer', 'master']

describe('成语补字', () => {
  it.each(difficulties)('%s 难度生成八个不重复成语和四个唯一选项', difficulty => {
    for (let seed = 1; seed <= 8; seed++) {
      const round = newIdiom(difficulty, seeded(seed)).round
      expect(round.questions).toHaveLength(IDIOM_QUESTIONS)
      expect(new Set(round.questions.map(question => question.idiomId)).size).toBe(IDIOM_QUESTIONS)
      for (const question of round.questions) {
        const source = idiomById(difficulty, question.idiomId)
        expect(source).toBeTruthy()
        expect(question.options).toHaveLength(4)
        expect(new Set(question.options).size).toBe(4)
        expect(question.options).toContain(source!.answer)
        expect(question.options.every(char => source!.options.includes(char))).toBe(true)
        expect(source!.text[source!.blank]).toBe(source!.answer)
      }
    }
  })

  it('答错后不能重复作答，答对后进入下一个成语', () => {
    const save = newIdiom('starter', seeded(3))
    const question = save.round.questions[0]
    const source = idiomById('starter', question.idiomId)!
    const wrong = question.options.find(char => char !== source.answer)!
    expect(answerIdiom(save, wrong)).toBe(false)
    expect(save.round).toMatchObject({ answered: wrong, mistakes: 1, correct: 0 })
    expect(answerIdiom(save, source.answer)).toBeNull()
    expect(advanceIdiom(save)).toBe('next')
    expect(save.round).toMatchObject({ index: 1, answered: null })

    const nextSource = idiomById('starter', save.round.questions[1].idiomId)!
    expect(answerIdiom(save, nextSource.answer)).toBe(true)
    expect(save.round.correct).toBe(1)
  })

  it('完成八题后结算星星和累计数据', () => {
    const save = newIdiom('starter', seeded(5))
    for (let index = 0; index < IDIOM_QUESTIONS; index++) {
      const source = idiomById('starter', save.round.questions[save.round.index].idiomId)!
      if (index === 2) {
        const wrong = save.round.questions[save.round.index].options.find(char => char !== source.answer)!
        expect(answerIdiom(save, wrong)).toBe(false)
        expect(advanceIdiom(save)).toBe('next')
        continue
      }
      expect(answerIdiom(save, source.answer)).toBe(true)
      const result = advanceIdiom(save)
      expect(result).toBe(index === IDIOM_QUESTIONS - 1 ? 'finished' : 'next')
    }
    expect(save.round.finished).toBe(true)
    expect(idiomStars(save.round)).toBe(2)
    expect(save.best.starter).toBe(2)
    expect(save.totalCorrect).toBe(IDIOM_QUESTIONS - 1)
    expect(save.rounds).toBe(1)
    expect(answerIdiom(save, '一')).toBeNull()
    expect(advanceIdiom(save)).toBeNull()
  })

  it.each([[0, 3], [1, 2], [2, 1], [7, 1]] as const)('错 %i 题得 %i 颗星', (mistakes, stars) => {
    expect(idiomStars({ mistakes })).toBe(stars)
  })

  it('切换难度生成对应成语库并保留历史最佳', () => {
    const save = newIdiom('starter', seeded(8))
    save.best.starter = 3
    switchIdiomDifficulty(save, 'master', seeded(9))
    expect(save.difficulty).toBe('master')
    expect(save.round.difficulty).toBe('master')
    expect(save.round.questions.every(question => idiomPools.master.some(item => item.id === question.idiomId))).toBe(true)
    for (const difficulty of idiomDifficulties) expect(save.best[difficulty.id]).toBe(difficulty.id === 'starter' ? 3 : 0)
  })

  it('进行中、已回答和已完成状态都能恢复，损坏数据会被忽略', () => {
    const base = newIdiom('explorer', seeded(11))
    expect(restoreIdiom(JSON.stringify(base))).toEqual(base)

    const answeredSource = idiomById('explorer', base.round.questions[0].idiomId)!
    expect(answerIdiom(base, answeredSource.answer)).toBe(true)
    expect(restoreIdiom(JSON.stringify(base))).toEqual(base)

    const finished = finishedSave()
    expect(restoreIdiom(JSON.stringify(finished))).toEqual(finished)

    const badIdiom = copy(base)
    badIdiom.round.questions[0].idiomId = 'missing'
    const duplicateOptions = copy(base)
    duplicateOptions.round.questions[0].options[1] = duplicateOptions.round.questions[0].options[0]
    const foreignOption = copy(base)
    foreignOption.round.questions[0].options[0] = '龘'
    expect(restoreIdiom(JSON.stringify(foreignOption))).toBeNull()
    const badAnswered = copy(base)
    badAnswered.round.answered = 'missing'
    const badCounters = copy(base)
    badCounters.round.mistakes = 2
    const badBest = copy(finished)
    badBest.best.explorer = 0
    for (const value of [
      null, 'broken', { ...base, version: 2 }, { ...base, difficulty: 'expert' },
      { ...base, round: { ...base.round, difficulty: 'master' } }, badIdiom,
      duplicateOptions, badAnswered, badCounters, badBest,
      { ...finished, totalCorrect: -1 }, { ...finished, rounds: 1.5 },
      { ...base, round: { ...base.round, questions: base.round.questions.slice(0, 7) } },
    ] as unknown[]) expect(restoreIdiom(typeof value === 'string' ? value : JSON.stringify(value))).toBeNull()
  })
})

function finishedSave(): IdiomSave {
  const save = newIdiom('explorer', seeded(12))
  for (let index = 0; index < IDIOM_QUESTIONS; index++) {
    answerIdiom(save, idiomById('explorer', save.round.questions[save.round.index].idiomId)!.answer)
    advanceIdiom(save)
  }
  return save
}
