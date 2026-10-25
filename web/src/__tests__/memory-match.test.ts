import { describe, expect, it } from 'vitest'
import {
  flipMemoryCard, memoryConfigFor, memoryStars, newMemory, resolveMemory,
  restartMemory, restoreMemory, switchMemoryDifficulty, type MemorySave,
} from '../games/memory-match'

function seeded(seed: number) {
  return () => {
    seed = (seed + 0x6D2B79F5) >>> 0
    let value = seed
    value = Math.imul(value ^ (value >>> 15), value | 1)
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61)
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296
  }
}
const copy = (save: MemorySave): MemorySave => JSON.parse(JSON.stringify(save))
const pairIds = (save: MemorySave) => [...new Set(save.round.cards.map(card => card.pairId))]
function flipPair(save: MemorySave, pairId: string) {
  const cards = save.round.cards.filter(card => card.pairId === pairId)
  expect(flipMemoryCard(save.round, cards[0].id)).toBe('first')
  expect(flipMemoryCard(save.round, cards[1].id)).toBe('matched')
  return resolveMemory(save)
}
function expressionValue(text: string): number | null {
  const match = /^(\d{1,2}) ([+×-]) (\d{1,2})$/.exec(text)
  if (!match) return null
  const left = Number(match[1]); const right = Number(match[3])
  return match[2] === '+' ? left + right : match[2] === '-' ? left - right : left * right
}

describe('记忆翻牌', () => {
  it.each(['cozy', 'focus', 'master'] as const)('%s 难度生成完整且唯一的配对牌', difficulty => {
    const pairs = memoryConfigFor(difficulty).pairs
    for (let seed = 1; seed <= 10; seed++) {
      const round = newMemory(difficulty, seeded(seed)).round
      expect(round.cards).toHaveLength(pairs * 2)
      expect(round.cards.map(card => card.id)).toEqual(Array.from({ length: pairs * 2 }, (_, index) => index))
      const grouped = new Map<string, typeof round.cards>()
      for (const card of round.cards) grouped.set(card.pairId, [...(grouped.get(card.pairId) ?? []), card])
      expect(grouped.size).toBe(pairs)
      const answers = new Set<string>()
      for (const cards of grouped.values()) {
        expect(cards).toHaveLength(2)
        const expression = cards.find(card => card.face === 'expression')!
        const answer = cards.find(card => card.face === 'answer')!
        expect(expressionValue(expression.text)).toBe(Number(answer.text))
        if (difficulty === 'master') expect(expression.text).toContain('×')
        else expect(expression.text).not.toContain('×')
        answers.add(answer.text)
      }
      expect(answers.size).toBe(pairs)
    }
  })

  it('翻开两张相同的牌会配对，不同的牌会翻回去并计一次翻牌', () => {
    const save = newMemory('cozy', seeded(4))
    const ids = pairIds(save)
    const [first, second] = save.round.cards.filter(card => card.pairId === ids[0])
    expect(flipMemoryCard(save.round, first.id)).toBe('first')
    expect(flipMemoryCard(save.round, first.id)).toBe('ignored')
    expect(flipMemoryCard(save.round, second.id)).toBe('matched')
    expect(save.round.moves).toBe(1)
    expect(resolveMemory(save)).toBe('resolved')
    expect(save.round.matched).toEqual([ids[0]])
    expect(flipMemoryCard(save.round, first.id)).toBe('ignored')

    const wrongA = save.round.cards.find(card => card.pairId === ids[1])!
    const wrongB = save.round.cards.find(card => card.pairId === ids[2])!
    expect(flipMemoryCard(save.round, wrongA.id)).toBe('first')
    expect(flipMemoryCard(save.round, wrongB.id)).toBe('mismatch')
    expect(save.round.moves).toBe(2)
    const third = save.round.cards.find(card => card.pairId === ids[3])!
    expect(flipMemoryCard(save.round, third.id)).toBe('ignored')
    expect(resolveMemory(save)).toBe('resolved')
    expect(save.round.flipped).toEqual([])
    expect(save.round.matched).toEqual([ids[0]])
  })

  it('全部配对后结算星星、最佳成绩和累计局数', () => {
    const save = newMemory('cozy', seeded(7))
    const ids = pairIds(save)
    ids.forEach((id, index) => {
      expect(flipPair(save, id)).toBe(index === ids.length - 1 ? 'finished' : 'resolved')
    })
    expect(save.round.finished).toBe(true)
    expect(save.round.moves).toBe(ids.length)
    expect(save.round.matched).toHaveLength(ids.length)
    expect(memoryStars(save.round)).toBe(3)
    expect(save.best.cozy).toBe(3)
    expect(save.totalMatches).toBe(ids.length)
    expect(save.rounds).toBe(1)
    expect(resolveMemory(save)).toBe('none')

    restartMemory(save, seeded(8))
    expect(save.round.finished).toBe(false)
    expect(save.round.moves).toBe(0)
    expect(save.rounds).toBe(1)
    expect(save.totalMatches).toBe(ids.length)
    expect(save.best.cozy).toBe(3)
  })

  it.each([[8, 3], [9, 2], [11, 2], [12, 1]] as const)('6 对牌翻 %i 次得 %i 颗星', (moves, stars) => {
    const round = newMemory('cozy', seeded(2)).round
    expect(memoryStars({ moves, cards: round.cards })).toBe(stars)
  })

  it('切换难度会重新发牌并保留历史最佳', () => {
    const save = newMemory('cozy', seeded(9))
    save.best.cozy = 2
    switchMemoryDifficulty(save, 'master', seeded(10))
    expect(save.difficulty).toBe('master')
    expect(save.round.difficulty).toBe('master')
    expect(save.round.cards).toHaveLength(20)
    expect(save.best.cozy).toBe(2)
    expect(save.best.master).toBe(0)
  })

  it('中途和完成状态能恢复，篡改牌面或进度会被忽略', () => {
    const mid = newMemory('focus', seeded(11))
    flipPair(mid, pairIds(mid)[0])
    flipMemoryCard(mid.round, mid.round.cards.find(card => card.pairId === pairIds(mid)[1])!.id)
    expect(restoreMemory(JSON.stringify(mid))).toEqual(mid)

    const finished = newMemory('cozy', seeded(12))
    for (const id of pairIds(finished)) flipPair(finished, id)
    expect(restoreMemory(JSON.stringify(finished))).toEqual(finished)

    const base = newMemory('cozy', seeded(13))
    const badExpression = copy(base)
    const expressionCard = badExpression.round.cards.find(card => card.face === 'expression')!
    expressionCard.text = expressionCard.text.replace(/(\d+)$/, value => String(Number(value) + 1))
    const duplicated = copy(base)
    const [firstPair, secondPair] = pairIds(duplicated).slice(0, 2)
    const sourceExpression = duplicated.round.cards.find(card => card.pairId === firstPair && card.face === 'expression')!
    const sourceAnswer = duplicated.round.cards.find(card => card.pairId === firstPair && card.face === 'answer')!
    const targetExpression = duplicated.round.cards.find(card => card.pairId === secondPair && card.face === 'expression')!
    const targetAnswer = duplicated.round.cards.find(card => card.pairId === secondPair && card.face === 'answer')!
    targetExpression.text = sourceExpression.text
    targetAnswer.text = sourceAnswer.text
    const threeFlipped = copy(base)
    threeFlipped.round.flipped = [0, 1, 2]
    const flippedMatched = copy(mid)
    const matchedPair = flippedMatched.round.matched[0]
    flippedMatched.round.flipped = flippedMatched.round.cards.filter(card => card.pairId === matchedPair).map(card => card.id)
    const unknownMatched = copy(base)
    unknownMatched.round.matched = ['p99']
    const unfinished = copy(finished)
    unfinished.round.finished = false
    const badBest = copy(finished)
    badBest.best.cozy = 1
    const badCardId = copy(base)
    badCardId.round.cards[0].id = 99
    for (const value of [
      null, 'broken', { ...base, version: 2 }, { ...base, difficulty: 'expert' },
      { ...base, round: { ...base.round, difficulty: 'focus' } }, badExpression, duplicated,
      threeFlipped, flippedMatched, unknownMatched, unfinished, badBest, badCardId,
      { ...base, rounds: -1 }, { ...base, totalMatches: 2.5 },
    ]) expect(restoreMemory(typeof value === 'string' ? value : JSON.stringify(value))).toBeNull()
  })
})
