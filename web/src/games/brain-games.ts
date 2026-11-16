import { variedStroke } from './varied-puzzles'
import { completeChallenge, createChallenge, freshJourney, seededRandom, validChallenge, validJourney, type ChallengeJourney } from './challenge-journey'
import { brainIds, freshBrain, isBrainId, type BrainBase, type BrainId } from './brain-types'
import { newTangram, placeTangram, tangramLayouts, tangramSolved, type Placement, type TangramRound } from './tangram'
import { moveSokoban, newSokoban, sokoDirections, sokobanMap, sokobanSolution, sokobanSolved, sokobanLevels, sokobanCampaign, type SokobanRound } from './sokoban'
import { colorNames, newSort, pourSort, sortSolution, sortSolved, sortSettings, type SortRound } from './color-sort'
import { puzzleDifficulties, type PuzzleDifficulty } from './puzzle-games'
import { randomInt, shuffle, type Rng } from './random'
export { brainIds, isBrainId }
export type { BrainId }

export interface PatternSpec { mode: 'repeat' | 'add' | 'grow' | 'double' | 'alternate' | 'square'; start: number; step: number; repeat: string[] }
export interface PatternQuestion { spec: PatternSpec; sequence: string[]; answer: string; options: string[]; explanation: string; missing?: number }
export interface PatternRound extends BrainBase { kind: 'pattern-train'; questions: PatternQuestion[]; index: number; answers: Array<string | null> }
export interface StrokeRound extends BrainBase { kind: 'one-stroke'; size: number; edges: Array<[number,number]>; path: number[] }
export interface BalanceRound extends BrainBase { kind: 'balance-scale'; target: number; weights: number[]; supply: number[]; counts: number[]; maxPieces?: number }
export interface MirrorRound extends BrainBase { kind: 'mirror-draw'; size: number; axis: 'vertical' | 'horizontal' | 'both'; colors: number; solution: number[]; fixed: number[]; cells: number[] }
export const sceneKinds = ['tree','house','flower','butterfly','sun','ball','bird','fish'] as const
export interface SceneItem { kind: typeof sceneKinds[number]; color: number; variant: number }
export interface DifferenceRound extends BrainBase { kind: 'spot-difference'; columns: number; left: SceneItem[]; right: SceneItem[]; differences: number[]; found: number[] }
export type BrainRound = TangramRound | SokobanRound | PatternRound | StrokeRound | BalanceRound | SortRound | MirrorRound | DifferenceRound
export interface BrainSave { version: 1; difficulty: PuzzleDifficulty; round: BrainRound; best: Record<PuzzleDifficulty,number>; rounds: number; journey?: ChallengeJourney }
export interface BrainHint { text: string; index?: number; next?: number; value?: number; placement?: Placement; action?: 'add' | 'remove' }
const rank = (difficulty: PuzzleDifficulty) => puzzleDifficulties.findIndex(item=>item.id === difficulty)
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)
const int = (value: unknown, min: number, max: number): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max

export function patternValues(spec: PatternSpec): string[] {
  return Array.from({ length: 6 }, (_,index) => {
    if (spec.mode === 'repeat') return spec.repeat[index % spec.repeat.length]
    return String(spec.mode === 'add' ? spec.start + index*spec.step : spec.mode === 'grow' ? spec.start + spec.step*index*(index+1)/2 : spec.mode === 'square' ? spec.start+spec.step*index**2 : spec.mode === 'double' ? spec.start*2**index : spec.start + Math.floor(index/2)*2 + (index%2 ? spec.step : 0))
  })
}
function newPattern(difficulty: PuzzleDifficulty, rng: Rng, stage = 1): PatternRound {
  const modes: PatternSpec['mode'][] = shuffle(difficulty === 'starter' ? ['repeat','repeat','repeat','repeat','repeat','repeat'] : difficulty === 'explorer' ? ['repeat','add','repeat','add','repeat','add'] : stage < 3 ? ['grow','double','alternate','grow','double','alternate'] : ['grow','double','alternate','square','add','repeat'],rng)
  const questions = Array.from({ length: 6 }, (_,index): PatternQuestion => {
    const symbols = shuffle(['●','▲','■','◆'],rng), mode = modes[index]
    const spec: PatternSpec = { mode, start: randomInt(rng,1,6), step: randomInt(rng,2,5), repeat: index%2 ? [symbols[0],symbols[0],symbols[1]] : symbols.slice(0,stage > 2 && index%3 === 0 ? 4 : index%3 === 0 ? 3 : 2) }
    const values = patternValues(spec), missing = stage>=3 ? randomInt(rng,2,5) : 5, answer = values[missing]
    const options = mode === 'repeat' ? symbols : shuffle([...new Set([Number(answer),Number(answer)+1,Math.max(0,Number(answer)-1),Number(answer)+spec.step])].map(String),rng)
    const rule = mode === 'repeat' ? `按“${spec.repeat.join('、')}”一组重复` : mode === 'add' ? `每次增加 ${spec.step}` : mode === 'grow' ? `依次增加 ${spec.step}、${spec.step*2}、${spec.step*3}……` : mode === 'square' ? `位置编号的平方乘 ${spec.step}，再加 ${spec.start}` : mode === 'double' ? '每次变成前一个数字的两倍' : '奇数位置和偶数位置分开看，各自每次增加 2'
    return { spec, sequence: values.filter((_,index)=>index!==missing), missing, answer, options: shuffle(options,rng), explanation: `${rule}，所以缺少的是 ${answer}。` }
  })
  return { ...freshBrain(), kind: 'pattern-train', questions, index: 0, answers: Array(6).fill(null) }
}
export const edgeKey = (a: number,b: number) => [a,b].sort((x,y)=>x-y).join('-')
export function strokeStarts(round: StrokeRound): number[] {
  const degrees = new Map<number,number>()
  round.edges.flat().forEach(node=>degrees.set(node,(degrees.get(node)||0)+1))
  const odd = [...degrees].filter(([,degree])=>degree%2).map(([node])=>node)
  return odd.length ? odd : [...degrees.keys()]
}
export function strokeRemaining(round: StrokeRound): Array<[number,number]> {
  const used = new Set(round.path.slice(1).map((node,index)=>edgeKey(round.path[index],node)))
  return round.edges.filter(([a,b])=>!used.has(edgeKey(a,b)))
}
export function strokeSolution(round: StrokeRound): number[] | null {
  const edges = strokeRemaining(round), start = round.path.length ? round.path[round.path.length-1] : strokeStarts(round)[0]
  const stack = [start], route: number[] = [], remaining = [...edges]
  while (stack.length) {
    const node = stack[stack.length-1], index = remaining.findIndex(([a,b])=>a === node || b === node)
    if (index < 0) route.unshift(stack.pop()!)
    else { const [a,b] = remaining.splice(index,1)[0]; stack.push(a === node ? b : a) }
  }
  if (remaining.length || route.length !== edges.length+1 || route.slice(1).some((node,index)=>!edges.some(([a,b])=>edgeKey(a,b) === edgeKey(route[index],node)))) return null
  return route
}
function newStroke(difficulty: PuzzleDifficulty, rng: Rng, stage = 1): StrokeRound {
  const size = difficulty === 'master' ? 4 : 3
  return { ...freshBrain(), kind: 'one-stroke', size, edges: variedStroke(size,rank(difficulty),stage,rng), path: [] }
}
export function balanceWeight(round: BalanceRound) { return round.weights.reduce((sum,weight,index)=>sum+weight*round.counts[index],0) }
export function balanceCombination(round: BalanceRound): number[] | null {
  const counts = Array(round.weights.length).fill(0)
  let best: number[] | null = null
  function search(index: number, left: number): number[] | null {
    if (index === counts.length) { if (left === 0 && (!best || counts.reduce((a,b)=>a+b,0)<best.reduce((a,b)=>a+b,0))) best = [...counts]; return null }
    for (let count = 0; count <= round.supply[index] && count*round.weights[index] <= left; count++) { counts[index] = count; const found = search(index+1,left-count*round.weights[index]); if (found) return found }
    return null
  }
  search(0,round.target); return best
}
const balanceSets = {starter:[[1,2,5],[1,3,4],[1,2,4]],explorer:[[1,2,3,5],[1,3,4,6],[1,2,5,7]],master:[[2,3,5,10],[2,4,5,9],[3,4,7,9]]}
function newBalance(difficulty: PuzzleDifficulty, rng: Rng, stage = 1): BalanceRound {
  const weights = balanceSets[difficulty][randomInt(rng,0,2)]
  const supply = weights.map(()=>3), selected = weights.map((_,index)=>randomInt(rng,index === 0 ? 1 : 0,difficulty === 'starter' ? 1 : 2))
  const round: BalanceRound = { ...freshBrain(), kind: 'balance-scale', weights, supply, counts: weights.map(()=>0), target: weights.reduce((sum,weight,index)=>sum+weight*selected[index],0) }
  const minimum = balanceCombination(round)!.reduce((a,b)=>a+b,0)
  if (stage>=2 || difficulty!=='starter') round.maxPieces = minimum+(stage<4 && difficulty!=='master' ? 1 : 0)
  return round
}
export function mirrorSource(round: Pick<MirrorRound,'size'|'axis'>, index: number): number {
  const size = round.size, row = Math.floor(index/size), col = index%size
  const y = round.axis !== 'vertical' ? Math.min(row,size-1-row) : row, x = round.axis !== 'horizontal' ? Math.min(col,size-1-col) : col
  return y*size+x
}
function newMirror(difficulty: PuzzleDifficulty, rng: Rng, stage=1): MirrorRound {
  const size = difficulty === 'starter' ? 5 : 7, middle = Math.floor(size/2), axis = difficulty === 'starter' ? (stage>=3 && rng()<.5 ? 'horizontal' : 'vertical') : difficulty === 'master' ? 'both' : rng() < .5 ? 'vertical' : 'horizontal', colors = rank(difficulty)+2
  const solution = Array(size*size).fill(0), fixed: number[] = []
  for (let index = 0; index < solution.length; index++) {
    const row = Math.floor(index/size), col = index%size
    const given = axis === 'vertical' ? col <= middle : axis === 'horizontal' ? row <= middle : row <= middle && col <= middle || row === middle || col === middle
    if (given) fixed.push(index)
    if ((axis === 'vertical' ? col < middle : axis === 'horizontal' ? row < middle : row < middle && col < middle) && rng() < Math.min(.8,.4+stage*.04)) solution[index] = randomInt(rng,1,colors)
  }
  solution[0] = 1
  for (let index = 0; index < solution.length; index++) {
    const row = Math.floor(index/size), col = index%size
    if ((axis !== 'vertical' && row === middle) || (axis !== 'horizontal' && col === middle)) continue
    solution[index] = solution[mirrorSource({ size,axis },index)]
  }
  return { ...freshBrain(), kind: 'mirror-draw', size, axis, colors, fixed, solution, cells: solution.map((value,index)=>fixed.includes(index) ? value : 0) }
}
function newDifference(difficulty: PuzzleDifficulty, rng: Rng, stage=1): DifferenceRound {
  const columns = difficulty === 'starter' ? 3 : 4, count = columns*(difficulty === 'master' ? 4 : 3)
  const kinds = shuffle([...sceneKinds],rng), left = Array.from({ length: count }, (_,index): SceneItem => ({ kind: kinds[index%kinds.length],color: randomInt(rng,0,5),variant: randomInt(rng,0,1) }))
  const right = left.map(item=>({ ...item })), differences = shuffle(Array.from({ length: count },(_,index)=>index),rng).slice(0,Math.min(count-2,rank(difficulty)+3+Math.min(2,Math.floor((stage-1)/3))))
  differences.forEach((index,order)=>{ if (stage>=3 && order%3===2) right[index].kind=kinds[(kinds.indexOf(left[index].kind)+1)%kinds.length]; else if (order%2) right[index].color = (right[index].color+2)%6; else right[index].variant ^= 1 })
  return { ...freshBrain(), kind: 'spot-difference', columns, left, right, differences, found: [] }
}
export function newBrainRound(id: BrainId, difficulty: PuzzleDifficulty, rng: Rng = Math.random, stage = 1): BrainRound {
  switch (id) {
    case 'tangram': return newTangram(difficulty,rng,stage)
    case 'sokoban': return newSokoban(difficulty,rng,stage)
    case 'pattern-train': return newPattern(difficulty,rng,stage)
    case 'one-stroke': return newStroke(difficulty,rng,stage)
    case 'balance-scale': return newBalance(difficulty,rng,stage)
    case 'color-sort': return newSort(difficulty,rng,stage)
    case 'mirror-draw': return newMirror(difficulty,rng,stage)
    case 'spot-difference': return newDifference(difficulty,rng,stage)
  }
}
export function newBrain(id: BrainId, difficulty: PuzzleDifficulty = 'starter', rng: Rng = Math.random): BrainSave {
  const journey = freshJourney()
  return { version: 1, difficulty, round: createChallenge((random, stage) => newBrainRound(id, difficulty, random, stage), difficulty, journey, rng), best: { starter: 0, explorer: 0, master: 0 }, rounds: 0, journey }
}
export function nextBrain(save: BrainSave, difficulty = save.difficulty, retry = false) {
  const id = save.round.kind, previous = save.round
  save.journey ||= freshJourney()
  if (id === 'sokoban' && !retry && difficulty === save.difficulty && previous.kind === 'sokoban' && previous.level >= 9 && (previous.stage || 1) < save.journey.completed[difficulty]) { visitSokoban(save,(previous.stage || 1)+1); return }
  if (id === 'sokoban' && !retry && difficulty === save.difficulty && save.journey.completed[difficulty] >= 24 && difficulty !== 'master') difficulty = difficulty === 'starter' ? 'explorer' : 'master'
  if (id === 'sokoban' && !retry && difficulty === 'master' && save.difficulty === 'master' && save.journey.completed.master >= 24) return
  save.difficulty = difficulty
  if (id === 'sokoban' && !retry && save.journey.completed[difficulty] >= 24) { visitSokoban(save,1); return }
  if (retry && previous.seed !== undefined) { save.round = newBrainRound(id, difficulty, seededRandom(previous.seed), previous.stage); Object.assign(save.round, { seed: previous.seed, stage: previous.stage, challenge: previous.challenge }) }
  else save.round = createChallenge((rng, stage) => newBrainRound(id, difficulty, rng, stage), difficulty, save.journey)
}
export function visitSokoban(save: BrainSave, stage: number): boolean {
  if (save.round.kind !== 'sokoban' || !Number.isInteger(stage) || stage < 1 || stage > 24 || stage > (save.journey?.completed[save.difficulty] || 0) + 1) return false
  const journey = save.journey ||= freshJourney(), completed = journey.completed[save.difficulty]
  journey.completed[save.difficulty] = stage - 1
  save.round = createChallenge((rng, step) => newBrainRound('sokoban', save.difficulty, rng, step), save.difficulty, journey)
  journey.completed[save.difficulty] = completed
  return true
}
export function brainSolved(round: BrainRound): boolean {
  switch (round.kind) {
    case 'tangram': return tangramSolved(round)
    case 'sokoban': return sokobanSolved(round)
    case 'pattern-train': return round.index === round.questions.length && round.answers.every(answer=>answer !== null)
    case 'one-stroke': return round.path.length === round.edges.length+1 && strokeRemaining(round).length === 0
    case 'balance-scale': return balanceWeight(round) === round.target && (round.maxPieces===undefined || round.counts.reduce((a,b)=>a+b,0)<=round.maxPieces)
    case 'color-sort': return sortSolved(round)
    case 'mirror-draw': return same(round.cells,round.solution)
    case 'spot-difference': return round.found.length === round.differences.length
  }
}
export function brainStars(round: BrainRound) {
  const par = round.kind === 'sokoban' && round.level >= 9 ? sokobanCampaign[round.level-9].pushes : undefined
  const efficient = par === undefined || round.kind !== 'sokoban' || (round.pushes || 0) <= par+Math.max(2,Math.floor(par*.2))
  const steady = par === undefined || round.kind !== 'sokoban' || (round.pushes || 0) <= par*2
  return round.hints === 0 && round.mistakes === 0 && efficient ? 3 : round.hints <= 2 && round.mistakes <= 2 && steady ? 2 : 1
}
export function recordBrain(save: BrainSave,changed: boolean): boolean {
  if (!changed) return false
  save.round.moves++
  if (!save.round.finished && brainSolved(save.round)) { save.round.finished = true; save.rounds++; completeChallenge(save.journey, save.difficulty, save.round, brainStars(save.round)); save.best[save.difficulty] = Math.max(save.best[save.difficulty],brainStars(save.round)) }
  return true
}
export const moveBrainTangram = (save: BrainSave,index: number,value: Placement) => save.round.kind === 'tangram' && recordBrain(save,placeTangram(save.round,index,value))
export const moveBrainSokoban = (save: BrainSave,direction: number) => save.round.kind === 'sokoban' && recordBrain(save,moveSokoban(save.round,direction))
export const moveBrainSort = (save: BrainSave,from: number,to: number) => save.round.kind === 'color-sort' && recordBrain(save,pourSort(save.round,from,to))
export function drawStroke(save: BrainSave,node: number): boolean {
  const round = save.round
  if (round.kind !== 'one-stroke' || round.finished || !int(node,0,round.size**2-1)) return false
  const last = round.path[round.path.length-1]
  if (!round.path.length ? !strokeStarts(round).includes(node) : !strokeRemaining(round).some(([a,b])=>edgeKey(a,b) === edgeKey(last,node))) return false
  round.path.push(node); return recordBrain(save,true)
}
export function weighBrain(save: BrainSave,index: number,delta: number): boolean {
  const round = save.round
  if (round.kind !== 'balance-scale' || round.finished || !int(index,0,round.weights.length-1) || ![-1,1].includes(delta)) return false
  const next = round.counts[index]+delta
  if (next < 0 || next > round.supply[index]) return false
  round.counts[index] = next; return recordBrain(save,true)
}
export function paintMirror(save: BrainSave,index: number,color: number): boolean {
  const round = save.round
  if (round.kind !== 'mirror-draw' || round.finished || !int(index,0,round.cells.length-1) || !int(color,0,round.colors) || round.fixed.includes(index) || round.cells[index] === color) return false
  round.cells[index] = color; return recordBrain(save,true)
}
export function findDifference(save: BrainSave,index: number): 'found' | 'same' | null {
  const round = save.round
  if (round.kind !== 'spot-difference' || round.finished || !int(index,0,round.left.length-1) || round.found.includes(index)) return null
  if (!round.differences.includes(index)) { round.mistakes++; recordBrain(save,true); return 'same' }
  round.found.push(index); recordBrain(save,true); return 'found'
}
export function answerPattern(save: BrainSave,answer: string): boolean | null {
  const round = save.round
  if (round.kind !== 'pattern-train' || round.finished || round.answers[round.index] !== null || !round.questions[round.index].options.includes(answer)) return null
  const correct = round.questions[round.index].answer === answer
  round.answers[round.index] = answer; if (!correct) round.mistakes++
  recordBrain(save,true); return correct
}
export function advancePattern(save: BrainSave): boolean {
  const round = save.round
  if (round.kind !== 'pattern-train' || round.finished || round.answers[round.index] === null) return false
  round.index++; return recordBrain(save,true)
}
export function brainHint(save: BrainSave): BrainHint | null {
  const round = save.round
  if (round.finished) return null
  let hint: BrainHint
  switch (round.kind) {
    case 'tangram': {
      const solution = tangramLayouts[round.layout].solution, index = round.pieces.findIndex((piece,index)=>!same(piece,solution[index]))
      hint = { index,placement: solution[index],text: `将第 ${index+1} 块放在第 ${solution[index].y+1} 行、第 ${solution[index].x+1} 列，旋转 ${solution[index].rotation*90}°${solution[index].flipped ? '，并翻面' : ''}。虚线显示参考位置。` }; break
    }
    case 'sokoban': {
      const path = sokobanSolution(round)
      hint = path?.length ? { index: path[0],text: `下一步试着向${sokoDirections[path[0]].name}走。先绕到箱子的后方，再把它推向目标。` } : { text: '先检查箱子是否被推到角落。可以撤回几步，重新为箱子留出转弯的位置。' }; break
    }
    case 'pattern-train': { const question = round.questions[round.index]; hint = { text: question.explanation.split('，所以')[0]+'，按这个规律接着想一想。' }; break }
    case 'one-stroke': { const path = strokeSolution(round), node = path?.[round.path.length ? 1 : 0]; hint = node !== undefined ? { index: node,text: `试着连接高亮的第 ${node+1} 个点。留意还有哪些线没有经过。` } : { text: '剩下的线被分开了。撤回几步，先走容易被封住的那一段。' }; break }
    case 'balance-scale': {
      const solution = balanceCombination(round)!, remove = round.counts.findIndex((count,index)=>count > solution[index]), index = remove >= 0 ? remove : round.counts.findIndex((count,index)=>count < solution[index])
      hint = { index,action: remove >= 0 ? 'remove' : 'add',text: `试着${remove >= 0 ? '取下' : '放入'}一个 ${round.weights[index]} 克砝码，再看看天平是否接近平衡。` }; break
    }
    case 'color-sort': { const route = sortSolution(round), next = route?.[0]; hint = next ? { index: next[0],next: next[1],text: `试着将第 ${next[0]+1} 管顶部的${colorNames[round.tubes[next[0]].at(-1)!]}移到第 ${next[1]+1} 管。` } : { text: '优先把顶部相同的颜色放在一起，留一个空管作为中转；必要时撤回几步。' }; break }
    case 'mirror-draw': { const index = round.cells.findIndex((value,index)=>value !== round.solution[index]); hint = { index,value: round.solution[index],text: `看看第 ${Math.floor(index/round.size)+1} 行、第 ${index%round.size+1} 列在对称轴另一侧的位置，这里应${round.solution[index] ? `填${colorNames[round.solution[index]-1]}` : '留空'}。` }; break }
    case 'spot-difference': { const index = round.differences.find(index=>!round.found.includes(index))!; hint = { index,text: `看看两幅图中第 ${Math.floor(index/round.columns)+1} 行、第 ${index%round.columns+1} 个小图案，比较颜色和细节。` }; break }
  }
  round.hints++; return hint
}

export function restoreBrain(raw: string | null,id: BrainId): BrainSave | null {
  if (!raw || raw.length > 128*1024) return null
  try {
    const save = JSON.parse(raw) as BrainSave, round = save.round
    if (!save || save.version !== 1 || !puzzleDifficulties.some(item=>item.id === save.difficulty) || !int(save.rounds,0,1_000_000) || !save.best || !puzzleDifficulties.every(item=>int(save.best[item.id],0,3))) return null
    if (!validJourney(save.journey) || !round || !validChallenge(round) || round.kind !== id || typeof round.finished !== 'boolean' || ![round.moves,round.hints,round.mistakes].every(value=>int(value,0,1_000_000))) return null
    const numbers = (value: unknown,count: number,min: number,max: number): value is number[] => Array.isArray(value) && value.length === count && value.every(item=>int(item,min,max))
    switch (round.kind) {
      case 'tangram': {
        if (!int(round.layout,0,tangramLayouts.length-1) || !Array.isArray(round.pieces) || round.pieces.length !== 7) return null
        if (round.pieces.some((piece,index)=>!piece || !int(piece.x,0,8) || !int(piece.y,0,8) || !int(piece.rotation,0,3) || typeof piece.flipped !== 'boolean' || typeof piece.placed !== 'boolean' || piece.placed && !placeTangram({ ...round,finished: false,pieces: round.pieces.map((value,i)=>i === index ? { ...value,placed: false } : value) },index,piece))) return null
        break
      }
      case 'sokoban': {
        if (!int(round.level,0,sokobanLevels.length-1) || (round.level < 9 ? Math.floor(round.level/3) !== rank(save.difficulty) : Math.floor((round.level-9)/24) !== rank(save.difficulty))) return null
        const map = sokobanMap(round.level)
        if (!int(round.player,0,map.width*map.height-1) || map.walls.includes(round.player) || !numbers(round.boxes,map.targets.length,0,map.width*map.height-1) || new Set(round.boxes).size !== round.boxes.length || round.boxes.some(box=>box === round.player || map.walls.includes(box))) return null
        break
      }
      case 'pattern-train': {
        if (!Array.isArray(round.questions) || round.questions.length !== 6 || !int(round.index,0,6) || !Array.isArray(round.answers) || round.answers.length !== 6) return null
        for (const [index,question] of round.questions.entries()) {
          const spec = question?.spec
          if (!spec || !['repeat','add','grow','double','alternate','square'].includes(spec.mode) || !int(spec.start,1,6) || !int(spec.step,2,5) || !Array.isArray(spec.repeat) || ![2,3,4].includes(spec.repeat.length) || !spec.repeat.every(token=>['●','▲','■','◆'].includes(token))) return null
          const values = patternValues(spec)
          if (!int(question.missing ?? 5,2,5) || !same(question.sequence,values.filter((_,index)=>index!==(question.missing ?? 5))) || question.answer !== values[question.missing ?? 5] || !Array.isArray(question.options) || question.options.length !== 4 || new Set(question.options).size !== 4 || !question.options.includes(question.answer) || !question.options.every(option=>typeof option === 'string' && option.length < 8) || typeof question.explanation !== 'string' || question.explanation.length > 200) return null
          const answer = round.answers[index]
          if (answer !== null && !question.options.includes(answer) || index < round.index && answer === null || index > round.index && answer !== null) return null
        }
        if (round.mistakes !== round.answers.filter((answer,index)=>answer !== null && answer !== round.questions[index].answer).length) return null
        break
      }
      case 'one-stroke': {
        const size = save.difficulty === 'master' ? 4 : 3
        if (round.size !== size || !Array.isArray(round.edges) || round.edges.length < 4 || round.edges.length > 24 || !round.edges.every(edge=>numbers(edge,2,0,size**2-1) && Math.abs(Math.floor(edge[0]/size)-Math.floor(edge[1]/size))+Math.abs(edge[0]%size-edge[1]%size) === 1) || new Set(round.edges.map(([a,b])=>edgeKey(a,b))).size !== round.edges.length) return null
        if (!Array.isArray(round.path) || round.path.length > round.edges.length+1 || !round.path.every(node=>int(node,0,size**2-1)) || round.path.length && !strokeStarts(round).includes(round.path[0])) return null
        const used = round.path.slice(1).map((node,index)=>edgeKey(round.path[index],node))
        if (new Set(used).size !== used.length || used.some(key=>!round.edges.some(([a,b])=>edgeKey(a,b) === key)) || !strokeSolution({ ...round,path: [] })) return null
        break
      }
      case 'balance-scale': {
        const weights = round.weights
        if (!balanceSets[save.difficulty].some(set=>same(set,weights)) || !numbers(round.supply,weights.length,3,3) || !numbers(round.counts,weights.length,0,3) || !int(round.target,1,80) || !balanceCombination(round) || round.maxPieces!==undefined && (!int(round.maxPieces,1,12) || balanceCombination(round)!.reduce((a,b)=>a+b,0)>round.maxPieces)) return null
        break
      }
      case 'color-sort': {
        const {colors,capacity}=sortSettings(save.difficulty,round.stage)
        if (round.colors !== colors || round.capacity !== capacity || !Array.isArray(round.tubes) || round.tubes.length !== colors+2 || round.tubes.some(tube=>!Array.isArray(tube) || tube.length > capacity || !tube.every(color=>int(color,0,colors-1)))) return null
        if (Array.from({ length: colors },(_,color)=>round.tubes.flat().filter(value=>value === color).length).some(count=>count !== capacity) || !Array.isArray(round.route) || round.route.length > 1000 || !round.route.every(move=>numbers(move,2,0,colors+1))) return null
        if (round.route.length) {
          const target = { ...round,finished: false,tubes: round.tubes.map(tube=>[...tube]),route: round.route.map(move=>[...move] as [number,number]) }
          for (const [from,to] of round.route) if (!pourSort(target,from,to)) return null
          if (!sortSolved(target)) return null
        }
        break
      }
      case 'mirror-draw': {
        const size = save.difficulty === 'starter' ? 5 : 7, middle = Math.floor(size/2)
        if (round.size !== size || round.colors !== rank(save.difficulty)+2 || !['vertical','horizontal','both'].includes(round.axis) || !numbers(round.solution,size**2,0,round.colors) || !numbers(round.cells,size**2,0,round.colors) || !Array.isArray(round.fixed)) return null
        const fixed = Array.from({ length: size**2 },(_,index)=>index).filter(index=>round.axis === 'vertical' ? index%size <= middle : round.axis === 'horizontal' ? Math.floor(index/size) <= middle : Math.floor(index/size) <= middle && index%size <= middle || Math.floor(index/size) === middle || index%size === middle)
        if (!same(round.fixed,fixed) || fixed.some(index=>round.cells[index] !== round.solution[index]) || round.solution.some((value,index)=>value !== round.solution[mirrorSource(round,index)]) || !round.solution.some(Boolean)) return null
        break
      }
      case 'spot-difference': {
        const columns = save.difficulty === 'starter' ? 3 : 4, count = columns*(save.difficulty === 'master' ? 4 : 3)
        const valid = (items: SceneItem[]) => Array.isArray(items) && items.length === count && items.every(item=>item && sceneKinds.includes(item.kind) && int(item.color,0,5) && int(item.variant,0,1))
        if (round.columns !== columns || !valid(round.left) || !valid(round.right) || !Array.isArray(round.differences) || ![rank(save.difficulty)+3, Math.min(count-2,rank(save.difficulty)+3+Math.min(2,Math.floor(((round.stage || 1)-1)/3)))].includes(round.differences.length) || !round.differences.every(index=>int(index,0,count-1)) || new Set(round.differences).size !== round.differences.length) return null
        const differences = round.left.flatMap((item,index)=>same(item,round.right[index]) ? [] : [index])
        if (!same([...round.differences].sort((a,b)=>a-b),differences) || !Array.isArray(round.found) || new Set(round.found).size !== round.found.length || round.found.some(index=>!round.differences.includes(index))) return null
        break
      }
    }
    if (round.finished !== brainSolved(round) || round.finished && (save.rounds < 1 || save.best[save.difficulty] < brainStars(round))) return null
    return save
  } catch { return null }
}
