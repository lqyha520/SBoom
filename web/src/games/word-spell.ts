import { englishDifficulties, englishWord, englishWords, isEnglishTier, type EnglishTier } from './english-words'
import { randomInt, shuffle, type Rng } from './random'

export type SpellDifficulty = EnglishTier

export interface SpellTile {
  id: string
  letter: string
}

export interface SpellQuestion {
  wordId: string
  word: string
  meaning: string
  emoji: string
  answer: string[]
  tiles: SpellTile[]
}

export interface SpellRound {
  version: 1
  difficulty: SpellDifficulty
  questions: SpellQuestion[]
  index: number
  correct: number
  mistakes: number
  hints: number
  selected: string[]
  solved: boolean
  finished: boolean
}

export interface SpellSave {
  version: 1
  difficulty: SpellDifficulty
  round: SpellRound
  best: Record<SpellDifficulty, number>
  totalWords: number
  rounds: number
}

export const SPELL_QUESTIONS = 8
export { englishDifficulties as spellDifficulties }

export function isSpellDifficulty(value: unknown): value is SpellDifficulty {
  return isEnglishTier(value)
}

function makeQuestion(difficulty: SpellDifficulty, rng: Rng, used: Set<string>): SpellQuestion {
  const available = englishWords[difficulty].filter(item => !used.has(item.word))
  const item = available[randomInt(rng, 0, available.length - 1)]
  used.add(item.word)
  const tiles = item.word.split('').map((letter, index) => ({ id: `${item.word}-${index}`, letter }))
  const answer = tiles.map(tile => tile.id)
  return { wordId: item.word, word: item.word, meaning: item.meaning, emoji: item.emoji, answer, tiles: shuffle(tiles, rng) }
}

export function newSpellRound(difficulty: SpellDifficulty, rng: Rng = Math.random): SpellRound {
  const used = new Set<string>()
  return {
    version: 1,
    difficulty,
    questions: Array.from({ length: SPELL_QUESTIONS }, () => makeQuestion(difficulty, rng, used)),
    index: 0,
    correct: 0,
    mistakes: 0,
    hints: 0,
    selected: [],
    solved: false,
    finished: false,
  }
}

export function newSpell(difficulty: SpellDifficulty = 'starter', rng: Rng = Math.random): SpellSave {
  return {
    version: 1,
    difficulty,
    round: newSpellRound(difficulty, rng),
    best: { starter: 0, explorer: 0, master: 0 },
    totalWords: 0,
    rounds: 0,
  }
}

export function spellStars(round: Pick<SpellRound, 'mistakes'>): number {
  return round.mistakes === 0 ? 3 : round.mistakes <= 2 ? 2 : 1
}

export function selectSpellTile(save: SpellSave, tileId: string): boolean {
  const round = save.round
  if (round.finished || round.solved) return false
  const question = round.questions[round.index]
  if (!question.tiles.some(tile => tile.id === tileId)) return false
  const existing = round.selected.indexOf(tileId)
  if (existing >= 0) {
    round.selected.splice(existing, 1)
    return true
  }
  if (round.selected.length >= question.word.length) return false
  round.selected.push(tileId)
  return true
}

export function clearSpellSelection(save: SpellSave): void {
  if (save.round.finished || save.round.solved) return
  save.round.selected = []
}

export function spellHint(save: SpellSave): string | null {
  const round = save.round
  if (round.finished || round.solved) return null
  const question = round.questions[round.index]
  round.hints++
  return question.word[0]
}

export function checkSpell(save: SpellSave): boolean | null {
  const round = save.round
  if (round.finished || round.solved) return null
  const question = round.questions[round.index]
  if (round.selected.length !== question.word.length) return null
  const attempt = round.selected.map(id => question.tiles.find(tile => tile.id === id)?.letter ?? '').join('')
  if (attempt === question.word) {
    round.solved = true
    round.correct++
    return true
  }
  round.mistakes++
  return false
}

export function advanceSpell(save: SpellSave): 'next' | 'finished' | null {
  const round = save.round
  if (round.finished || !round.solved) return null
  if (round.index < SPELL_QUESTIONS - 1) {
    round.index++
    round.selected = []
    round.solved = false
    return 'next'
  }
  round.finished = true
  round.solved = false
  round.selected = []
  save.best[round.difficulty] = Math.max(save.best[round.difficulty], spellStars(round))
  save.totalWords += SPELL_QUESTIONS
  save.rounds++
  return 'finished'
}

export function restartSpell(save: SpellSave, rng: Rng = Math.random): void {
  save.round = newSpellRound(save.difficulty, rng)
}

export function switchSpellDifficulty(save: SpellSave, difficulty: SpellDifficulty, rng: Rng = Math.random): void {
  save.difficulty = difficulty
  save.round = newSpellRound(difficulty, rng)
}

function isInt(value: unknown, min: number, max: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max
}

function validQuestion(question: SpellQuestion, difficulty: SpellDifficulty): boolean {
  const source = englishWord(difficulty, question?.wordId)
  if (!source || question.word !== source.word || question.meaning !== source.meaning || question.emoji !== source.emoji) return false
  if (!Array.isArray(question.tiles) || question.tiles.length !== source.word.length) return false
  if (!Array.isArray(question.answer) || question.answer.length !== source.word.length) return false
  const ids = question.tiles.map(tile => tile?.id)
  if (!ids.every(id => typeof id === 'string') || new Set(ids).size !== ids.length) return false
  const letters = question.tiles.map(tile => tile?.letter)
  if (!letters.every(letter => typeof letter === 'string')) return false
  if (question.tiles.map(tile => tile.letter).sort().join('') !== source.word.split('').sort().join('')) return false
  if (question.answer.some(id => !question.tiles.some(tile => tile.id === id))) return false
  const attempt = question.answer.map(id => question.tiles.find(tile => tile.id === id)!.letter).join('')
  return attempt === source.word
}

export function restoreSpell(raw: string | null): SpellSave | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as SpellSave
    if (!value || value.version !== 1 || !isSpellDifficulty(value.difficulty)) return null
    const best = value.best as unknown as Record<string, unknown>
    if (!best || !englishDifficulties.every(item => isInt(best[item.id], 0, 3))) return null
    if (!isInt(value.totalWords, 0, 1_000_000) || !isInt(value.rounds, 0, 1_000_000)) return null
    const round = value.round
    if (!round || round.version !== 1 || round.difficulty !== value.difficulty) return null
    if (!Array.isArray(round.questions) || round.questions.length !== SPELL_QUESTIONS) return null
    if (!round.questions.every(question => validQuestion(question, value.difficulty))) return null
    if (new Set(round.questions.map(question => question.wordId)).size !== SPELL_QUESTIONS) return null
    if (!isInt(round.index, 0, SPELL_QUESTIONS - 1) || typeof round.solved !== 'boolean' || typeof round.finished !== 'boolean') return null
    if (!isInt(round.correct, 0, SPELL_QUESTIONS) || !isInt(round.mistakes, 0, 9999) || !isInt(round.hints, 0, 9999)) return null
    if (!Array.isArray(round.selected) || !round.selected.every(id => typeof id === 'string')) return null
    const question = round.questions[round.index]
    if (new Set(round.selected).size !== round.selected.length) return null
    if (!round.selected.every(id => question.tiles.some(tile => tile.id === id))) return null
    if (round.selected.length > question.word.length) return null
    if (!round.finished) {
      if (round.correct !== round.index + (round.solved ? 1 : 0)) return null
      if (round.solved && (round.selected.length !== question.word.length || !round.selected.every((id, index) => id === question.answer[index]))) return null
    }
    if (round.finished) {
      if (round.index !== SPELL_QUESTIONS - 1 || round.solved || round.correct !== SPELL_QUESTIONS || round.selected.length !== 0) return null
      if ((best[value.difficulty] as number) < spellStars(round)) return null
    }
    return value
  } catch {
    return null
  }
}
