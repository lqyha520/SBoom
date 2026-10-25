import { englishDifficulties, englishWord, englishWords, isEnglishTier, type EnglishTier } from './english-words'
import { randomInt, shuffle, type Rng } from './random'

export type MarketDifficulty = EnglishTier

export interface MarketQuestion {
  wordId: string
  options: string[]
}

export interface MarketRound {
  version: 1
  difficulty: MarketDifficulty
  questions: MarketQuestion[]
  index: number
  correct: number
  mistakes: number
  answered: string | null
  finished: boolean
}

export interface MarketSave {
  version: 1
  difficulty: MarketDifficulty
  round: MarketRound
  best: Record<MarketDifficulty, number>
  totalCorrect: number
  rounds: number
}

export const MARKET_QUESTIONS = 8
export { englishDifficulties as marketDifficulties }

export function isMarketDifficulty(value: unknown): value is MarketDifficulty {
  return isEnglishTier(value)
}

export function newMarketRound(difficulty: MarketDifficulty, rng: Rng = Math.random): MarketRound {
  const pool = englishWords[difficulty]
  const used = new Set<string>()
  const questions: MarketQuestion[] = []
  for (let index = 0; index < MARKET_QUESTIONS; index++) {
    const available = pool.filter(item => !used.has(item.word))
    const item = available[randomInt(rng, 0, available.length - 1)]
    used.add(item.word)
    const distractors = shuffle(pool.filter(candidate => candidate.word !== item.word), rng)
      .slice(0, 3)
      .map(candidate => candidate.word)
    questions.push({ wordId: item.word, options: shuffle([item.word, ...distractors], rng) })
  }
  return {
    version: 1,
    difficulty,
    questions,
    index: 0,
    correct: 0,
    mistakes: 0,
    answered: null,
    finished: false,
  }
}

export function newMarket(difficulty: MarketDifficulty = 'starter', rng: Rng = Math.random): MarketSave {
  return {
    version: 1,
    difficulty,
    round: newMarketRound(difficulty, rng),
    best: { starter: 0, explorer: 0, master: 0 },
    totalCorrect: 0,
    rounds: 0,
  }
}

export function marketStars(round: Pick<MarketRound, 'mistakes'>): number {
  return round.mistakes === 0 ? 3 : round.mistakes === 1 ? 2 : 1
}

export function answerMarket(save: MarketSave, word: string): boolean | null {
  const round = save.round
  if (round.finished || round.answered !== null) return null
  const question = round.questions[round.index]
  if (!question.options.includes(word)) return null
  round.answered = word
  if (word === question.wordId) round.correct++
  else round.mistakes++
  return word === question.wordId
}

export function advanceMarket(save: MarketSave): 'next' | 'finished' | null {
  const round = save.round
  if (round.finished || round.answered === null) return null
  if (round.index < MARKET_QUESTIONS - 1) {
    round.index++
    round.answered = null
    return 'next'
  }
  round.finished = true
  round.answered = null
  save.best[round.difficulty] = Math.max(save.best[round.difficulty], marketStars(round))
  save.totalCorrect += round.correct
  save.rounds++
  return 'finished'
}

export function restartMarket(save: MarketSave, rng: Rng = Math.random): void {
  save.round = newMarketRound(save.difficulty, rng)
}

export function switchMarketDifficulty(save: MarketSave, difficulty: MarketDifficulty, rng: Rng = Math.random): void {
  save.difficulty = difficulty
  save.round = newMarketRound(difficulty, rng)
}

function isInt(value: unknown, min: number, max: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max
}

function validQuestion(question: MarketQuestion, difficulty: MarketDifficulty): boolean {
  const source = englishWord(difficulty, question?.wordId)
  if (!source) return false
  if (!Array.isArray(question.options) || question.options.length !== 4) return false
  if (!question.options.every(word => typeof word === 'string')) return false
  if (new Set(question.options).size !== 4 || !question.options.includes(source.word)) return false
  return question.options.every(word => englishWord(difficulty, word) !== undefined)
}

export function restoreMarket(raw: string | null): MarketSave | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as MarketSave
    if (!value || value.version !== 1 || !isMarketDifficulty(value.difficulty)) return null
    const best = value.best as unknown as Record<string, unknown>
    if (!best || !englishDifficulties.every(item => isInt(best[item.id], 0, 3))) return null
    if (!isInt(value.totalCorrect, 0, 1_000_000) || !isInt(value.rounds, 0, 1_000_000)) return null
    const round = value.round
    if (!round || round.version !== 1 || round.difficulty !== value.difficulty) return null
    if (!Array.isArray(round.questions) || round.questions.length !== MARKET_QUESTIONS) return null
    if (!round.questions.every(question => validQuestion(question, value.difficulty))) return null
    if (new Set(round.questions.map(question => question.wordId)).size !== MARKET_QUESTIONS) return null
    if (!isInt(round.index, 0, MARKET_QUESTIONS - 1) || typeof round.finished !== 'boolean') return null
    if (!isInt(round.correct, 0, MARKET_QUESTIONS) || !isInt(round.mistakes, 0, MARKET_QUESTIONS)) return null
    const question = round.questions[round.index]
    if (round.answered !== null && (typeof round.answered !== 'string' || !question.options.includes(round.answered))) return null
    if (!round.finished) {
      const answeredCount = round.index + (round.answered === null ? 0 : 1)
      if (round.correct + round.mistakes !== answeredCount) return null
    }
    if (round.finished) {
      if (round.index !== MARKET_QUESTIONS - 1 || round.answered !== null) return null
      if (round.correct + round.mistakes !== MARKET_QUESTIONS) return null
      if ((best[value.difficulty] as number) < marketStars(round)) return null
    }
    return value
  } catch {
    return null
  }
}
