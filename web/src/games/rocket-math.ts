import { contentDeck, rememberContent, validContentHistory, type ContentHistory } from './challenge-journey'
import { shuffle, type Rng } from './random'

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

export interface RocketSave extends ContentHistory {
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

function questionPool(difficulty: RocketDifficulty): Array<Omit<RocketQuestion,'options'>> {
  const pool: Array<Omit<RocketQuestion,'options'>> = []
  const max = difficulty === 'starter' ? 20 : difficulty === 'explorer' ? 99 : 9
  for (let left = difficulty === 'pilot' ? 2 : 1; left <= max; left++) for (let right = difficulty === 'pilot' ? 2 : 1; right <= max; right++) {
    const operators: RocketOperator[] = difficulty === 'pilot' ? ['×'] : ['+','-']
    for (const operator of operators) {
      const answer = operator === '+' ? left+right : operator === '-' ? left-right : left*right
      if (answer < 1 || (operator !== '×' && answer > max)) continue
      pool.push({left,right,operator,answer,expression:`${left} ${operator} ${right}`})
    }
  }
  return pool
}

export function rocketExplanation(question: RocketQuestion): string {
  const {left,right,operator,answer} = question
  if (operator === '×') return `每组 ${left} 个，共 ${right} 组：${left} × ${right} = ${answer}。也可以用 ${left} × ${right-1} + ${left} = ${answer} 检查。`
  if (operator === '+') {
    const bridge = Math.ceil(left/10)*10-left
    if (bridge > 0 && right > bridge) return `先凑整十：${left} + ${bridge} = ${left+bridge}，再加剩下的 ${right-bridge}，得到 ${answer}。`
    return `${left} 和 ${right} 合起来是 ${answer}，用 ${answer} − ${right} = ${left} 检查。`
  }
  const ones = left%10
  if (right > ones && ones > 0) return `先减 ${ones} 到整十 ${left-ones}，再减剩下的 ${right-ones}，得到 ${answer}。`
  return `从 ${left} 去掉 ${right}，剩下 ${answer}；用 ${answer} + ${right} = ${left} 检查。`
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
  for (let value = 1; candidates.size < 3 && value <= maxAnswer; value++) if (value !== answer) candidates.add(value)
  return shuffle([answer, ...shuffle([...candidates], rng).slice(0, 3)], rng)
}

export function newFlight(difficulty: RocketDifficulty, rng: Rng = Math.random, history: string[] = []): RocketFlight {
  const pool = questionPool(difficulty)
  const selected = difficulty === 'pilot' ? contentDeck(pool,ROCKET_QUESTIONS,q=>q.expression,history,rng) : ['+','-'].flatMap(operator=>contentDeck(pool.filter(q=>q.operator===operator),ROCKET_QUESTIONS/2,q=>q.expression,history,rng))
  const questions = shuffle(selected,rng).map(q=>({...q,options:buildOptions(q.answer,difficulty === 'starter' ? 20 : difficulty === 'explorer' ? 100 : 81,q.operator,rng)}))
  return {
    version: 1,
    difficulty,
    questions,
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
  const id = save.difficulty === 'pilot' ? 'master' : save.difficulty
  const history = rememberContent(save,id,save.flight.questions.map(q=>q.expression))
  save.flight = newFlight(save.difficulty, rng, history)
}

export function switchRocketDifficulty(save: RocketSave, difficulty: RocketDifficulty, rng: Rng = Math.random): void {
  rememberContent(save,save.difficulty === 'pilot' ? 'master' : save.difficulty,save.flight.questions.map(q=>q.expression))
  save.difficulty = difficulty
  save.flight = newFlight(difficulty, rng, save.contentHistory?.[difficulty === 'pilot' ? 'master' : difficulty] || [])
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
    if (!validContentHistory(value.contentHistory) || !value || value.version !== 1 || !isRocketDifficulty(value.difficulty)) return null
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
