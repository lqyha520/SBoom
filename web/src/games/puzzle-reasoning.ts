import { hanoiDistance } from './varied-puzzles'
import { lightNeighbors, lineClues, pipePort, pipeTurns, pipeWater, shapeNames, sudokuConflicts, type PuzzleRound } from './puzzle-games'

export function sudokuCandidates(cells: number[], index: number): number[] {
  return [1, 2, 3, 4].filter(value => {
    const attempt = [...cells]; attempt[index] = value
    return !sudokuConflicts(attempt).includes(index)
  })
}

// 枚举一行满足数字的所有排列，再取交集；提示只使用玩家看得到的条件。
export function linePossibilities(clues: number[], cells: number[]): number[][] {
  const possibilities: number[][] = []
  for (let mask = 0; mask < 2 ** cells.length; mask++) {
    const values = cells.map((_, index) => mask >> index & 1)
    if (values.some((value, index) => cells[index] && value !== (cells[index] === 1 ? 1 : 0))) continue
    if (JSON.stringify(lineClues(values)) === JSON.stringify(clues)) possibilities.push(values)
  }
  return possibilities
}

export function pictureLines(round: PuzzleRound) {
  const size = round.size
  return Array.from({ length: size * 2 }, (_, line) => {
    const column = line >= size, number = line % size
    const indices = Array.from({ length: size }, (_, offset) => column ? offset * size + number : number * size + offset)
    const cells = indices.map(index => round.cells[index]), clues = lineClues(indices.map(index => round.solution[index]))
    const possibilities = linePossibilities(clues, cells)
    return { indices, possibilities, name: `第 ${number + 1} ${column ? '列' : '行'}`, clues,
      state: !possibilities.length ? 'conflict' : cells.every(Boolean) ? 'done' : 'open' }
  })
}

export function reasoningHint(round: PuzzleRound): { index: number; text: string } | null {
  if (round.kind === 'shape-sudoku') {
    const conflicts = sudokuConflicts(round.cells)
    if (conflicts.length) return { index: conflicts[0], text: '这里的图形和同一行、列或小方框重复。先取下重复的图形，再看看可以填哪些候选。' }
    const blanks = round.cells.flatMap((cell, index) => cell ? [] : [index])
    for (const index of blanks) {
      const candidates = sudokuCandidates(round.cells, index)
      if (candidates.length === 1) return { index, text: `同一行、列和小方框已经排除了其他三种图形，这一格只剩${shapeNames[candidates[0]]}可以填。` }
    }
    const groups = [
      ...Array.from({ length: 4 }, (_, r) => [0, 1, 2, 3].map(c => r * 4 + c)),
      ...Array.from({ length: 4 }, (_, c) => [0, 1, 2, 3].map(r => r * 4 + c)),
      ...[0, 2, 8, 10].map(start => [start, start + 1, start + 4, start + 5]),
    ]
    for (const group of groups) for (const value of [1, 2, 3, 4]) {
      if (group.some(index => round.cells[index] === value)) continue
      const available = group.filter(index => !round.cells[index] && sudokuCandidates(round.cells, index).includes(value))
      if (available.length === 1) return { index: available[0], text: `这个行、列或小方框里，只有高亮位置还能放${shapeNames[value]}。比较其他空格被哪些已知图形排除。` }
    }
    const index = blanks.sort((a, b) => sudokuCandidates(round.cells, a).length - sudokuCandidates(round.cells, b).length)[0]
    return index === undefined ? null : { index, text: '先观察这格的候选，比较相同行、列和小方框。暂时没有只剩一个候选的格子，可以先检查前面填写的条件。' }
  }
  if (round.kind === 'picture-logic') {
    const lines = pictureLines(round), conflict = lines.find(line => line.state === 'conflict')
    if (conflict) return { index: conflict.indices.find(index => round.cells[index])!, text: `${conflict.name}的标记无法满足数字 ${conflict.clues.join('、')}。先取消这一行或列中不确定的标记，重新比较连续格数。` }
    for (const line of lines) for (const [offset, index] of line.indices.entries()) {
      if (round.cells[index]) continue
      const values = new Set(line.possibilities.map(values => values[offset]))
      if (values.size === 1) return { index, text: `${line.name}数字为 ${line.clues.join('、')}。所有符合条件的排法中，高亮格都必须${values.has(1) ? '填色' : '留空'}；可以${values.has(1) ? '填色' : '标空'}后再看交叉方向。` }
    }
    const open = lines.filter(line => line.state === 'open').sort((a, b) => a.possibilities.length - b.possibilities.length)[0]
    return open ? { index: open.indices.find(index => !round.cells[index])!, text: `${open.name}还可能有 ${open.possibilities.length} 种排法。先和交叉的列、行比较；没有确定的格子时，不必猜涂色答案。` } : null
  }
  if (round.kind === 'pipe-connect') {
    const source = pipePort(round), wet = pipeWater(round)
    const index = wet.length < round.route.length ? (wet.length ? round.route[Math.min(wet.length, round.route.length - 1)] : source.index) : round.route.at(-1)!
    return { index, text: `${wet.length ? '水流到这里还不能继续。' : '进水口还没有接通。'}检查相邻两根管子的开口是否相对；高亮管在参考路线中需顺时针转 ${pipeTurns(round.cells[index], round.solution[index])} 次。` }
  }
  return null
}

export const slidingDistance = (round: PuzzleRound) => round.cells.reduce((sum, value, index) => value ? sum + Math.abs(Math.floor(index / round.size) - Math.floor((value - 1) / round.size)) + Math.abs(index % round.size - (value - 1) % round.size) : sum, 0)
export const hanoiRemaining = (round: PuzzleRound) => hanoiDistance(round.cells)
export const lightPreview = (round: PuzzleRound, index: number) => lightNeighbors(index, round.size)
