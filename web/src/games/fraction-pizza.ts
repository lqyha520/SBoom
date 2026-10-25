import { randomInt, shuffle, type Rng } from './random'

export type FractionDifficulty = 'starter' | 'explorer' | 'master'
export type FractionMode = 'identify' | 'simplify'

export interface FractionQuestion {
  total: number
  shaded: number
  mode: FractionMode
  answer: string
  options: string[]
}

export interface FractionFlight {
  version: 1
  difficulty: FractionDifficulty
  questions: FractionQuestion[]
  index: number
  correct: number
  mistakes: number
  answered: string | null
  finished: boolean
}

export interface FractionSave {
  version: 1
  difficulty: FractionDifficulty
  flight: FractionFlight
  best: Record<FractionDifficulty, number>
  totalCorrect: number
  flights: number
}

export const FRACTION_QUESTIONS = 8
export const fractionDifficulties = [
  { id: 'starter' as const, name: '初尝', detail: '2-5 等份', age: '6-8 岁' },
  { id: 'explorer' as const, name: '进阶', detail: '2-8 等份', age: '7-9 岁' },
  { id: 'master' as const, name: '挑战', detail: '最简分数', age: '8-10 岁' },
]

export function isFractionDifficulty(value: unknown): value is FractionDifficulty {
  return value === 'starter' || value === 'explorer' || value === 'master'
}

export function gcd(left: number, right: number): number {
  let a = Math.abs(left)
  let b = Math.abs(right)
  while (b) [a, b] = [b, a % b]
  return a || 1
}

export function fractionLabel(numerator: number, denominator: number): string {
  return `${numerator}/${denominator}`
}

export function fractionValue(label: string): number {
  const [numerator, denominator] = label.split('/').map(Number)
  return numerator / denominator
}

function simplifiedLabel(numerator: number, denominator: number): string {
  const divisor = gcd(numerator, denominator)
  return fractionLabel(numerator / divisor, denominator / divisor)
}

const digitWords = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九']

function numberWord(value: number): string {
  if (value < 10) return digitWords[value]
  if (value === 10) return '十'
  if (value < 20) return `十${digitWords[value - 10]}`
  const rest = value % 10
  return `${digitWords[Math.floor(value / 10)]}十${rest ? digitWords[rest] : ''}`
}

export function fractionReading(label: string): string {
  const [numerator, denominator] = label.split('/').map(Number)
  return `${numberWord(denominator)}分之${numberWord(numerator)}`
}

export function fractionPrompt(mode: FractionMode): string {
  return mode === 'simplify' ? '涂色部分是多少？请选出最简分数。' : '涂色部分是这张披萨的几分之几？'
}

function makeQuestion(difficulty: FractionDifficulty, rng: Rng, used: Set<string>): FractionQuestion {
  for (let attempt = 0; attempt < 200; attempt++) {
    let total: number
    let mode: FractionMode
    if (difficulty === 'starter') {
      total = randomInt(rng, 2, 5)
      mode = 'identify'
    } else if (difficulty === 'explorer') {
      total = randomInt(rng, 2, 8)
      mode = rng() < 0.4 ? 'simplify' : 'identify'
    } else {
      total = [4, 6, 8, 9, 10, 12][randomInt(rng, 0, 5)]
      mode = 'simplify'
    }
    const shaded = randomInt(rng, 1, total - 1)
    if (mode === 'simplify' && gcd(shaded, total) === 1) continue
    const key = `${mode}:${shaded}/${total}`
    if (used.has(key)) continue
    const raw = fractionLabel(shaded, total)
    const answer = mode === 'identify' ? raw : simplifiedLabel(shaded, total)
    if (mode === 'simplify' && answer === raw) continue
    used.add(key)
    return { total, shaded, mode, answer, options: buildOptions(shaded, total, answer, rng) }
  }
  throw new Error('分数题生成失败')
}

function buildOptions(shaded: number, total: number, answer: string, rng: Rng): string[] {
  const target = shaded / total
  const candidates = new Set<string>()
  function add(numerator: number, denominator: number): void {
    if (!Number.isInteger(numerator) || !Number.isInteger(denominator)) return
    if (denominator < 2 || denominator > 12 || numerator < 1 || numerator >= denominator) return
    const label = fractionLabel(numerator, denominator)
    if (label === answer) return
    if (Math.abs(numerator / denominator - target) < 1e-9) return
    candidates.add(label)
  }
  add(shaded - 1, total)
  add(shaded + 1, total)
  add(total - shaded, total)
  add(shaded, total - 1)
  add(shaded, total + 1)
  add(shaded - 1, total - 1)
  add(shaded + 1, total - 1)
  while (candidates.size < 3) add(randomInt(rng, 1, 11), randomInt(rng, 2, 12))
  for (let denominator = 2; denominator <= 12 && candidates.size < 3; denominator++) {
    for (let numerator = 1; numerator < denominator && candidates.size < 3; numerator++) add(numerator, denominator)
  }
  return shuffle([answer, ...shuffle([...candidates], rng).slice(0, 3)], rng)
}

export function newFlight(difficulty: FractionDifficulty, rng: Rng = Math.random): FractionFlight {
  const used = new Set<string>()
  return {
    version: 1,
    difficulty,
    questions: Array.from({ length: FRACTION_QUESTIONS }, () => makeQuestion(difficulty, rng, used)),
    index: 0,
    correct: 0,
    mistakes: 0,
    answered: null,
    finished: false,
  }
}

export function newFraction(difficulty: FractionDifficulty = 'starter', rng: Rng = Math.random): FractionSave {
  return {
    version: 1,
    difficulty,
    flight: newFlight(difficulty, rng),
    best: { starter: 0, explorer: 0, master: 0 },
    totalCorrect: 0,
    flights: 0,
  }
}

export function fractionStars(flight: Pick<FractionFlight, 'mistakes'>): number {
  return flight.mistakes === 0 ? 3 : flight.mistakes === 1 ? 2 : 1
}

export function answerFraction(save: FractionSave, value: string): boolean | null {
  const flight = save.flight
  if (flight.finished || flight.answered !== null) return null
  const question = flight.questions[flight.index]
  if (!question.options.includes(value)) return null
  flight.answered = value
  if (value === question.answer) {
    flight.correct++
  } else {
    flight.mistakes++
  }
  return value === question.answer
}

export function advanceFraction(save: FractionSave): 'next' | 'finished' | null {
  const flight = save.flight
  if (flight.finished || flight.answered === null) return null
  if (flight.index < FRACTION_QUESTIONS - 1) {
    flight.index++
    flight.answered = null
    return 'next'
  }
  flight.finished = true
  flight.answered = null
  save.best[flight.difficulty] = Math.max(save.best[flight.difficulty], fractionStars(flight))
  save.totalCorrect += flight.correct
  save.flights++
  return 'finished'
}

export function restartFraction(save: FractionSave, rng: Rng = Math.random): void {
  save.flight = newFlight(save.difficulty, rng)
}

export function switchFractionDifficulty(save: FractionSave, difficulty: FractionDifficulty, rng: Rng = Math.random): void {
  save.difficulty = difficulty
  save.flight = newFlight(difficulty, rng)
}

function isInt(value: unknown, min: number, max: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max
}

function validLabel(label: unknown): label is string {
  if (typeof label !== 'string') return false
  const match = /^(\d{1,2})\/(\d{1,2})$/.exec(label)
  if (!match) return false
  const numerator = Number(match[1])
  const denominator = Number(match[2])
  return isInt(numerator, 1, 11) && isInt(denominator, 2, 12) && numerator < denominator
}

function validQuestion(question: FractionQuestion): boolean {
  if (!question || !isInt(question.total, 2, 12) || !isInt(question.shaded, 1, question.total - 1)) return false
  if (question.mode !== 'identify' && question.mode !== 'simplify') return false
  const raw = fractionLabel(question.shaded, question.total)
  const simplified = simplifiedLabel(question.shaded, question.total)
  if (question.mode === 'simplify' && simplified === raw) return false
  const expected = question.mode === 'identify' ? raw : simplified
  if (question.answer !== expected) return false
  if (!Array.isArray(question.options) || question.options.length !== 4) return false
  if (!question.options.every(validLabel)) return false
  if (new Set(question.options).size !== 4 || !question.options.includes(question.answer)) return false
  const target = question.shaded / question.total
  return question.options.filter(label => Math.abs(fractionValue(label) - target) < 1e-9).length === 1
}

export function restoreFraction(raw: string | null): FractionSave | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as FractionSave
    if (!value || value.version !== 1 || !isFractionDifficulty(value.difficulty)) return null
    const best = value.best as unknown as Record<string, unknown>
    if (!best || !fractionDifficulties.every(item => isInt(best[item.id], 0, 3))) return null
    if (!isInt(value.totalCorrect, 0, 1_000_000) || !isInt(value.flights, 0, 1_000_000)) return null
    const flight = value.flight
    if (!flight || flight.version !== 1 || flight.difficulty !== value.difficulty) return null
    if (!Array.isArray(flight.questions) || flight.questions.length !== FRACTION_QUESTIONS) return null
    if (!flight.questions.every(validQuestion)) return null
    if (!isInt(flight.index, 0, FRACTION_QUESTIONS - 1) || typeof flight.finished !== 'boolean') return null
    if (!isInt(flight.correct, 0, FRACTION_QUESTIONS) || !isInt(flight.mistakes, 0, FRACTION_QUESTIONS)) return null
    const question = flight.questions[flight.index]
    if (flight.answered !== null && (typeof flight.answered !== 'string' || !question.options.includes(flight.answered))) return null
    if (!flight.finished) {
      const answeredCount = flight.index + (flight.answered === null ? 0 : 1)
      if (flight.correct + flight.mistakes !== answeredCount) return null
    }
    if (flight.finished) {
      if (flight.index !== FRACTION_QUESTIONS - 1 || flight.answered !== null) return null
      if (flight.correct + flight.mistakes !== FRACTION_QUESTIONS) return null
      if ((best[value.difficulty] as number) < fractionStars(flight)) return null
    }
    return value
  } catch {
    return null
  }
}
