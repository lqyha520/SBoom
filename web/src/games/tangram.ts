import { freshBrain, type BrainBase } from './brain-types'
import type { PuzzleDifficulty } from './puzzle-games'
import type { Rng } from './random'
import { extraTangramLayouts } from './tangram-layouts'

export interface Placement { x: number; y: number; rotation: number; flipped: boolean; placed: boolean }
export interface TangramRound extends BrainBase { kind: 'tangram'; layout: number; pieces: Placement[] }
export const pieceNames = ['大三角 1', '大三角 2', '中三角', '小三角 1', '小三角 2', '正方形', '平行四边形']
const pieces = [ [[0,0],[4,0],[2,2]], [[0,0],[4,0],[2,2]], [[0,0],[2,0],[0,2]], [[0,0],[2,0],[1,1]], [[0,0],[2,0],[1,1]], [[0,1],[1,0],[2,1],[1,2]], [[0,0],[2,0],[3,1],[1,1]] ]
const placement = (x: number, y: number, rotation: number, flipped = false): Placement => ({ x, y, rotation, flipped, placed: true })
export const tangramLayouts = [
  { name: '正方形', outline: [[2,2],[6,2],[6,6],[2,6]], solution: [placement(2,4,2),placement(2,2,3),placement(4,2,1),placement(5,4,1),placement(3,3,0),placement(4,3,0),placement(2,2,0)] },
  { name: '大三角', outline: [[0,6],[8,6],[4,2]], solution: [placement(0,4,2),placement(4,4,2),placement(2,4,1),placement(4,4,3),placement(3,2,2),placement(4,3,0),placement(2,3,0,true)] },
  { name: '斜方块', outline: [[0,2],[4,2],[8,6],[4,6]], solution: [placement(4,4,2),placement(0,2,0),placement(2,4,1),placement(4,4,3),placement(3,2,2),placement(4,3,0),placement(2,3,0,true)] },
  ...extraTangramLayouts.sort((a,b)=>a.outline.length-b.outline.length),
]
export function tangramPolygon(index: number, value: Placement): number[][] {
  let points = pieces[index].map(([x, y]) => [value.flipped ? -x : x, y])
  for (let rotation = 0; rotation < value.rotation; rotation++) points = points.map(([x,y]) => [-y,x])
  const minX = Math.min(...points.map(([x]) => x)), minY = Math.min(...points.map(([,y]) => y))
  return points.map(([x,y]) => [x - minX + value.x, y - minY + value.y])
}
function inside(x: number, y: number, points: number[][]) {
  let inside = false
  for (let index = 0, previous = points.length-1; index < points.length; previous = index++) {
    const [ax,ay]=points[index], [bx,by]=points[previous]
    if ((ay>y)!==(by>y) && x<(bx-ax)*(y-ay)/(by-ay)+ax) inside=!inside
  }
  return inside
}
// 将每个格子分成四个小三角，精确判断覆盖和重叠；不依赖拖动误差。
export function tangramAtoms(points: number[][]): number[] {
  const result: number[] = []
  for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) for (const [atom,[dx,dy]] of [[.5,1/6],[5/6,.5],[.5,5/6],[1/6,.5]].entries()) if (inside(x+dx,y+dy,points)) result.push((y*8+x)*4+atom)
  return result
}
export function tangramConflicts(round: TangramRound): number[] {
  const target = new Set(tangramAtoms(tangramLayouts[round.layout].outline))
  const areas = round.pieces.map((piece, index) => piece.placed ? tangramAtoms(tangramPolygon(index,piece)) : [])
  return areas.flatMap((area,index) => area.some(atom => !target.has(atom) || areas.some((other,j) => j !== index && other.includes(atom))) ? [index] : [])
}
export function tangramSolved(round: TangramRound): boolean {
  if (!round.pieces.every(piece => piece.placed) || tangramConflicts(round).length) return false
  const covered = new Set(round.pieces.flatMap((piece,index) => tangramAtoms(tangramPolygon(index,piece))))
  return tangramAtoms(tangramLayouts[round.layout].outline).every(atom => covered.has(atom))
}
export function placeTangram(round: TangramRound, index: number, value: Placement): boolean {
  if (round.finished || !Number.isInteger(index) || index < 0 || index > 6 || !Number.isInteger(value.x) || !Number.isInteger(value.y) || !Number.isInteger(value.rotation) || value.rotation < 0 || value.rotation > 3) return false
  const points = tangramPolygon(index,value)
  if (value.placed && points.some(([x,y]) => x < 0 || x > 8 || y < 0 || y > 8)) return false
  if (JSON.stringify(round.pieces[index]) === JSON.stringify(value)) return false
  round.pieces[index] = { ...value }; return true
}
export function newTangram(difficulty: PuzzleDifficulty, _rng: Rng, stage = 1): TangramRound {
  return { ...freshBrain(), kind: 'tangram', layout: (stage-1+['starter','explorer','master'].indexOf(difficulty)*9)%tangramLayouts.length, pieces: Array.from({ length: 7 }, () => ({ x: 0, y: 0, rotation: 0, flipped: false, placed: false })) }
}
