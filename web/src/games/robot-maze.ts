export type Command = 'forward' | 'left' | 'right'
export type Instruction = { type: Command } | { type: 'repeat'; count: number; body: Command[] }
export type Direction = 0 | 1 | 2 | 3
export interface Point { x: number; y: number }
export interface Level {
  name: string
  chapter: number
  concept: string
  description: string
  rows: string[]
  start: Point & { direction: Direction }
  goal: Point
  gears: Point[]
  commands: Command[]
  repeat: boolean
  budget: number
  hint: string
}

// 地图中的 . 是可行走地面，# 是石块，~ 是水面；坐标从左上角开始。
export const levels: Level[] = [
  { name: '第一次出发', chapter: 0, concept: '顺序', description: '沿着小路走，带回第一枚零件。', rows: ['~~~~~', '.....', '#####', '~~~~~', '~~~~~'], start: { x: 0, y: 1, direction: 1 }, goal: { x: 4, y: 1 }, gears: [{ x: 2, y: 1 }], commands: ['forward'], repeat: false, budget: 4, hint: '机器人朝右。每个「前进」走一格，从起点到终点一共走 4 格。' },
  { name: '沿途的礼物', chapter: 0, concept: '顺序', description: '经过两枚零件，再停在充电站。', rows: ['~~.~~', '~~.~~', '~~.~~', '~~.~~', '~~.~~'], start: { x: 2, y: 4, direction: 0 }, goal: { x: 2, y: 0 }, gears: [{ x: 2, y: 3 }, { x: 2, y: 1 }], commands: ['forward'], repeat: false, budget: 4, hint: '箭头朝上，前进就是往上走。零件会在经过时自动收集。' },
  { name: '转角遇见你', chapter: 0, concept: '转向', description: '到了路口，向机器人的左边转。', rows: ['~~~.~', '~~~.~', '~~~.~', '....~', '#####'], start: { x: 0, y: 3, direction: 1 }, goal: { x: 3, y: 0 }, gears: [{ x: 3, y: 2 }], commands: ['forward', 'left'], repeat: false, budget: 7, hint: '先向右走 3 格，左转一次，再向上走 3 格。转弯只改变朝向，不会移动。' },
  { name: '绕过小石丘', chapter: 1, concept: '转向', description: '绕开石块，从小路的另一头出发。', rows: ['~~~~~', '.....', '.###.', '.###.', '~~~~~'], start: { x: 0, y: 3, direction: 0 }, goal: { x: 4, y: 3 }, gears: [{ x: 2, y: 1 }], commands: ['forward', 'left', 'right'], repeat: false, budget: 10, hint: '先向上走 2 格，右转走过上方的小路，再右转走到充电站。' },
  { name: '弯弯小河', chapter: 1, concept: '方向', description: '两次转弯，让每一步都落在小路上。', rows: ['~~~~~', '~~~~~', '....~', '~~~.~', '~~~..'], start: { x: 0, y: 2, direction: 1 }, goal: { x: 4, y: 4 }, gears: [{ x: 3, y: 3 }, { x: 4, y: 4 }], commands: ['forward', 'left', 'right'], repeat: false, budget: 8, hint: '向右走 3 格，右转向下走 2 格，再左转向右走 1 格。左右要看机器人的朝向。' },
  { name: '零件兜兜圈', chapter: 1, concept: '规划', description: '先绕到上方拿零件，再回到右侧。', rows: ['~~~~~', '.....', '.###.', '.....', '~~~~~'], start: { x: 0, y: 3, direction: 1 }, goal: { x: 4, y: 3 }, gears: [{ x: 2, y: 1 }], commands: ['forward', 'left', 'right'], repeat: false, budget: 11, hint: '直接向右走会漏掉零件。先左转，绕上面的小路收集零件，再走到右下角。' },
  { name: '重复的魔法', chapter: 2, concept: '循环', description: '把一样的动作放进重复积木。', rows: ['~~~~~~', '......', '######', '~~~~~~', '~~~~~~'], start: { x: 0, y: 1, direction: 1 }, goal: { x: 4, y: 1 }, gears: [{ x: 1, y: 1 }, { x: 3, y: 1 }], commands: ['forward', 'left', 'right'], repeat: true, budget: 1, hint: '加入一块「重复 4 次」，在里面放一个「前进」。这 1 块积木会执行 4 步。' },
  { name: '阶梯小径', chapter: 2, concept: '循环', description: '找到小路里重复出现的走法。', rows: ['~~..~', '~..~~', '..~~~', '~~~~~', '~~~~~'], start: { x: 0, y: 2, direction: 1 }, goal: { x: 3, y: 0 }, gears: [{ x: 1, y: 1 }, { x: 2, y: 0 }], commands: ['forward', 'left', 'right'], repeat: true, budget: 2, hint: '重复 2 次「前进、左转、前进、右转」，就能走过两级台阶。最后再前进一格。' },
  { name: '环岛收集站', chapter: 2, concept: '循环与规划', description: '绕小岛一圈，把零件都带回起点。', rows: ['~~~~~', '....~', '.##.~', '.##.~', '....~'], start: { x: 0, y: 4, direction: 0 }, goal: { x: 0, y: 4 }, gears: [{ x: 0, y: 1 }, { x: 3, y: 1 }, { x: 3, y: 4 }], commands: ['forward', 'left', 'right'], repeat: true, budget: 1, hint: '小岛四条边一样长。重复 4 次「前进、前进、前进、右转」，就能绕岛一圈。' },
]
export const chapters = [
  { name: '初次启航', subtitle: '按顺序安排动作', icon: 'i-lucide-footprints' },
  { name: '转弯的学问', subtitle: '观察方向，规划路线', icon: 'i-lucide-route' },
  { name: '循环实验室', subtitle: '用重复积木简化程序', icon: 'i-lucide-repeat-2' },
]
export const commandInfo: Record<Command, { name: string; icon: string; description: string }> = {
  forward: { name: '前进', icon: 'i-lucide-arrow-up', description: '沿朝向走一格' },
  left: { name: '左转', icon: 'i-lucide-corner-up-left', description: '原地向左转' },
  right: { name: '右转', icon: 'i-lucide-corner-up-right', description: '原地向右转' },
}
export const MAX_CARDS = 12
export const MAX_BODY = 6
export interface CompiledStep { command: Command; card: number; inner: number | null; iteration: number }
export function compileProgram(program: Instruction[]): CompiledStep[] {
  return program.flatMap<CompiledStep>((instruction, card) => instruction.type === 'repeat'
    ? Array.from({ length: instruction.count }, (_, iteration) => instruction.body.map((command, inner) => ({ command, card, inner, iteration: iteration + 1 }))).flat()
    : [{ command: instruction.type, card, inner: null, iteration: 1 }])
}
export interface RobotState extends Point { direction: Direction; collected: string[] }
export const pointKey = (p: Point): string => `${p.x},${p.y}`
export function startRobot(level: Level): RobotState {
  return { ...level.start, collected: level.gears.some(p => pointKey(p) === pointKey(level.start)) ? [pointKey(level.start)] : [] }
}
export function moveRobot(level: Level, robot: RobotState, command: Command): { robot: RobotState; blocked: boolean } {
  const next = { ...robot, collected: [...robot.collected] }
  if (command === 'left') next.direction = ((next.direction + 3) % 4) as Direction
  else if (command === 'right') next.direction = ((next.direction + 1) % 4) as Direction
  else {
    const delta = [[0, -1], [1, 0], [0, 1], [-1, 0]][next.direction]
    next.x += delta[0]; next.y += delta[1]
    if (level.rows[next.y]?.[next.x] !== '.') return { robot, blocked: true }
    const key = pointKey(next)
    if (level.gears.some(p => pointKey(p) === key) && !next.collected.includes(key)) next.collected.push(key)
  }
  return { robot: next, blocked: false }
}
export function resultOf(level: Level, robot: RobotState): 'success' | 'missing' | 'unfinished' {
  if (pointKey(robot) !== pointKey(level.goal)) return 'unfinished'
  return robot.collected.length === level.gears.length ? 'success' : 'missing'
}
export function starsFor(level: Level, program: Instruction[], hints: number): number {
  return hints > 0 ? 1 : program.length <= level.budget ? 3 : 2
}
export interface MazeSave {
  version: 1
  level: number
  program: Instruction[]
  stars: number[]
  hints: number[]
}
export function newMaze(): MazeSave {
  return { version: 1, level: 0, program: [], stars: levels.map(() => 0), hints: levels.map(() => 0) }
}
export function isProgram(value: unknown, level: Level): value is Instruction[] {
  if (!Array.isArray(value) || value.length > MAX_CARDS) return false
  return value.every(item => item && (item.type === 'repeat'
    ? level.repeat && Number.isInteger(item.count) && item.count >= 2 && item.count <= 4 && Array.isArray(item.body) && item.body.length <= MAX_BODY && item.body.every((c: Command) => level.commands.includes(c))
    : level.commands.includes(item.type)))
}
export function restoreMaze(raw: string | null): MazeSave | null {
  if (!raw) return null
  try {
    const v = JSON.parse(raw) as MazeSave
    if (!v || v.version !== 1 || !Number.isInteger(v.level) || v.level < 0 || v.level >= levels.length
      || !Array.isArray(v.stars) || v.stars.length !== levels.length || !v.stars.every(n => Number.isInteger(n) && n >= 0 && n <= 3)
      || !Array.isArray(v.hints) || v.hints.length !== levels.length || !v.hints.every(n => Number.isSafeInteger(n) && n >= 0 && n <= 1_000_000)
      || v.stars.some((n, i) => n > 0 && i > 0 && v.stars[i - 1] === 0)
      || (v.level > 0 && v.stars[v.level - 1] === 0) || !isProgram(v.program, levels[v.level])) return null
    return { version: 1, level: v.level, program: v.program, stars: v.stars, hints: v.hints }
  } catch { return null }
}
