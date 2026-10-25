import { describe, expect, it } from 'vitest'
import {
  advancePoem, checkPoem, clearPoemSelection, newPoem, poemHint, poemPools, poemStars,
  POEM_QUESTIONS, restorePoem, selectPoemTile, switchPoemDifficulty,
  type PoemDifficulty, type PoemSave,
} from '../games/poem-order'

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
const difficulties: PoemDifficulty[] = ['starter', 'explorer', 'master']

describe('诗句排队', () => {
  it.each(difficulties)('%s 难度生成八首不重复的诗和打乱的诗句', difficulty => {
    for (let seed = 1; seed <= 8; seed++) {
      const round = newPoem(difficulty, seeded(seed)).round
      expect(round.questions).toHaveLength(POEM_QUESTIONS)
      expect(new Set(round.questions.map(question => question.poemId)).size).toBe(POEM_QUESTIONS)
      const pool = poemPools[difficulty === 'starter' ? 'starter' : 'explorer']
      for (const question of round.questions) {
        const source = pool.find(poem => poem.id === question.poemId)
        expect(source).toBeTruthy()
        expect(question.title).toBe(source!.title)
        expect(question.author).toBe(source!.author)
        expect(question.lineCount).toBe(4)
        expect(question.answer).toHaveLength(4)
        expect(question.answer.map(id => question.tiles.find(tile => tile.id === id)?.text)).toEqual(source!.lines)
        expect(question.tiles).toHaveLength(difficulty === 'master' ? 5 : 4)
        const extras = question.tiles.filter(tile => !question.answer.includes(tile.id))
        if (difficulty === 'master') {
          expect(extras).toHaveLength(1)
          expect(source!.lines).not.toContain(extras[0].text)
        } else {
          expect(extras).toHaveLength(0)
        }
      }
    }
  })

  it('选句可以取下和重排，排错保留选择并记录重排次数', () => {
    const save = newPoem('starter', seeded(3))
    const question = save.round.questions[0]
    expect(selectPoemTile(save, question.answer[0])).toBe(true)
    expect(selectPoemTile(save, question.answer[0])).toBe(true)
    expect(save.round.selected).toEqual([])
    for (const id of [question.answer[1], question.answer[0], question.answer[2], question.answer[3]]) {
      expect(selectPoemTile(save, id)).toBe(true)
    }
    expect(checkPoem(save)).toBe(false)
    expect(save.round).toMatchObject({ mistakes: 1, correct: 0, solved: false })
    expect(save.round.selected).toHaveLength(4)
    clearPoemSelection(save)
    expect(save.round.selected).toEqual([])
    for (const id of question.answer) expect(selectPoemTile(save, id)).toBe(true)
    expect(checkPoem(save)).toBe(true)
    expect(save.round).toMatchObject({ solved: true, correct: 1, mistakes: 1 })
    expect(advancePoem(save)).toBe('next')
    expect(save.round).toMatchObject({ index: 1, selected: [], solved: false })
  })

  it('提示返回第一句，挑战难度最多只能选四句', () => {
    const save = newPoem('master', seeded(4))
    const question = save.round.questions[0]
    expect(poemHint(save)).toBe(question.tiles.find(tile => tile.id === question.answer[0])!.text)
    expect(save.round.hints).toBe(1)
    for (const id of question.answer) expect(selectPoemTile(save, id)).toBe(true)
    const extra = question.tiles.find(tile => !question.answer.includes(tile.id))!
    expect(selectPoemTile(save, extra.id)).toBe(false)
    expect(save.round.selected).toHaveLength(4)
    expect(checkPoem(save)).toBe(true)
  })

  it('完成八首后结算星星、累计数量并保留最佳记录', () => {
    const save = newPoem('starter', seeded(5))
    for (let index = 0; index < POEM_QUESTIONS; index++) {
      const question = save.round.questions[save.round.index]
      for (const id of question.answer) selectPoemTile(save, id)
      expect(checkPoem(save)).toBe(true)
      const result = advancePoem(save)
      expect(result).toBe(index === POEM_QUESTIONS - 1 ? 'finished' : 'next')
    }
    expect(save.round.finished).toBe(true)
    expect(poemStars(save.round)).toBe(3)
    expect(save.best.starter).toBe(3)
    expect(save.totalPoems).toBe(POEM_QUESTIONS)
    expect(save.rounds).toBe(1)
    expect(advancePoem(save)).toBeNull()

    const saveWithMistakes = newPoem('starter', seeded(6))
    for (let index = 0; index < POEM_QUESTIONS; index++) {
      const question = saveWithMistakes.round.questions[saveWithMistakes.round.index]
      if (index < 3) {
        selectPoemTile(saveWithMistakes, question.answer[1])
        selectPoemTile(saveWithMistakes, question.answer[0])
        selectPoemTile(saveWithMistakes, question.answer[2])
        selectPoemTile(saveWithMistakes, question.answer[3])
        expect(checkPoem(saveWithMistakes)).toBe(false)
        clearPoemSelection(saveWithMistakes)
      }
      for (const id of question.answer) selectPoemTile(saveWithMistakes, id)
      expect(checkPoem(saveWithMistakes)).toBe(true)
      advancePoem(saveWithMistakes)
    }
    expect(poemStars(saveWithMistakes.round)).toBe(1)
    expect(saveWithMistakes.best.starter).toBe(1)
  })

  it.each([[0, 3], [1, 2], [2, 2], [5, 1]] as const)('重排 %i 次得 %i 颗星', (mistakes, stars) => {
    expect(poemStars({ mistakes })).toBe(stars)
  })

  it('切换难度生成对应的诗体并保留最佳记录', () => {
    const save = newPoem('starter', seeded(8))
    save.best.starter = 3
    switchPoemDifficulty(save, 'master', seeded(9))
    expect(save.difficulty).toBe('master')
    expect(save.round.difficulty).toBe('master')
    expect(save.round.questions.every(question => question.tiles.length === 5)).toBe(true)
    expect(save.best.starter).toBe(3)
    expect(save.best.master).toBe(0)
  })

  it('进行中、排好和已完成的状态都能恢复，损坏数据会被忽略', () => {
    const base = newPoem('starter', seeded(11))
    const question = base.round.questions[0]
    selectPoemTile(base, question.answer[0])
    selectPoemTile(base, question.answer[1])
    expect(restorePoem(JSON.stringify(base))).toEqual(base)

    const solved = copy(base)
    clearPoemSelection(solved)
    for (const id of question.answer) selectPoemTile(solved, id)
    expect(checkPoem(solved)).toBe(true)
    expect(restorePoem(JSON.stringify(solved))).toEqual(solved)
    expect(restorePoem(JSON.stringify(saveWithFinish()))).not.toBeNull()

    const badTitle = copy(base)
    badTitle.round.questions[0].title = '错误的诗'
    const duplicateTile = copy(base)
    duplicateTile.round.questions[0].tiles[1].text = duplicateTile.round.questions[0].tiles[0].text
    const badSelected = copy(base)
    badSelected.round.selected = ['missing-tile']
    const badOrder = copy(solved)
    ;[badOrder.round.selected[0], badOrder.round.selected[1]] = [badOrder.round.selected[1], badOrder.round.selected[0]]
    const badCount = copy(solved)
    badCount.round.correct = 0
    const badHint = copy(base)
    badHint.round.hints = -1
    const finished = saveWithFinish()
    const badBest = copy(finished)
    badBest.best.starter = 0
    for (const value of [
      null, 'broken', { ...base, version: 2 }, { ...base, difficulty: 'expert' },
      { ...base, round: { ...base.round, difficulty: 'master' } }, badTitle, duplicateTile,
      badSelected, badOrder, badCount, badHint, badBest,
      { ...finished, totalPoems: -1 }, { ...finished, rounds: 1.5 },
      { ...base, round: { ...base.round, questions: base.round.questions.slice(0, 7) } },
    ] as unknown[]) expect(restorePoem(typeof value === 'string' ? value : JSON.stringify(value))).toBeNull()
  })
})

function saveWithFinish(): PoemSave {
  const save = newPoem('starter', seeded(12))
  for (let index = 0; index < POEM_QUESTIONS; index++) {
    const question = save.round.questions[save.round.index]
    for (const id of question.answer) selectPoemTile(save, id)
    checkPoem(save)
    advancePoem(save)
  }
  return save
}
