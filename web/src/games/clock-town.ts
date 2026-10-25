import { randomInt, shuffle, type Rng } from './random'

export type ClockDifficulty = 'starter' | 'explorer' | 'master'

export interface ClockQuestion {
  hour: number
  minute: number
  answer: string
  options: string[]
}

export interface ClockRound {
  version: 1
  difficulty: ClockDifficulty
  questions: ClockQuestion[]
  index: number
  correct: number
  mistakes: number
  answered: string | null
  finished: boolean
}

export interface ClockSave {
  version: 1
  difficulty: ClockDifficulty
  round: ClockRound
  best: Record<ClockDifficulty, number>
  totalCorrect: number
  rounds: number
}

export const CLOCK_QUESTIONS = 8

export const clockDifficulties = [
  { id: 'starter' as const, name: '整点', detail: '认识整点', age: '5-7 岁' },
  { id: 'explorer' as const, name: '一刻', detail: '半点与一刻', age: '7-9 岁' },
  { id: 'master' as const, name: '五分钟', detail: '每 5 分钟', age: '8-10 岁' },
]

export function isClockDifficulty(value: unknown): value is ClockDifficulty {
  return value === 'starter' || value === 'explorer' || value === 'master'
}

export function formatClock(hour: number, minute: number): string {
  return `${hour}:${String(minute).padStart(2, '0')}`
}

function allowedMinutes(difficulty: ClockDifficulty): number[] {
  if (difficulty === 'starter') return [0]
  if (difficulty === 'explorer') return [0, 15, 30, 45]
  return Array.from({ length: 12 }, (_, index) => index * 5)
}

function buildOptions(hour: number, minute: number, difficulty: ClockDifficulty, rng: Rng): string[] {
  const minutes = allowedMinutes(difficulty)
  const answer = formatClock(hour, minute)
  const candidates = new Set<string>()
  const nextHour = (value: number) => ((value - 1 + 12) % 12) + 1
  function add(candidateHour: number, candidateMinute: number): void {
    if (!minutes.includes(candidateMinute)) return
    const label = formatClock(nextHour(candidateHour), candidateMinute)
    if (label !== answer) candidates.add(label)
  }
  add(hour + 1, minute)
  add(hour - 1, minute)
  add(hour + 2, minute)
  for (const candidate of shuffle(minutes, rng)) add(hour, candidate)
  add(hour + 1, minute + 15)
  add(hour - 1, minute - 15)
  while (candidates.size < 3) add(randomInt(rng, 1, 12), minutes[randomInt(rng, 0, minutes.length - 1)])
  return shuffle([answer, ...shuffle([...candidates], rng).slice(0, 3)], rng)
}

export function newClockRound(difficulty: ClockDifficulty, rng: Rng = Math.random): ClockRound {
  const minutes = allowedMinutes(difficulty)
  const times = shuffle(
    Array.from({ length: 12 }, (_, index) => index + 1).flatMap(hour => minutes.map(minute => ({ hour, minute }))),
    rng,
  ).slice(0, CLOCK_QUESTIONS)
  const questions = times.map(({ hour, minute }) => ({
    hour,
    minute,
    answer: formatClock(hour, minute),
    options: buildOptions(hour, minute, difficulty, rng),
  }))
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

export function newClock(difficulty: ClockDifficulty = 'starter', rng: Rng = Math.random): ClockSave {
  return {
    version: 1,
    difficulty,
    round: newClockRound(difficulty, rng),
    best: { starter: 0, explorer: 0, master: 0 },
    totalCorrect: 0,
    rounds: 0,
  }
}

export function clockStars(round: Pick<ClockRound, 'mistakes'>): number {
  return round.mistakes === 0 ? 3 : round.mistakes === 1 ? 2 : 1
}

export function clockExplanation(question: Pick<ClockQuestion, 'hour' | 'minute' | 'answer'>): string {
  if (question.minute === 0) return `分针指向 12，时针指向 ${question.hour}，是 ${question.answer}。`
  const nextHour = (question.hour % 12) + 1
  return `时针在 ${question.hour} 和 ${nextHour} 之间，分针指向 ${question.minute / 5}，是 ${question.answer}。`
}

export function answerClock(save: ClockSave, value: string): boolean | null {
  const round = save.round
  if (round.finished || round.answered !== null) return null
  const question = round.questions[round.index]
  if (!question.options.includes(value)) return null
  round.answered = value
  if (value === question.answer) round.correct++
  else round.mistakes++
  return value === question.answer
}

export function advanceClock(save: ClockSave): 'next' | 'finished' | null {
  const round = save.round
  if (round.finished || round.answered === null) return null
  if (round.index < CLOCK_QUESTIONS - 1) {
    round.index++
    round.answered = null
    return 'next'
  }
  round.finished = true
  round.answered = null
  save.best[round.difficulty] = Math.max(save.best[round.difficulty], clockStars(round))
  save.totalCorrect += round.correct
  save.rounds++
  return 'finished'
}

export function restartClock(save: ClockSave, rng: Rng = Math.random): void {
  save.round = newClockRound(save.difficulty, rng)
}

export function switchClockDifficulty(save: ClockSave, difficulty: ClockDifficulty, rng: Rng = Math.random): void {
  save.difficulty = difficulty
  save.round = newClockRound(difficulty, rng)
}

function isInt(value: unknown, min: number, max: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max
}

function parseClock(label: unknown): { hour: number; minute: number } | null {
  if (typeof label !== 'string') return null
  const match = /^([1-9]|1[0-2]):([0-5]\d)$/.exec(label)
  if (!match) return null
  return { hour: Number(match[1]), minute: Number(match[2]) }
}

function validQuestion(question: ClockQuestion, difficulty: ClockDifficulty): boolean {
  if (!question || !isInt(question.hour, 1, 12) || !isInt(question.minute, 0, 55)) return false
  if (!allowedMinutes(difficulty).includes(question.minute)) return false
  if (question.answer !== formatClock(question.hour, question.minute)) return false
  if (!Array.isArray(question.options) || question.options.length !== 4) return false
  if (!question.options.every(option => parseClock(option) !== null)) return false
  if (new Set(question.options).size !== 4 || !question.options.includes(question.answer)) return false
  return question.options.every(option => allowedMinutes(difficulty).includes(parseClock(option)!.minute))
}

export function restoreClock(raw: string | null): ClockSave | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as ClockSave
    if (!value || value.version !== 1 || !isClockDifficulty(value.difficulty)) return null
    const best = value.best as unknown as Record<string, unknown>
    if (!best || !clockDifficulties.every(item => isInt(best[item.id], 0, 3))) return null
    if (!isInt(value.totalCorrect, 0, 1_000_000) || !isInt(value.rounds, 0, 1_000_000)) return null
    const round = value.round
    if (!round || round.version !== 1 || round.difficulty !== value.difficulty) return null
    if (!Array.isArray(round.questions) || round.questions.length !== CLOCK_QUESTIONS) return null
    if (!round.questions.every(question => validQuestion(question, value.difficulty))) return null
    if (new Set(round.questions.map(question => question.answer)).size !== CLOCK_QUESTIONS) return null
    if (!isInt(round.index, 0, CLOCK_QUESTIONS - 1) || typeof round.finished !== 'boolean') return null
    if (!isInt(round.correct, 0, CLOCK_QUESTIONS) || !isInt(round.mistakes, 0, CLOCK_QUESTIONS)) return null
    const question = round.questions[round.index]
    if (round.answered !== null && (typeof round.answered !== 'string' || !question.options.includes(round.answered))) return null
    if (!round.finished) {
      const answeredCount = round.index + (round.answered === null ? 0 : 1)
      if (round.correct + round.mistakes !== answeredCount) return null
    }
    if (round.finished) {
      if (round.index !== CLOCK_QUESTIONS - 1 || round.answered !== null) return null
      if (round.correct + round.mistakes !== CLOCK_QUESTIONS) return null
      if ((best[value.difficulty] as number) < clockStars(round)) return null
    }
    return value
  } catch {
    return null
  }
}
