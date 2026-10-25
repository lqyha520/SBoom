import { randomInt, shuffle, type Rng } from './random'

export type MemoryDifficulty = 'cozy' | 'focus' | 'master'
export type MemoryFace = 'expression' | 'answer'
export type FlipResult = 'ignored' | 'first' | 'matched' | 'mismatch'
export type ResolveResult = 'none' | 'resolved' | 'finished'

export interface MemoryCard {
  id: number
  pairId: string
  face: MemoryFace
  text: string
}

export interface MemoryRound {
  version: 1
  difficulty: MemoryDifficulty
  cards: MemoryCard[]
  flipped: number[]
  matched: string[]
  moves: number
  finished: boolean
}

export interface MemorySave {
  version: 1
  difficulty: MemoryDifficulty
  round: MemoryRound
  best: Record<MemoryDifficulty, number>
  totalMatches: number
  rounds: number
}

interface MemoryConfig {
  name: string
  detail: string
  pairs: number
  columns: number
  age: string
}

const configs: Record<MemoryDifficulty, MemoryConfig> = {
  cozy: { name: '轻松', detail: '6 对 · 10 以内', pairs: 6, columns: 4, age: '5-7 岁' },
  focus: { name: '专注', detail: '8 对 · 20 以内', pairs: 8, columns: 4, age: '7-9 岁' },
  master: { name: '挑战', detail: '10 对 · 乘法', pairs: 10, columns: 5, age: '8-10 岁' },
}

export const memoryDifficulties = (['cozy', 'focus', 'master'] as const).map(id => ({ id, ...configs[id] }))

export function memoryConfigFor(difficulty: MemoryDifficulty): MemoryConfig {
  return configs[difficulty]
}

export function isMemoryDifficulty(value: unknown): value is MemoryDifficulty {
  return value === 'cozy' || value === 'focus' || value === 'master'
}

function makePairs(difficulty: MemoryDifficulty, rng: Rng): Array<{ expression: string; answer: number }> {
  const pairs: Array<{ expression: string; answer: number }> = []
  const answers = new Set<number>()
  const limit = difficulty === 'cozy' ? 10 : 20
  for (let attempt = 0; attempt < 1000 && pairs.length < configs[difficulty].pairs; attempt++) {
    if (difficulty === 'master') {
      const left = randomInt(rng, 2, 9)
      const right = randomInt(rng, 2, 9)
      const answer = left * right
      if (answers.has(answer)) continue
      answers.add(answer)
      pairs.push({ expression: `${left} × ${right}`, answer })
      continue
    }
    const answer = randomInt(rng, 1, limit)
    if (answers.has(answer)) continue
    let expression: string
    if (rng() < 0.5) {
      const left = answer > 1 ? randomInt(rng, 1, answer - 1) : 0
      expression = `${left} + ${answer - left}`
    } else {
      if (answer >= limit) continue
      const left = randomInt(rng, answer + 1, limit)
      expression = `${left} - ${left - answer}`
    }
    answers.add(answer)
    pairs.push({ expression, answer })
  }
  if (pairs.length !== configs[difficulty].pairs) throw new Error('记忆配对牌生成失败')
  return pairs
}

export function newMemoryRound(difficulty: MemoryDifficulty = 'cozy', rng: Rng = Math.random): MemoryRound {
  const deck = makePairs(difficulty, rng).flatMap<Omit<MemoryCard, 'id'>>((pair, index) => [
    { pairId: `p${index}`, face: 'expression', text: pair.expression },
    { pairId: `p${index}`, face: 'answer', text: String(pair.answer) },
  ])
  const cards = shuffle(deck, rng).map((card, index) => ({ ...card, id: index }))
  return { version: 1, difficulty, cards, flipped: [], matched: [], moves: 0, finished: false }
}

export function newMemory(difficulty: MemoryDifficulty = 'cozy', rng: Rng = Math.random): MemorySave {
  return {
    version: 1,
    difficulty,
    round: newMemoryRound(difficulty, rng),
    best: { cozy: 0, focus: 0, master: 0 },
    totalMatches: 0,
    rounds: 0,
  }
}

export function flipMemoryCard(round: MemoryRound, cardId: number): FlipResult {
  const card = round.cards[cardId]
  if (!card || round.finished || round.flipped.length >= 2) return 'ignored'
  if (round.flipped.includes(cardId) || round.matched.includes(card.pairId)) return 'ignored'
  round.flipped.push(cardId)
  if (round.flipped.length < 2) return 'first'
  round.moves++
  return round.cards[round.flipped[0]].pairId === card.pairId ? 'matched' : 'mismatch'
}

export function resolveMemoryRound(round: MemoryRound): ResolveResult {
  if (round.flipped.length !== 2) return 'none'
  const first = round.cards[round.flipped[0]]
  const second = round.cards[round.flipped[1]]
  if (first.pairId === second.pairId && !round.matched.includes(first.pairId)) {
    round.matched.push(first.pairId)
  }
  round.flipped = []
  if (round.matched.length === round.cards.length / 2) {
    round.finished = true
    return 'finished'
  }
  return 'resolved'
}

export function memoryStars(round: Pick<MemoryRound, 'moves' | 'cards'>): number {
  const pairs = round.cards.length / 2
  if (round.moves <= pairs + 2) return 3
  if (round.moves <= Math.ceil(pairs * 1.8)) return 2
  return 1
}

export function resolveMemory(save: MemorySave): ResolveResult {
  const result = resolveMemoryRound(save.round)
  if (result !== 'finished') return result
  save.best[save.difficulty] = Math.max(save.best[save.difficulty], memoryStars(save.round))
  save.totalMatches += save.round.cards.length / 2
  save.rounds++
  return result
}

export function restartMemory(save: MemorySave, rng: Rng = Math.random): void {
  save.round = newMemoryRound(save.difficulty, rng)
}

export function switchMemoryDifficulty(save: MemorySave, difficulty: MemoryDifficulty, rng: Rng = Math.random): void {
  save.difficulty = difficulty
  save.round = newMemoryRound(difficulty, rng)
}

function isInt(value: unknown, min: number, max: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max
}

function parseExpression(text: unknown): number | null {
  if (typeof text !== 'string') return null
  const match = /^(\d{1,2}) ([+×-]) (\d{1,2})$/.exec(text)
  if (!match) return null
  const left = Number(match[1])
  const right = Number(match[3])
  if (match[2] === '+') return left + right
  if (match[2] === '-') return left > right ? left - right : null
  return left * right
}

export function restoreMemory(raw: string | null): MemorySave | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as MemorySave
    if (!value || value.version !== 1 || !isMemoryDifficulty(value.difficulty)) return null
    const best = value.best as unknown as Record<string, unknown>
    if (!best || !(['cozy', 'focus', 'master'] as const).every(id => isInt(best[id], 0, 3))) return null
    if (!isInt(value.totalMatches, 0, 1_000_000) || !isInt(value.rounds, 0, 1_000_000)) return null
    const round = value.round
    if (!round || round.version !== 1 || round.difficulty !== value.difficulty) return null
    const pairs = configs[value.difficulty].pairs
    if (!Array.isArray(round.cards) || round.cards.length !== pairs * 2) return null
    if (!round.cards.every((card, index) => card && card.id === index
      && typeof card.pairId === 'string' && (card.face === 'expression' || card.face === 'answer')
      && typeof card.text === 'string' && card.text.length > 0 && card.text.length <= 12)) return null
    const pairCards = new Map<string, MemoryCard[]>()
    for (const card of round.cards) {
      const list = pairCards.get(card.pairId) ?? []
      list.push(card)
      pairCards.set(card.pairId, list)
    }
    if (pairCards.size !== pairs) return null
    const answers = new Set<number>()
    for (const cards of pairCards.values()) {
      if (cards.length !== 2) return null
      const expression = cards.find(card => card.face === 'expression')
      const answer = cards.find(card => card.face === 'answer')
      if (!expression || !answer || !/^\d{1,3}$/.test(answer.text)) return null
      const expected = parseExpression(expression.text)
      const answerValue = Number(answer.text)
      if (expected === null || expected !== answerValue) return null
      if (value.difficulty === 'master' ? !expression.text.includes('×') : expression.text.includes('×')) return null
      const max = value.difficulty === 'cozy' ? 10 : value.difficulty === 'focus' ? 20 : 81
      if (!isInt(answerValue, 1, max) || answers.has(answerValue)) return null
      answers.add(answerValue)
    }
    if (!Array.isArray(round.flipped) || round.flipped.length > 2) return null
    if (!round.flipped.every(id => isInt(id, 0, round.cards.length - 1))) return null
    if (new Set(round.flipped).size !== round.flipped.length) return null
    if (!Array.isArray(round.matched) || new Set(round.matched).size !== round.matched.length) return null
    if (!round.matched.every(id => pairCards.has(id))) return null
    if (round.flipped.some(id => round.matched.includes(round.cards[id].pairId))) return null
    if (!isInt(round.moves, 0, 100_000) || typeof round.finished !== 'boolean') return null
    if (round.finished) {
      if (round.matched.length !== pairs || round.flipped.length !== 0 || round.moves < pairs) return null
      if ((best[value.difficulty] as number) < memoryStars(round)) return null
    } else if (round.matched.length === pairs) return null
    return value
  } catch {
    return null
  }
}
