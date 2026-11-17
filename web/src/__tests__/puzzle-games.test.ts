import { describe, expect, it, vi } from 'vitest'
import { cloudGames, gameKey, games, validSave } from '../games/catalog'
import { GameCloud } from '../games/cloud-saves'
import {
  hanoiHint, lineClues, moveHanoi, newPuzzle, pipeTurns, playPuzzle, puzzleDifficulties,
  puzzleHint, puzzleIds, puzzleSolved, restorePuzzle, slidingSolvable, sudokuConflicts,
  sudokuSolutions, type PuzzleSave,
} from '../games/puzzle-games'

function seeded(seed: number) {
  return () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296 }
}
function solve(save: PuzzleSave) {
  const round = save.round
  if (round.kind === 'sliding-puzzle') {
    for (let step = 0; !round.finished && step < 200; step++) expect(playPuzzle(save, round.route[0])).toBe(true)
  } else if (round.kind === 'tower-hanoi') {
    for (let step = 0; !round.finished && step < 100; step++) { const move = hanoiHint(round)!; expect(moveHanoi(save, move.from, move.to)).toBe(true) }
  } else if (round.kind === 'lights-out') {
    for (const index of round.plan.flatMap((value, index) => value ? [index] : [])) { if (!round.finished) expect(playPuzzle(save, index)).toBe(true) }
  } else {
    for (let index = 0; index < round.cells.length && !round.finished; index++) {
      if (round.kind === 'shape-sudoku') { if (!round.fixed.includes(index)) expect(playPuzzle(save, index, round.solution[index])).toBe(true) }
      else if (round.kind === 'picture-logic') expect(playPuzzle(save, index, round.solution[index] ? 1 : 2)).toBe(true)
      else while (round.cells[index] !== round.solution[index] && !round.finished) expect(playPuzzle(save, index)).toBe(true)
    }
  }
}

describe('益智游戏的棋盘与规则', () => {
  for (const id of puzzleIds) for (const { id: difficulty } of puzzleDifficulties) {
    it(`${id} / ${difficulty}：随机棋盘有解，完整通关只计一次，刷新可恢复`, () => {
      for (let seed = 1; seed <= 20; seed++) {
        const save = newPuzzle(id, difficulty, seeded(seed))
        expect(puzzleSolved(save.round)).toBe(false)
        expect(restorePuzzle(JSON.stringify(save), id)).toEqual(save)
        if (id === 'shape-sudoku') expect(sudokuSolutions(save.round.initial)).toBe(1)
        solve(save)
        expect(save.round.finished).toBe(true)
        expect(puzzleSolved(save.round)).toBe(true)
        expect(save.rounds).toBe(1)
        expect(save.best[difficulty]).toBeGreaterThanOrEqual(1)
        expect(restorePuzzle(JSON.stringify(save), id)).toEqual(save)
        expect(playPuzzle(save, 0)).toBe(false)
        expect(moveHanoi(save, 2, 0)).toBe(false)
        expect(puzzleHint(save)).toBeNull()
        expect(save.rounds).toBe(1)
      }
    })
  }
  it('数独的重复图形提示冲突，已知图形不能改', () => {
    const save = newPuzzle('shape-sudoku', 'master', seeded(5)), round = save.round
    expect(playPuzzle(save, round.fixed[0], 0)).toBe(false)
    const index = round.cells.indexOf(0), sameRow = round.fixed.find(other => Math.floor(other / 4) === Math.floor(index / 4))
    if (sameRow !== undefined) {
      expect(playPuzzle(save, index, round.cells[sameRow])).toBe(true)
      expect(sudokuConflicts(round.cells)).toContain(index)
      expect(restorePuzzle(JSON.stringify(save), 'shape-sudoku')).toEqual(save)
      expect(playPuzzle(save, index, 0)).toBe(true)
    }
  })
  it('华容道只允许邻接空格的数字移动；来回移动后提示路线仍能通关', () => {
    const save = newPuzzle('sliding-puzzle', 'master', seeded(4)), round = save.round
    expect(playPuzzle(save, round.cells.indexOf(0))).toBe(false)
    expect(playPuzzle(save, -1)).toBe(false)
    const blank = round.cells.indexOf(0), index = round.route[0]
    expect(playPuzzle(save, index)).toBe(true)
    expect(playPuzzle(save, blank)).toBe(true)
    expect(restorePuzzle(JSON.stringify(save), 'sliding-puzzle')).toEqual(save)
    solve(save); expect(round.finished).toBe(true)
    expect(slidingSolvable([2, 1, 3, 4, 5, 6, 7, 8, 0], 3)).toBe(false)
  })
  it('星星点击两次回到原样；提示没有偷偷改动棋盘', () => {
    const save = newPuzzle('lights-out'), initial = [...save.round.cells]
    playPuzzle(save, 0); playPuzzle(save, 0)
    expect(save.round.cells).toEqual(initial)
    const hint = puzzleHint(save)
    expect(hint?.index).toBeGreaterThanOrEqual(0)
    expect(save.round.hints).toBe(1)
    expect(save.round.cells).toEqual(initial)
    expect(restorePuzzle(JSON.stringify(save), 'lights-out')).toEqual(save)
  })
  it('汉诺塔只搬最上面一盘，并阻止大盘放到小盘上', () => {
    const save = newPuzzle('tower-hanoi')
    expect(moveHanoi(save, 1, 2)).toBe(false)
    expect(moveHanoi(save, 0, 2)).toBe(true)
    expect(moveHanoi(save, 0, 2)).toBe(false)
    expect(moveHanoi(save, 0, 1)).toBe(true)
    expect(moveHanoi(save, 2, 1)).toBe(true)
    for (let step = 0; step < 30 && !save.round.finished; step++) { const move = hanoiHint(save.round)!; expect(moveHanoi(save, move.from, move.to)).toBe(true) }
    expect(save.round.finished).toBe(true)
  })
  it('像素线索区分多组连续格，标空不计入填色', () => {
    expect(lineClues([1, 1, 2, 1, 0])).toEqual([2, 1])
    expect(lineClues([0, 2, 0])).toEqual([0])
    const save = newPuzzle('picture-logic')
    expect(playPuzzle(save, 0, 2)).toBe(true)
    expect(save.round.cells[0]).toBe(2)
    expect(playPuzzle(save, 0, 2)).toBe(true)
    expect(save.round.cells[0]).toBe(0)
  })
  it('损坏的棋盘、错误的游戏类型、无解路线及伪造完成标记不恢复', () => {
    for (const id of puzzleIds) {
      const save = newPuzzle(id), copy = () => JSON.parse(JSON.stringify(save)) as PuzzleSave
      const broken = copy(); broken.round.cells[0] = 99
      expect(restorePuzzle(JSON.stringify(broken), id)).toBeNull()
      const finished = copy(); finished.round.finished = true
      expect(restorePuzzle(JSON.stringify(finished), id)).toBeNull()
      const version = copy(); version.version = 2 as 1
      expect(restorePuzzle(JSON.stringify(version), id)).toBeNull()
      expect(restorePuzzle(JSON.stringify(save), puzzleIds.find(other => other !== id)!)).toBeNull()
    }
    const sliding = newPuzzle('sliding-puzzle'); sliding.round.route = []
    expect(restorePuzzle(JSON.stringify(sliding), 'sliding-puzzle')).toBeNull()
    const pipe = newPuzzle('pipe-connect'); pipe.round.cells[0] = pipeTurns(3, 5) === -1 ? 5 : 3
    if (pipeTurns(pipe.round.cells[0], pipe.round.solution[0]) < 0) expect(restorePuzzle(JSON.stringify(pipe), 'pipe-connect')).toBeNull()
    expect(restorePuzzle('{', 'shape-sudoku')).toBeNull()
  })
  it('六款益智游戏可从目录打开和校验，并只使用本机存档', async () => {
    localStorage.clear(); vi.useFakeTimers()
    const put = vi.fn(), cloud = new GameCloud('7', () => {}, { list: async () => [], put })
    try {
      expect(games).toHaveLength(32)
      for (const id of puzzleIds) {
        const raw = JSON.stringify(newPuzzle(id))
        expect(await validSave(id, raw)).toBe(true)
        expect(cloudGames.some(game => String(game.id) === id)).toBe(false)
        localStorage.setItem(gameKey(id, '7'), raw)
      }
      await cloud.refresh(); await vi.advanceTimersByTimeAsync(2000)
      expect(put).not.toHaveBeenCalled()
    } finally { cloud.dispose(); vi.useRealTimers(); localStorage.clear() }
  })
})
