import { contentDeck, rememberContent, validContentHistory, validChallenge, type ContentHistory, type ChallengeRound } from './challenge-journey'
import { shuffle, type Rng } from './random'

export type FractionDifficulty = 'starter' | 'explorer' | 'master'
export type FractionMode = 'identify' | 'simplify' | 'complement' | 'compare'

export interface FractionQuestion {
  total: number
  shaded: number
  mode: FractionMode
  answer: string
  options: string[]
  other?: { total: number; shaded: number }
}

export interface FractionFlight extends ChallengeRound {
  version: 1
  difficulty: FractionDifficulty
  questions: FractionQuestion[]
  index: number
  correct: number
  mistakes: number
  answered: string | null
  finished: boolean
}

export interface FractionSave extends ContentHistory {
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
  { id: 'explorer' as const, name: '进阶', detail: '剩余部分 · 同分母比较', age: '7-9 岁' },
  { id: 'master' as const, name: '挑战', detail: '约分 · 不同分母比较', age: '8-10 岁' },
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
  if (['<', '=', '>'].includes(label)) return label === '<' ? '左边小于右边' : label === '>' ? '左边大于右边' : '两边一样多'
  const [numerator, denominator] = label.split('/').map(Number)
  return `${numberWord(denominator)}分之${numberWord(numerator)}`
}

export function fractionPrompt(mode: FractionMode): string {
  if (mode === 'compare') return '两张一样大的披萨，哪边的涂色部分更多？'
  if (mode === 'complement') return '还没涂色的部分占整张披萨的几分之几？'
  return mode === 'simplify' ? '涂色部分是多少？请选出最简分数。' : '涂色部分是这张披萨的几分之几？'
}

function questionPool(difficulty: FractionDifficulty, stage: number): Array<Omit<FractionQuestion,'options'>> {
  const pool: Array<Omit<FractionQuestion,'options'>> = []
  const limit = difficulty === 'starter' ? Math.min(8,5+Math.floor((stage-1)/2)) : difficulty === 'explorer' ? Math.min(12,8+Math.floor((stage-1)/2)) : Math.min(16,12+Math.floor((stage-1)/2))
  for (let total = 2; total <= limit; total++) for (let shaded = 1; shaded < total; shaded++) {
    const modes: FractionMode[] = difficulty === 'starter' ? (stage >= 3 ? ['identify','complement'] : ['identify']) : ['identify','complement','simplify','compare']
    for (const mode of modes) {
      if (mode === 'simplify' && gcd(shaded,total) === 1) continue
      if (mode === 'compare') {
        const denominators = difficulty === 'master' ? [total, Math.max(2,total-1)] : [total]
        for (const otherTotal of denominators) for (const otherShaded of new Set([Math.max(1,shaded-1), Math.min(otherTotal-1,shaded), Math.min(otherTotal-1,shaded+1)])) {
          const difference = shaded*otherTotal-otherShaded*total
          pool.push({total,shaded,mode,other:{total:otherTotal,shaded:otherShaded},answer:difference === 0 ? '=' : difference > 0 ? '>' : '<'})
        }
      } else pool.push({total,shaded,mode,answer:mode === 'simplify' ? simplifiedLabel(shaded,total) : fractionLabel(mode === 'complement' ? total-shaded : shaded,total)})
    }
  }
  return pool
}
const fractionKey = (q: FractionQuestion | Omit<FractionQuestion,'options'>) => `${q.mode}:${q.shaded}/${q.total}${q.other ? ':'+q.other.shaded+'/'+q.other.total : ''}`

function buildOptions(shaded: number, total: number, answer: string, rng: Rng): string[] {
  const limit = Math.max(12,total)
  const target = shaded / total
  const candidates = new Set<string>()
  function add(numerator: number, denominator: number): void {
    if (!Number.isInteger(numerator) || !Number.isInteger(denominator)) return
    if (denominator < 2 || denominator > limit || numerator < 1 || numerator >= denominator) return
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
  for (let denominator = 2; denominator <= limit && candidates.size < 3; denominator++) {
    for (let numerator = 1; numerator < denominator && candidates.size < 3; numerator++) add(numerator, denominator)
  }
  return shuffle([answer, ...shuffle([...candidates], rng).slice(0, 3)], rng)
}

export function newFlight(difficulty: FractionDifficulty, rng: Rng = Math.random, history: string[] = [], stage = 1): FractionFlight {
  const pool = questionPool(difficulty,stage), modes = [...new Set(pool.map(q=>q.mode))]
  const selected = modes.flatMap(mode=>contentDeck(pool.filter(q=>q.mode===mode),FRACTION_QUESTIONS/modes.length,fractionKey,history,rng))
  const questions = shuffle(selected,rng).map(q=>({...q,options:q.mode === 'compare' ? shuffle(['<','=','>'],rng) : buildOptions(q.mode === 'complement' ? q.total-q.shaded : q.shaded,q.total,q.answer,rng)}))
  return {
    version: 1,
    difficulty,
    questions, stage,
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
  const history = rememberContent(save,save.difficulty,save.flight.questions.map(fractionKey))
  save.flight = newFlight(save.difficulty, rng, history, save.flights+1)
}

export function switchFractionDifficulty(save: FractionSave, difficulty: FractionDifficulty, rng: Rng = Math.random): void {
  rememberContent(save,save.difficulty,save.flight.questions.map(fractionKey))
  save.difficulty = difficulty
  save.flight = newFlight(difficulty, rng, save.contentHistory?.[difficulty] || [], save.flights+1)
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
  return isInt(numerator, 1, 15) && isInt(denominator, 2, 16) && numerator < denominator
}

function validQuestion(question: FractionQuestion): boolean {
  if (!question || !isInt(question.total, 2, 16) || !isInt(question.shaded, 1, question.total - 1)) return false
  if (!['identify','simplify','complement','compare'].includes(question.mode)) return false
  if (question.mode === 'compare') {
    const other = question.other
    if (!other || !isInt(other.total,2,16) || !isInt(other.shaded,1,other.total-1)) return false
    const difference = question.shaded*other.total-other.shaded*question.total
    return question.answer === (difference === 0 ? '=' : difference > 0 ? '>' : '<') && Array.isArray(question.options) && question.options.length === 3 && new Set(question.options).size === 3 && question.options.every(value=>['<','=','>'].includes(value))
  }
  if (question.other !== undefined) return false
  const raw = fractionLabel(question.shaded, question.total)
  const simplified = simplifiedLabel(question.shaded, question.total)
  if (question.mode === 'simplify' && simplified === raw) return false
  const expected = question.mode === 'identify' ? raw : question.mode === 'complement' ? fractionLabel(question.total-question.shaded,question.total) : simplified
  if (question.answer !== expected) return false
  if (!Array.isArray(question.options) || question.options.length !== 4) return false
  if (!question.options.every(validLabel)) return false
  if (new Set(question.options).size !== 4 || !question.options.includes(question.answer)) return false
  const target = (question.mode === 'complement' ? question.total-question.shaded : question.shaded) / question.total
  return question.options.filter(label => Math.abs(fractionValue(label) - target) < 1e-9).length === 1
}

export function restoreFraction(raw: string | null): FractionSave | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as FractionSave
    if (!validContentHistory(value.contentHistory) || !value || value.version !== 1 || !isFractionDifficulty(value.difficulty)) return null
    const best = value.best as unknown as Record<string, unknown>
    if (!best || !fractionDifficulties.every(item => isInt(best[item.id], 0, 3))) return null
    if (!isInt(value.totalCorrect, 0, 1_000_000) || !isInt(value.flights, 0, 1_000_000)) return null
    const flight = value.flight
    if (!flight || !validChallenge(flight) || flight.version !== 1 || flight.difficulty !== value.difficulty) return null
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
