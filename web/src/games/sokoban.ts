import { freshBrain, type BrainBase } from './brain-types'
import type { Rng } from './random'
import type { PuzzleDifficulty } from './puzzle-games'
import { sokobanCampaign } from './sokoban-levels'
export { sokobanCampaign }

export interface SokobanRound extends BrainBase { kind: 'sokoban'; level: number; player: number; boxes: number[]; pushes?: number }
export const sokobanLevels = [
  ['######','#    #','# @$ #','#  . #','#    #','######'],
  ['######','# .  #','# $  #','# @  #','#    #','######'],
  ['######','#    #','# .$ #','#    #','# @  #','######'],
  ['#######','#     #','# . . #','# $ $ #','#  @  #','#     #','#######'],
  ['#######','#     #','# .#. #','# $ $ #','#  @  #','#     #','#######'],
  ['#######','#     #','#  .. #','# $$  #','# @   #','#     #','#######'],
  ['#######','#     #','# ... #','# $$$ #','#  @  #','#     #','#######'],
  ['#######','# . . #','#     #','# $$$ #','#  @  #','#  .  #','#######'],
  ['#######','#     #','#. . .#','# $$$ #','#     #','#  @  #','#######'],
  ...sokobanCampaign.map(level => [...level.rows]),
]
export const sokoDirections = [{ dx: 0, dy: -1, name: '上' }, { dx: 1, dy: 0, name: '右' }, { dx: 0, dy: 1, name: '下' }, { dx: -1, dy: 0, name: '左' }]
export function sokobanMap(level: number) {
  const rows = sokobanLevels[level], width = rows[0].length, cells = rows.join('').split('')
  return { width, height: rows.length, walls: cells.flatMap((cell,index) => cell === '#' ? [index] : []), targets: cells.flatMap((cell,index) => cell === '.' || cell === '+' ? [index] : []), boxes: cells.flatMap((cell,index) => cell === '$' ? [index] : []), player: cells.findIndex(cell=>cell === '@' || cell === '+') }
}
export function newSokoban(difficulty: PuzzleDifficulty, _rng: Rng, stage = 1): SokobanRound {
  const level = 9 + ['starter','explorer','master'].indexOf(difficulty)*24 + (stage-1)%24, map = sokobanMap(level)
  return { ...freshBrain(), kind: 'sokoban', level, player: map.player, boxes: map.boxes, pushes: 0 }
}
function nextCell(index: number, direction: number, width: number) { const step = sokoDirections[direction]; return index + step.dx + step.dy*width }
export function moveSokoban(round: SokobanRound, direction: number): boolean {
  if (round.finished || !Number.isInteger(direction) || direction < 0 || direction > 3) return false
  const map = sokobanMap(round.level), next = nextCell(round.player,direction,map.width)
  if (map.walls.includes(next)) return false
  const box = round.boxes.indexOf(next)
  if (box >= 0) {
    const beyond = nextCell(next,direction,map.width)
    if (map.walls.includes(beyond) || round.boxes.includes(beyond)) return false
    round.boxes[box] = beyond
    round.pushes = (round.pushes || 0) + 1
  }
  round.player = next; return true
}
export const sokobanSolved = (round: SokobanRound) => round.boxes.every(box => sokobanMap(round.level).targets.includes(box))
function safeBoxCells(level: number): Set<number> {
  const map = sokobanMap(level), walls = new Set(map.walls), safe = new Set(map.targets), queue = [...map.targets]
  const floor = (cell: number) => cell >= 0 && cell < map.width*map.height && !walls.has(cell)
  for (const cell of queue) for (let direction = 0; direction < 4; direction++) {
    const previous = nextCell(cell,(direction+2)%4,map.width), behind = nextCell(previous,(direction+2)%4,map.width)
    if (floor(previous) && floor(behind) && !safe.has(previous)) { safe.add(previous); queue.push(previous) }
  }
  return safe
}
export function sokobanDeadlocks(round: SokobanRound): number[] {
  const map = sokobanMap(round.level), safe = safeBoxCells(round.level), occupied = new Set([...map.walls,...round.boxes])
  return round.boxes.filter(box => !map.targets.includes(box) && (!safe.has(box) || [-1,1].some(dx=>[-1,1].some(dy=>[box,box+dx,box+dy*map.width,box+dx+dy*map.width].every(cell=>occupied.has(cell))))))
}
export function sokobanSolution(round: SokobanRound, limit = 60_000): number[] | null {
  const map = sokobanMap(round.level), walls = new Set(map.walls), targets = new Set(map.targets), total = map.width*map.height
  const floor = (cell: number) => cell >= 0 && cell < total && !walls.has(cell)
  function walking(player: number, boxes: number[]) {
    const paths = new Map<number, number[]>([[player, []]]), queue = [player], occupied = new Set(boxes)
    for (const cell of queue) for (let direction = 0; direction < 4; direction++) {
      const next = nextCell(cell, direction, map.width)
      if (floor(next) && !occupied.has(next) && !paths.has(next)) { paths.set(next, [...paths.get(cell)!, direction]); queue.push(next) }
    }
    return paths
  }
  // 从目标逆推可到达位置，排除贴墙死格；搜索按推动次数，而不是重复遍历走路状态。
  const safe = new Set(map.targets), cells = [...map.targets]
  for (const cell of cells) for (let direction = 0; direction < 4; direction++) {
    const previous = nextCell(cell, (direction+2)%4, map.width), behind = nextCell(previous, (direction+2)%4, map.width)
    if (floor(previous) && floor(behind) && !safe.has(previous)) { safe.add(previous); cells.push(previous) }
  }
  const queue = [{ player: round.player, boxes: [...round.boxes], parent: -1, actions: [] as number[] }], seen = new Set<string>()
  for (let cursor = 0; cursor < queue.length && cursor < limit; cursor++) {
    const node = queue[cursor]
    if (node.boxes.every(box => targets.has(box))) {
      const path: number[] = []
      for (let index = cursor; queue[index].parent >= 0; index = queue[index].parent) path.unshift(...queue[index].actions)
      return path
    }
    const paths = walking(node.player, node.boxes)
    for (const box of node.boxes) for (let direction = 0; direction < 4; direction++) {
      const behind = nextCell(box, (direction+2)%4, map.width), destination = nextCell(box, direction, map.width)
      if (!paths.has(behind) || !safe.has(destination) || node.boxes.includes(destination)) continue
      const boxes = node.boxes.map(cell => cell === box ? destination : cell), component = walking(box, boxes)
      const key = [...boxes].sort((a,b)=>a-b).join(',') + ':' + Math.min(...component.keys())
      if (seen.has(key)) continue
      seen.add(key); queue.push({ player: box, boxes, parent: cursor, actions: [...paths.get(behind)!, direction] })
    }
  }
  return null
}
