import { randomInt, shuffle, type Rng } from './random'

export type { Rng } from './random'

export type RocketDifficulty = 'starter' | 'explorer' | 'pilot'
export type RocketOperator = '+' | '-' | '×'

export interface RocketQuestion {
  left: number
  right: number
  operator: RocketOperator
  expression: string
  answer: number
  options: number[]
}

export interface RocketFlight {
  version: 1
  difficulty: RocketDifficulty
  questions: RocketQuestion[]
  index: number
  correct: number
  mistakes: number
  streak: number
  bestStreak: number
  answered: number | null
  finished: boolean
}

export interface RocketSave {
  version: 1
  difficulty: RocketDifficulty
  flight: RocketFlight
  best: Record<RocketDifficulty, number>
  totalCorrect: number
  flights: number
}

export const ROCKET_QUESTIONS = 8
export const rocketDifficulties = [
  { id: 'starter' as const, name: '20 以内', detail: '加减法', age: '5-7 岁' },
  { id: 'explorer' as const, name: '100 以内', detail: '加减法', age: '7-9 岁' },
  { id: 'pilot' as const, name: '乘法口诀', detail: '2-9 乘法', age: '8-10 岁' },
]

export function isRocketDifficulty(value: unknown): value is RocketDifficulty {
  return value === 'starter' || value === 'explorer' || value === 'pilot'
}

function makeQuestion(difficulty: RocketDifficulty, rng: Rng, used: Set<string>): RocketQuestion {
  for (let attempt = 0; attempt < 80; attempt++) {
    let left: number
    let right: number
    let operator: RocketOperator
    let maxAnswer: number
    if (difficulty === 'starter') {
      operator = rng() < 0.5 ? '+' : '-'
      maxAnswer = 20
      if (operator === '+') {
        left = randomInt(rng, 1, 10)
        right = randomInt(rng, 1, 20 - left)
      } else {
        left = randomInt(rng, 2, 20)
        right = randomInt(rng, 1, left - 1)
      }
    } else if (difficulty === 'explorer') {
      operator = rng() < 0.5 ? '+' : '-'
      maxAnswer = 100
      if (operator === '+') {
        left = randomInt(rng, 10, 70)
        right = randomInt(rng, 5, 99 - left)
      } else {
        left = randomInt(rng, 30, 99)
        right = randomInt(rng, 5, left - 1)
      }
    } else {
      operator = '×'
      left = randomInt(rng, 2, 9)
      right = randomInt(rng, 2, 9)
      maxAnswer = 81
    }
    const answer = operator === '+' ? left + right : operator === '-' ? left - right : left * right
    const expression = `${left} ${operator} ${right}`
    if (used.has(expression)) continue
    used.add(expression)
    return { left, right, operator, expression, answer, options: buildOptions(answer, maxAnswer, operator, rng) }
  }
  throw new Error('口算题生成失败')
}

function buildOptions(answer: number, maxAnswer: number, operator: RocketOperator, rng: Rng): number[] {
  const candidates = new Set<number>()
  const offsets = operator === '×'
    ? [-2, -1, 1, 2, -9, 9, -10, 10]
    : [-1, 1, -2, 2, -9, 9, -10, 10]
  for (const offset of offsets) {
    const value = answer + offset
    if (value > 0 && value <= maxAnswer) candidates.add(value)
  }
  while (candidates.size < 3) candidates.add(randomInt(rng, 1, maxAnswer))
  return shuffle([answer, ...shuffle([...candidates], rng).slice(0, 3)], rng)
}

export function newFlight(difficulty: RocketDifficulty, rng: Rng = Math.random): RocketFlight {
  const used = new Set<string>()
  return {
    version: 1,
    difficulty,
    questions: Array.from({ length: ROCKET_QUESTIONS }, () => makeQuestion(difficulty, rng, used)),
    index: 0,
    correct: 0,
    mistakes: 0,
    streak: 0,
    bestStreak: 0,
    answered: null,
    finished: false,
  }
}

export function newRocket(difficulty: RocketDifficulty = 'starter', rng: Rng = Math.random): RocketSave {
  return {
    version: 1,
    difficulty,
    flight: newFlight(difficulty, rng),
    best: { starter: 0, explorer: 0, pilot: 0 },
    totalCorrect: 0,
    flights: 0,
  }
}

export function rocketStars(flight: Pick<RocketFlight, 'mistakes'>): number {
  return flight.mistakes === 0 ? 3 : flight.mistakes === 1 ? 2 : 1
}

export function answerRocket(save: RocketSave, value: number): boolean | null {
  const flight = save.flight
  if (flight.finished || flight.answered !== null) return null
  const question = flight.questions[flight.index]
  if (!question.options.includes(value)) return null
  flight.answered = value
  if (value === question.answer) {
    flight.correct++
    flight.streak++
    flight.bestStreak = Math.max(flight.bestStreak, flight.streak)
  } else {
    flight.mistakes++
    flight.streak = 0
  }
  return value === question.answer
}

export function advanceRocket(save: RocketSave): 'next' | 'finished' | null {
  const flight = save.flight
  if (flight.finished || flight.answered === null) return null
  if (flight.index < ROCKET_QUESTIONS - 1) {
    flight.index++
    flight.answered = null
    return 'next'
  }
  flight.finished = true
  flight.answered = null
  save.best[flight.difficulty] = Math.max(save.best[flight.difficulty], rocketStars(flight))
  save.totalCorrect += flight.correct
  save.flights++
  return 'finished'
}

export function restartRocket(save: RocketSave, rng: Rng = Math.random): void {
  save.flight = newFlight(save.difficulty, rng)
}

export function switchRocketDifficulty(save: RocketSave, difficulty: RocketDifficulty, rng: Rng = Math.random): void {
  save.difficulty = difficulty
  save.flight = newFlight(difficulty, rng)
}

function isInt(value: unknown, min: number, max: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max
}

function validQuestion(question: RocketQuestion): boolean {
  if (!question || !isInt(question.left, 0, 100) || !isInt(question.right, 0, 100)) return false
  if (!['+', '-', '×'].includes(question.operator)) return false
  const expected = question.operator === '+' ? question.left + question.right
    : question.operator === '-' ? question.left - question.right : question.left * question.right
  if (!isInt(question.answer, 1, 1000) || question.answer !== expected) return false
  if (question.expression !== `${question.left} ${question.operator} ${question.right}`) return false
  if (!Array.isArray(question.options) || question.options.length !== 4) return false
  if (!question.options.every(value => isInt(value, 1, 1000))) return false
  if (new Set(question.options).size !== 4 || !question.options.includes(question.answer)) return false
  return true
}

export function restoreRocket(raw: string | null): RocketSave | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as RocketSave
    if (!value || value.version !== 1 || !isRocketDifficulty(value.difficulty)) return null
    const best = value.best as unknown as Record<string, unknown>
    if (!best || !rocketDifficulties.every(item => isInt(best[item.id], 0, 3))) return null
    if (!isInt(value.totalCorrect, 0, 1_000_000) || !isInt(value.flights, 0, 1_000_000)) return null
    const flight = value.flight
    if (!flight || flight.version !== 1 || flight.difficulty !== value.difficulty) return null
    if (!Array.isArray(flight.questions) || flight.questions.length !== ROCKET_QUESTIONS) return null
    if (!flight.questions.every(validQuestion)) return null
    if (!isInt(flight.index, 0, ROCKET_QUESTIONS - 1) || typeof flight.finished !== 'boolean') return null
    if (!isInt(flight.correct, 0, ROCKET_QUESTIONS) || !isInt(flight.mistakes, 0, ROCKET_QUESTIONS)) return null
    if (!isInt(flight.streak, 0, ROCKET_QUESTIONS) || !isInt(flight.bestStreak, 0, ROCKET_QUESTIONS)) return null
    if (flight.bestStreak > flight.correct || flight.streak > flight.bestStreak) return null
    const question = flight.questions[flight.index]
    if (flight.answered !== null && (!isInt(flight.answered, 1, 1000) || !question.options.includes(flight.answered))) return null
    if (!flight.finished) {
      const answeredCount = flight.index + (flight.answered === null ? 0 : 1)
      if (flight.correct + flight.mistakes !== answeredCount) return null
    }
    if (flight.finished) {
      if (flight.index !== ROCKET_QUESTIONS - 1 || flight.answered !== null) return null
      if (flight.correct + flight.mistakes !== ROCKET_QUESTIONS) return null
      if ((best[value.difficulty] as number) < rocketStars(flight)) return null
    }
    return value
  } catch {
    return null
  }
}
