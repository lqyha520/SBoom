import { freshBrain, type BrainBase } from './brain-types'
import type { PuzzleDifficulty } from './puzzle-games'
import { randomInt, type Rng } from './random'

export interface SortRound extends BrainBase { kind: 'color-sort'; capacity: number; colors: number; tubes: number[][]; route: Array<[number,number]> }
export const colorNames = ['珊瑚红','湖水蓝','青草绿','暖黄色','葡萄紫','杏橙色']
export const colorValues = ['#da9078','#78a7bd','#8fae7d','#d8b56a','#ad95c3','#d1a176']
export const sortSolved = (round: SortRound) => round.tubes.every(tube => tube.length === 0 || tube.length === round.capacity && tube.every(color => color === tube[0]))
export function pourSort(round: SortRound, from: number, to: number): boolean {
  if (round.finished || !Number.isInteger(from) || !Number.isInteger(to) || from < 0 || to < 0 || from >= round.tubes.length || to >= round.tubes.length || from === to) return false
  const source = round.tubes[from], target = round.tubes[to], color = source[source.length-1]
  if (!source.length || target.length >= round.capacity || target.length > 0 && target[target.length-1] !== color) return false
  target.push(source.pop()!)
  if (round.route[0]?.[0] === from && round.route[0]?.[1] === to) round.route.shift(); else round.route = []
  return true
}
export const sortSettings=(difficulty:PuzzleDifficulty,stage=1)=>({colors:Math.min(difficulty==='starter'?3:difficulty==='explorer'?4:6,['starter','explorer','master'].indexOf(difficulty)+2+Math.floor((stage-1)/4)),capacity:difficulty==='starter' && stage<5?3:4})
export function newSort(difficulty: PuzzleDifficulty, rng: Rng, stage = 1): SortRound {
  const {colors,capacity}=sortSettings(difficulty,stage)
  const round: SortRound = { ...freshBrain(), kind: 'color-sort', capacity, colors, tubes: Array.from({ length: colors+2 }, (_,index) => index < colors ? Array(capacity).fill(index) : []), route: [] }
  let previous = [-1,-1]
  for (let step = 0; step < colors*14+Math.min(stage,16)*2; step++) {
    const choices: Array<[number,number]> = []
    for (let from = 0; from < round.tubes.length; from++) {
      const source = round.tubes[from], color = source[source.length-1]
      if (!source.length || source.length > 1 && source[source.length-2] !== color) continue
      for (let to = 0; to < round.tubes.length; to++) if (from !== to && round.tubes[to].length < capacity && !(from === previous[1] && to === previous[0])) choices.push([from,to])
    }
    if (!choices.length) break
    const [from,to] = choices[randomInt(rng,0,choices.length-1)]
    round.tubes[to].push(round.tubes[from].pop()!); round.route.unshift([to,from]); previous = [from,to]
  }
  if (sortSolved(round)) {
    const from = round.tubes.findIndex(tube=>tube.length === capacity), to = round.tubes.findIndex(tube=>!tube.length)
    round.tubes[to].push(round.tubes[from].pop()!); round.route.unshift([to,from])
  }
  return round
}
export function sortSolution(round: SortRound, limit = 25_000): Array<[number,number]> | null {
  if (round.route.length) return round.route
  const encode = (tubes: number[][]) => tubes.map(tube => tube.join('')).sort().join('|')
  const queue = [{ tubes: round.tubes.map(tube=>[...tube]), parent: -1, move: [-1,-1] as [number,number] }], seen = new Set([encode(round.tubes)])
  for (let cursor = 0; cursor < queue.length && cursor < limit; cursor++) {
    const node = queue[cursor], state = { ...round, tubes: node.tubes }
    if (sortSolved(state)) {
      const result: Array<[number,number]> = []
      for (let index = cursor; queue[index].parent >= 0; index = queue[index].parent) result.unshift(queue[index].move)
      return result
    }
    for (let from = 0; from < node.tubes.length; from++) for (let to = 0; to < node.tubes.length; to++) {
      const source = node.tubes[from], target = node.tubes[to]
      if (!target.length && source.every(color=>color === source[0])) continue
      const next = { ...round, finished: false, route: [], tubes: node.tubes.map(tube=>[...tube]) }
      if (!pourSort(next,from,to)) continue
      const key = encode(next.tubes)
      if (seen.has(key)) continue
      seen.add(key); queue.push({ tubes: next.tubes, parent: cursor, move: [from,to] })
    }
  }
  return null
}
