import { describe, expect, it } from 'vitest'
import { englishWords } from '../games/english-words'
import {
  advanceSpell, checkSpell, clearSpellSelection, newSpell, restoreSpell, selectSpellTile,
  SPELL_QUESTIONS, spellHint, spellStars, switchSpellDifficulty,
  type SpellDifficulty, type SpellSave,
} from '../games/word-spell'

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
const difficulties: SpellDifficulty[] = ['starter', 'explorer', 'master']

function wrongOrder(question: { word: string; tiles: Array<{ id: string; letter: string }> }) {
  const pool = [...question.tiles]
  return question.word.split('').reverse().map(letter => {
    const index = pool.findIndex(tile => tile.letter === letter)
    return pool.splice(index, 1)[0].id
  })
}

describe('单词拼写', () => {
  it.each(difficulties)('%s 难度生成八个不重复单词和完整字母卡', difficulty => {
    for (let seed = 1; seed <= 8; seed++) {
      const round = newSpell(difficulty, seeded(seed)).round
      expect(round.questions).toHaveLength(SPELL_QUESTIONS)
      expect(new Set(round.questions.map(question => question.wordId)).size).toBe(SPELL_QUESTIONS)
      for (const question of round.questions) {
        const source = englishWords[difficulty].find(item => item.word === question.wordId)
        expect(source).toBeTruthy()
        expect(question.meaning).toBe(source!.meaning)
        expect(question.emoji).toBe(source!.emoji)
        expect(question.tiles).toHaveLength(question.word.length)
        expect(question.tiles.map(tile => tile.letter).sort().join('')).toBe(question.word.split('').sort().join(''))
        expect(question.answer.map(id => question.tiles.find(tile => tile.id === id)!.letter).join('')).toBe(question.word)
        expect(new Set(question.answer).size).toBe(question.word.length)
      }
    }
  })

  it('字母可以取下重排，拼错保留选择并记录次数', () => {
    const save = newSpell('starter', seeded(3))
    const question = save.round.questions[0]
    expect(selectSpellTile(save, question.answer[0])).toBe(true)
    expect(selectSpellTile(save, question.answer[0])).toBe(true)
    expect(save.round.selected).toEqual([])
    for (const id of wrongOrder(question)) expect(selectSpellTile(save, id)).toBe(true)
    expect(checkSpell(save)).toBe(false)
    expect(save.round).toMatchObject({ mistakes: 1, correct: 0, solved: false })
    expect(save.round.selected).toHaveLength(question.word.length)
    clearSpellSelection(save)
    for (const id of question.answer) expect(selectSpellTile(save, id)).toBe(true)
    expect(checkSpell(save)).toBe(true)
    expect(save.round).toMatchObject({ solved: true, correct: 1 })
    expect(advanceSpell(save)).toBe('next')
    expect(save.round).toMatchObject({ index: 1, selected: [], solved: false })
  })

  it('提示返回首字母，完成八题后结算星星与累计单词', () => {
    const save = newSpell('starter', seeded(5))
    expect(spellHint(save)).toBe(save.round.questions[0].word[0])
    expect(save.round.hints).toBe(1)
    for (let index = 0; index < SPELL_QUESTIONS; index++) {
      const question = save.round.questions[save.round.index]
      for (const id of question.answer) selectSpellTile(save, id)
      expect(checkSpell(save)).toBe(true)
      const result = advanceSpell(save)
      expect(result).toBe(index === SPELL_QUESTIONS - 1 ? 'finished' : 'next')
    }
    expect(save.round.finished).toBe(true)
    expect(spellStars(save.round)).toBe(3)
    expect(save.best.starter).toBe(3)
    expect(save.totalWords).toBe(SPELL_QUESTIONS)
    expect(save.rounds).toBe(1)
    expect(advanceSpell(save)).toBeNull()
  })

  it.each([[0, 3], [1, 2], [2, 2], [6, 1]] as const)('重拼 %i 次得 %i 颗星', (mistakes, stars) => {
    expect(spellStars({ mistakes })).toBe(stars)
  })

  it('切换难度生成对应长度的单词并保留最佳记录', () => {
    const save = newSpell('starter', seeded(8))
    save.best.starter = 3
    switchSpellDifficulty(save, 'master', seeded(9))
    expect(save.difficulty).toBe('master')
    expect(save.round.difficulty).toBe('master')
    expect(save.round.questions.every(question => question.word.length >= 8)).toBe(true)
    expect(save.best.starter).toBe(3)
    expect(save.best.master).toBe(0)
  })

  it('进行中、拼好和已完成状态都能恢复，损坏数据会被忽略', () => {
    const base = newSpell('explorer', seeded(11))
    selectSpellTile(base, base.round.questions[0].answer[0])
    expect(restoreSpell(JSON.stringify(base))).toEqual(base)

    const solved = copy(base)
    clearSpellSelection(solved)
    for (const id of solved.round.questions[0].answer) selectSpellTile(solved, id)
    expect(checkSpell(solved)).toBe(true)
    expect(restoreSpell(JSON.stringify(solved))).toEqual(solved)

    const finished = finishedSave()
    expect(restoreSpell(JSON.stringify(finished))).toEqual(finished)

    const badWord = copy(base)
    badWord.round.questions[0].word = 'zzz'
    const badLetters = copy(base)
    badLetters.round.questions[0].tiles[0].letter = 'x'
    const badAnswer = copy(base)
    badAnswer.round.questions[0].answer = [...badAnswer.round.questions[0].answer].reverse()
    const badSelected = copy(base)
    badSelected.round.selected = ['missing-tile']
    const badCount = copy(solved)
    badCount.round.correct = 0
    const badBest = copy(finished)
    badBest.best.explorer = 0
    for (const value of [
      null, 'broken', { ...base, version: 2 }, { ...base, difficulty: 'expert' },
      { ...base, round: { ...base.round, difficulty: 'master' } }, badWord, badLetters,
      badAnswer, badSelected, badCount, badBest,
      { ...finished, totalWords: -1 }, { ...finished, rounds: 1.5 },
      { ...base, round: { ...base.round, questions: base.round.questions.slice(0, 7) } },
    ] as unknown[]) expect(restoreSpell(typeof value === 'string' ? value : JSON.stringify(value))).toBeNull()
  })
})

function finishedSave(): SpellSave {
  const save = newSpell('explorer', seeded(12))
  for (let index = 0; index < SPELL_QUESTIONS; index++) {
    const question = save.round.questions[save.round.index]
    for (const id of question.answer) selectSpellTile(save, id)
    checkSpell(save)
    advanceSpell(save)
  }
  return save
}
