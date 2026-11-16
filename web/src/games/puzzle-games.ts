import { reasoningHint } from './puzzle-reasoning'
import { completeChallenge, createChallenge, freshJourney, seededRandom, validChallenge, validJourney, type ChallengeJourney, type ChallengeRound } from './challenge-journey'
import { hanoiDistance,variedPicture,variedPipeRoute } from './varied-puzzles'
import { randomInt, shuffle, type Rng } from './random'

export const puzzleIds = ['shape-sudoku', 'sliding-puzzle', 'lights-out', 'tower-hanoi', 'picture-logic', 'pipe-connect'] as const
export type PuzzleId = typeof puzzleIds[number]
export type PuzzleDifficulty = 'starter' | 'explorer' | 'master'
export const puzzleDifficulties = [
  { id: 'starter' as const, name: '入门' },
  { id: 'explorer' as const, name: '进阶' },
  { id: 'master' as const, name: '挑战' },
]
export interface PuzzleRound extends ChallengeRound {
  kind: PuzzleId
  size: number
  initial: number[]
  cells: number[]
  solution: number[]
  fixed: number[]
  route: number[]
  plan: number[]
  moves: number
  hints: number
  baseline: number
  finished: boolean
}
export interface PuzzleSave {
  version: 1
  difficulty: PuzzleDifficulty
  round: PuzzleRound
  best: Record<PuzzleDifficulty, number>
  rounds: number
  journey?: ChallengeJourney
}
export const shapes = ['', '●', '▲', '■', '◆']
export const shapeNames = ['空白', '圆形', '三角形', '正方形', '菱形']
const rank = (difficulty: PuzzleDifficulty) => puzzleDifficulties.findIndex(item => item.id === difficulty)
export const isPuzzleId = (value: unknown): value is PuzzleId => puzzleIds.some(id => id === value)
const integer = (value: unknown, min: number, max: number): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max
const adjacent = (a: number, b: number, size: number) => Math.abs(Math.floor(a / size) - Math.floor(b / size)) + Math.abs(a % size - b % size) === 1
export const puzzleSize = (id: PuzzleId, difficulty: PuzzleDifficulty, stage = 1) => id === 'tower-hanoi' ? Math.min([4,5,6][rank(difficulty)],3+rank(difficulty)+Math.floor((stage-1)/4)) : id === 'shape-sudoku' ? 4 : id === 'sliding-puzzle' ? (difficulty === 'master' ? 4 : 3) : id === 'picture-logic' ? 5 + rank(difficulty) : 3 + rank(difficulty)

function sudokuAllowed(cells: number[], index: number, value: number): boolean {
  const row = Math.floor(index / 4), col = index % 4
  return cells.every((cell, other) => other === index || cell !== value || (Math.floor(other / 4) !== row && other % 4 !== col && (Math.floor(other / 8) !== Math.floor(row / 2) || Math.floor(other % 4 / 2) !== Math.floor(col / 2))))
}
export function sudokuSolutions(input: number[], limit = 2): number {
  const cells = [...input]
  if (cells.some((value, index) => value !== 0 && !sudokuAllowed(cells, index, value))) return 0
  let count = 0
  function search() {
    const index = cells.indexOf(0)
    if (index < 0) { count++; return }
    for (let value = 1; value <= 4 && count < limit; value++) {
      if (!sudokuAllowed(cells, index, value)) continue
      cells[index] = value; search(); cells[index] = 0
    }
  }
  search()
  return count
}
export function sudokuConflicts(cells: number[]): number[] {
  return cells.flatMap((value, index) => value && !sudokuAllowed(cells, index, value) ? [index] : [])
}
export function slidingSolvable(cells: number[], size: number): boolean {
  const tiles = cells.filter(Boolean)
  let inversions = 0
  for (let a = 0; a < tiles.length; a++) for (let b = a + 1; b < tiles.length; b++) if (tiles[a] > tiles[b]) inversions++
  return size % 2 ? inversions % 2 === 0 : (inversions + size - Math.floor(cells.indexOf(0) / size)) % 2 === 1
}
export function lightNeighbors(index: number, size: number): number[] {
  return [index, ...Array.from({ length: size * size }, (_, other) => other).filter(other => adjacent(index, other, size))]
}
function toggleLight(cells: number[], index: number, size: number) { for (const cell of lightNeighbors(index, size)) cells[cell] = 1 - cells[cell] }
export function lineClues(values: number[]): number[] {
  const result: number[] = []
  let run = 0
  for (const value of [...values, 0]) { if (value === 1) run++; else if (run) { result.push(run); run = 0 } }
  return result.length ? result : [0]
}
export function pictureClues(cells: number[], size: number) {
  return {
    rows: Array.from({ length: size }, (_, row) => lineClues(cells.slice(row * size, (row + 1) * size))),
    columns: Array.from({ length: size }, (_, col) => lineClues(Array.from({ length: size }, (_, row) => cells[row * size + col]))),
  }
}
// 管口用上、右、下、左四个二进制位表示；所有弯管和直管都能通过旋转还原。
export const pipeBits = [1, 2, 4, 8]
export function rotatePipe(mask: number): number { return (mask << 1 & 15) | (mask >> 3) }
export function pipeTurns(from: number, to: number): number {
  for (let turn = 0; turn < 4; turn++, from = rotatePipe(from)) if (from === to) return turn
  return -1
}
function direction(from: number, to: number, size: number): number { return to === from - size ? 1 : to === from + 1 ? 2 : to === from + size ? 4 : 8 }
function neighbor(index: number, bit: number, size: number): number {
  const row = Math.floor(index / size), col = index % size
  return bit === 1 ? (row ? index - size : -1) : bit === 2 ? (col < size - 1 ? index + 1 : -1) : bit === 4 ? (row < size - 1 ? index + size : -1) : (col ? index - 1 : -1)
}
export function pipePort(round: PuzzleRound, outlet = false) {
  const index = outlet ? round.route[round.route.length - 1] : round.route[0]
  const bit = pipeBits.find(bit => (round.solution[index] & bit) !== 0 && neighbor(index, bit, round.size) < 0)!
  return { index, bit }
}
export function pipeWater(round: PuzzleRound): number[] {
  const source = pipePort(round), sink = pipePort(round, true)
  if (!(round.cells[source.index] & source.bit)) return []
  const wet: number[] = []
  let index = source.index, incoming = source.bit
  while (!wet.includes(index)) {
    const mask = round.cells[index]
    if (!(mask & incoming)) break
    wet.push(index)
    const outgoing = pipeBits.find(bit => bit !== incoming && (mask & bit))!
    if (index === sink.index && outgoing === sink.bit) break
    const next = neighbor(index, outgoing, round.size)
    if (next < 0) break
    incoming = outgoing === 1 ? 4 : outgoing === 2 ? 8 : outgoing === 4 ? 1 : 2
    index = next
  }
  return wet
}
export function puzzleSolved(round: PuzzleRound): boolean {
  if (round.kind === 'picture-logic') return round.cells.every(Boolean) && JSON.stringify(pictureClues(round.cells, round.size)) === JSON.stringify(pictureClues(round.solution, round.size))
  if (round.kind === 'pipe-connect') {
    const wet = pipeWater(round), sink = pipePort(round, true)
    return wet.length === round.cells.length && wet[wet.length - 1] === sink.index && !!(round.cells[sink.index] & sink.bit)
  }
  return round.cells.every((value, index) => value === round.solution[index])
}

export function newPuzzleRound(kind: PuzzleId, difficulty: PuzzleDifficulty, rng: Rng = Math.random, stage = 1): PuzzleRound {
  const size = puzzleSize(kind, difficulty, stage), count = kind === 'tower-hanoi' ? size : size * size
  const round: PuzzleRound = { kind, size, initial: [], cells: [], solution: [], fixed: [], route: [], plan: [], moves: 0, hints: 0, baseline: count, finished: false }
  if (kind === 'shape-sudoku') {
    const symbols = shuffle([1, 2, 3, 4], rng)
    const order = () => shuffle([0, 1], rng).flatMap(band => shuffle([band * 2, band * 2 + 1], rng))
    const rows = order(), cols = order()
    round.solution = rows.flatMap(row => cols.map(col => symbols[(row * 2 + Math.floor(row / 2) + col) % 4]))
    round.cells = [...round.solution]
    const given = Math.max([7,5,4][rank(difficulty)],[10,7,5][rank(difficulty)]-Math.floor((stage-1)/3))
    for (const index of shuffle(Array.from({ length: 16 }, (_, index) => index), rng)) {
      if (round.cells.filter(Boolean).length <= given) break
      const value = round.cells[index]; round.cells[index] = 0
      if (sudokuSolutions(round.cells) !== 1) round.cells[index] = value
    }
    round.fixed = round.cells.flatMap((value, index) => value ? [index] : [])
    round.baseline = 16 - round.fixed.length
  } else if (kind === 'sliding-puzzle') {
    round.solution = Array.from({ length: count }, (_, index) => (index + 1) % count)
    round.cells = [...round.solution]
    let previous = -1
    for (let step = 0; step < [16, 40, 80][rank(difficulty)] + Math.min(stage-1,12)*[2,4,5][rank(difficulty)]; step++) {
      const blank = round.cells.indexOf(0)
      const choices = round.cells.flatMap((_, index) => adjacent(index, blank, size) && index !== previous ? [index] : [])
      const index = choices[randomInt(rng, 0, choices.length - 1)]
      ;[round.cells[blank], round.cells[index]] = [round.cells[index], round.cells[blank]]
      round.route.unshift(blank); previous = blank
    }
    if (round.cells.every((value, index) => value === round.solution[index])) {
      const blank = round.cells.indexOf(0), index = blank - 1
      ;[round.cells[blank], round.cells[index]] = [round.cells[index], round.cells[blank]]
      round.route.unshift(blank)
    }
    round.baseline = round.route.length
  } else if (kind === 'lights-out') {
    round.solution = Array(count).fill(1); round.cells = [...round.solution]
    round.plan = Array(count).fill(0)
    for (const index of shuffle(Array.from({ length: count }, (_, index) => index), rng).slice(0, Math.min(count-1,[3, 7, 12][rank(difficulty)]+Math.floor(Math.min(stage-1,12)/3)))) {
      toggleLight(round.cells, index, size); round.plan[index] = 1
    }
    if (round.cells.every(Boolean)) { toggleLight(round.cells, 0, size); round.plan[0] ^= 1 }
    round.baseline = round.plan.filter(Boolean).length
  } else if (kind === 'tower-hanoi') {
    round.cells = stage === 1 ? Array(size).fill(0) : Array.from({length:size},()=>randomInt(rng,0,2)); round.cells[size-1]=stage%2?0:1; round.solution = Array(size).fill(2); round.baseline = hanoiDistance(round.cells)
  } else if (kind === 'picture-logic') {
    round.solution = variedPicture(size,stage,rng); round.cells = Array(count).fill(0)
  } else {
    round.route = variedPipeRoute(size,rng)
    const port = (cell:number) => pipeBits.find(bit=>neighbor(cell,bit,size)<0)!
    round.solution = Array(count).fill(0)
    for (let step = 0; step < count; step++) {
      const index = round.route[step]
      round.solution[index] = (step ? direction(index, round.route[step - 1], size) : port(index)) | (step < count - 1 ? direction(index, round.route[step + 1], size) : port(index))
    }
    round.cells = round.solution.map(mask => { for (let turns = randomInt(rng, 0, 3); turns > 0; turns--) mask = rotatePipe(mask); return mask })
    if (puzzleSolved(round)) round.cells[round.route[0]] = rotatePipe(round.cells[round.route[0]])
    round.baseline = round.cells.reduce((sum, mask, index) => sum + pipeTurns(mask, round.solution[index]), 0)
  }
  round.initial = [...round.cells]
  return round
}
export function newPuzzle(id: PuzzleId, difficulty: PuzzleDifficulty = 'starter', rng: Rng = Math.random): PuzzleSave {
  const journey = freshJourney()
  return { version: 1, difficulty, round: createChallenge((random, stage) => newPuzzleRound(id, difficulty, random, stage), difficulty, journey, rng), best: { starter: 0, explorer: 0, master: 0 }, rounds: 0, journey }
}
export function nextPuzzle(save: PuzzleSave, difficulty = save.difficulty, retry = false) {
  const previous = save.round, id = previous.kind
  save.journey ||= freshJourney(); save.difficulty = difficulty
  if (retry && previous.seed !== undefined) { save.round = newPuzzleRound(id, difficulty, seededRandom(previous.seed), previous.stage); Object.assign(save.round, { seed: previous.seed, stage: previous.stage, challenge: previous.challenge }) }
  else save.round = createChallenge((rng, stage) => newPuzzleRound(id, difficulty, rng, stage), difficulty, save.journey)
}
export function puzzleStars(round: PuzzleRound): number {
  return round.hints === 0 && round.moves <= round.baseline * 1.5 ? 3 : round.hints <= 2 && round.moves <= round.baseline * 3 ? 2 : 1
}
function complete(save: PuzzleSave) {
  if (!save.round.finished && puzzleSolved(save.round)) {
    save.round.finished = true; save.rounds++; completeChallenge(save.journey, save.difficulty, save.round, puzzleStars(save.round))
    save.best[save.difficulty] = Math.max(save.best[save.difficulty], puzzleStars(save.round))
  }
}
export function playPuzzle(save: PuzzleSave, index: number, value = 1): boolean {
  const round = save.round
  if (round.finished || !integer(index, 0, round.cells.length - 1) || round.kind === 'tower-hanoi') return false
  if (round.kind === 'shape-sudoku') {
    if (round.fixed.includes(index) || !integer(value, 0, 4) || round.cells[index] === value) return false
    round.cells[index] = value
  } else if (round.kind === 'sliding-puzzle') {
    const blank = round.cells.indexOf(0)
    if (!adjacent(index, blank, round.size)) return false
    ;[round.cells[index], round.cells[blank]] = [round.cells[blank], round.cells[index]]
    if (round.route[0] === index) round.route.shift(); else round.route.unshift(blank)
  } else if (round.kind === 'lights-out') {
    toggleLight(round.cells, index, round.size); round.plan[index] ^= 1
  } else if (round.kind === 'picture-logic') {
    if (value !== 1 && value !== 2) return false
    round.cells[index] = round.cells[index] === value ? 0 : value
  } else round.cells[index] = rotatePipe(round.cells[index])
  round.moves++; complete(save); return true
}
export function hanoiTop(round: PuzzleRound, peg: number): number { return round.cells.indexOf(peg) }
export function moveHanoi(save: PuzzleSave, from: number, to: number): boolean {
  const round = save.round
  if (round.kind !== 'tower-hanoi' || round.finished || !integer(from, 0, 2) || !integer(to, 0, 2) || from === to) return false
  const disk = hanoiTop(round, from), target = hanoiTop(round, to)
  if (disk < 0 || target >= 0 && disk > target) return false
  round.cells[disk] = to; round.moves++; complete(save); return true
}
export function hanoiHint(round: PuzzleRound): { from: number; to: number } | null {
  function next(disk: number, destination: number): { from: number; to: number } | null {
    if (disk < 0) return null
    const from = round.cells[disk]
    if (from === destination) return next(disk - 1, destination)
    const spare = 3 - from - destination
    return next(disk - 1, spare) || { from, to: destination }
  }
  return next(round.size - 1, 2)
}
export function puzzleHint(save: PuzzleSave): { index: number; text: string } | null {
  const round = save.round
  if (round.finished) return null
  const reasoned = reasoningHint(round)
  if (reasoned) { round.hints++; return reasoned }
  let index = -1, text = ''
  if (round.kind === 'shape-sudoku') {
    index = round.cells.findIndex((value, index) => value !== round.solution[index])
    text = `第 ${Math.floor(index / 4) + 1} 行、第 ${index % 4 + 1} 列可以填${shapeNames[round.solution[index]]}。看看同一行、列和小方框里缺了哪种图形。`
  } else if (round.kind === 'sliding-puzzle') {
    index = round.route[0]; text = `试着把高亮的 ${round.cells[index]} 移进空格，沿着这条路线可以逐步还原。`
  } else if (round.kind === 'lights-out') {
    index = round.plan.indexOf(1); text = '试着点击这颗星星。它和上下左右的星星会一起改变，再看看哪些还没有亮。'
  } else if (round.kind === 'tower-hanoi') {
    const move = hanoiHint(round)!
    index = move.from; text = `将 ${'ABC'[move.from]} 柱最上面的圆盘移到 ${'ABC'[move.to]} 柱，先为大圆盘腾出路线。`
  } else if (round.kind === 'picture-logic') {
    index = round.cells.findIndex((value, index) => value !== (round.solution[index] ? 1 : 2))
    text = `第 ${Math.floor(index / round.size) + 1} 行、第 ${index % round.size + 1} 列可以${round.solution[index] ? '填色' : '标空'}。对照这一行和这一列的数字推一推。`
  } else {
    index = round.cells.findIndex((mask, index) => mask !== round.solution[index])
    text = `高亮的水管再转 ${pipeTurns(round.cells[index], round.solution[index])} 次，就能接上这条参考路线。`
  }
  if (index < 0) return null
  round.hints++
  return { index, text }
}

export function restorePuzzle(raw: string | null, id: PuzzleId): PuzzleSave | null {
  if (!raw || raw.length > 128 * 1024) return null
  try {
    const value = JSON.parse(raw) as PuzzleSave
    if (!value || value.version !== 1 || !puzzleDifficulties.some(item => item.id === value.difficulty) || !integer(value.rounds, 0, 1_000_000)) return null
    if (!value.best || !puzzleDifficulties.every(item => integer(value.best[item.id], 0, 3))) return null
    const round = value.round, size = puzzleSize(id, value.difficulty, round?.stage), count = id === 'tower-hanoi' ? size : size * size
    if (!validJourney(value.journey) || !round || !validChallenge(round) || round.kind !== id || round.size !== size || typeof round.finished !== 'boolean' || !integer(round.moves, 0, 1_000_000) || !integer(round.hints, 0, 1_000_000) || !integer(round.baseline, 1, 10_000)) return null
    const max = id === 'shape-sudoku' ? 4 : id === 'sliding-puzzle' ? count - 1 : id === 'pipe-connect' ? 15 : id === 'lights-out' ? 1 : 2
    if (![round.cells, round.initial, round.solution].every(cells => Array.isArray(cells) && cells.length === count && cells.every(cell => integer(cell, 0, max)))) return null
    if (![round.fixed, round.route, round.plan].every(cells => Array.isArray(cells) && cells.length <= 20_000 && cells.every(cell => integer(cell, 0, count - 1)))) return null
    if (id !== 'shape-sudoku' && round.fixed.length || id !== 'lights-out' && round.plan.length || id !== 'pipe-connect' && id !== 'sliding-puzzle' && round.route.length) return null
    if (id === 'shape-sudoku') {
      if (round.solution.includes(0) || sudokuSolutions(round.solution) !== 1 || sudokuSolutions(round.initial) !== 1) return null
      const fixed = round.initial.flatMap((cell, index) => cell ? [index] : [])
      if (JSON.stringify(fixed) !== JSON.stringify(round.fixed) || fixed.length < 4 || fixed.length > 10 || fixed.some(index => round.cells[index] !== round.initial[index] || round.initial[index] !== round.solution[index])) return null
    } else if (id === 'sliding-puzzle') {
      if (new Set(round.initial).size !== count || new Set(round.cells).size !== count || !slidingSolvable(round.cells, size) || !slidingSolvable(round.initial, size) || !round.solution.every((cell, index) => cell === (index + 1) % count)) return null
      const route = [...round.cells]
      for (const index of round.route) {
        const blank = route.indexOf(0)
        if (!adjacent(blank, index, size)) return null
        ;[route[blank], route[index]] = [route[index], route[blank]]
      }
      if (!route.every((cell, index) => cell === round.solution[index])) return null
    } else if (id === 'lights-out') {
      if (round.plan.length !== count || !round.plan.every(cell => cell === 0 || cell === 1) || !round.solution.every(cell => cell === 1)) return null
      const target = [...round.cells]
      round.plan.forEach((cell, index) => { if (cell) toggleLight(target, index, size) })
      if (!target.every(Boolean)) return null
    } else if (id === 'tower-hanoi') {
      if (!round.initial.every(cell => integer(cell,0,2)) || !round.solution.every(cell => cell === 2)) return null
    } else if (id === 'picture-logic') {
      if (!round.initial.every(cell => cell === 0) || !round.solution.every(cell => cell === 0 || cell === 1) || !round.solution.includes(1)) return null
    } else {
      if (round.route.length !== count || new Set(round.route).size !== count || round.route.some((cell, step) => step > 0 && !adjacent(cell, round.route[step - 1], size))) return null
      const masks = [3, 5, 6, 9, 10, 12]
      if (!round.solution.every(mask => masks.includes(mask)) || !round.cells.every((mask, index) => pipeTurns(mask, round.solution[index]) >= 0) || !round.initial.every((mask, index) => pipeTurns(mask, round.solution[index]) >= 0)) return null
      // 校验参考路线确实连通，避免损坏的端口让恢复后的棋盘无解。
      if (!puzzleSolved({ ...round, cells: round.solution })) return null
    }
    if (round.finished !== puzzleSolved(round) || round.finished && (value.rounds < 1 || value.best[value.difficulty] < puzzleStars(round))) return null
    return value
  } catch { return null }
}
