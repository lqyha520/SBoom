import { describe, expect, it } from 'vitest'
import {
  compileProgram, levels, moveRobot, newMaze, restoreMaze, resultOf, starsFor, startRobot,
  type Command, type Instruction,
} from '../games/robot-maze'

const f: Command = 'forward'
const l: Command = 'left'
const r: Command = 'right'
const commands = (...items: Command[]): Instruction[] => items.map(type => ({ type }))
const repeat = (count: number, ...body: Command[]): Instruction => ({ type: 'repeat', count, body })
const solutions: Instruction[][] = [
  commands(f, f, f, f),
  commands(f, f, f, f),
  commands(f, f, f, l, f, f, f),
  commands(f, f, r, f, f, f, f, r, f, f),
  commands(f, f, f, r, f, f, l, f),
  commands(l, f, f, r, f, f, f, f, r, f, f),
  [repeat(4, f)],
  [repeat(2, f, l, f, r), ...commands(f)],
  [repeat(4, f, f, f, r)],
]

describe('机器人闯迷宫', () => {
  it.each(levels.map((level, index) => ({ level, index })))('第 $index 关存在符合三星积木预算的路线', ({ level, index }) => {
    let robot = startRobot(level)
    for (const { command } of compileProgram(solutions[index])) {
      const next = moveRobot(level, robot, command)
      expect(next.blocked).toBe(false)
      robot = next.robot
    }
    expect(resultOf(level, robot)).toBe('success')
    expect(starsFor(level, solutions[index], 0)).toBe(3)
    expect(robot.collected).toHaveLength(level.gears.length)
  })

  it('转向相对于机器人，转弯不移动且四次右转回到原朝向', () => {
    const level = levels[2]
    const start = startRobot(level)
    const turned = moveRobot(level, start, l).robot
    expect(turned).toMatchObject({ x: start.x, y: start.y, direction: 0 })
    let robot = turned
    for (let i = 0; i < 4; i++) robot = moveRobot(level, robot, r).robot
    expect(robot).toEqual(turned)
    expect(start.direction).toBe(1)
  })

  it('走向水面、石块、地图外时停在原位置，原状态不变', () => {
    const level = levels[0]
    const start = startRobot(level)
    for (const direction of [0, 2, 3] as const) {
      const robot = { ...start, direction }
      expect(moveRobot(level, robot, f)).toEqual({ robot, blocked: true })
    }
  })

  it('重复动作按轮次展开，执行时能定位到外层积木和内部动作', () => {
    expect(compileProgram([repeat(2, f, r), ...commands(l)])).toEqual([
      { command: f, card: 0, inner: 0, iteration: 1 }, { command: r, card: 0, inner: 1, iteration: 1 },
      { command: f, card: 0, inner: 0, iteration: 2 }, { command: r, card: 0, inner: 1, iteration: 2 },
      { command: l, card: 1, inner: null, iteration: 1 },
    ])
  })

  it('到终点仍需拿全零件，停在其他位置不会通关；返回零件位置不重复计数', () => {
    const level = levels[5]
    let robot = startRobot(level)
    expect(resultOf(level, robot)).toBe('unfinished')
    for (let i = 0; i < 4; i++) robot = moveRobot(level, robot, f).robot
    expect(resultOf(level, robot)).toBe('missing')
    const gearRobot = { x: 1, y: 1, direction: 1 as const, collected: ['2,1'] }
    expect(moveRobot(level, gearRobot, f).robot.collected).toEqual(['2,1'])
  })

  it('独立解法按积木数给星，使用提示记为一次引导通关', () => {
    expect(starsFor(levels[6], commands(f, f, f, f), 0)).toBe(2)
    expect(starsFor(levels[6], [repeat(4, f)], 1)).toBe(1)
  })

  it('恢复合法关卡、循环程序和得星记录', () => {
    const save = newMaze()
    save.level = 6; save.stars = levels.map((_, i) => i < 6 ? 3 : 0)
    save.program = [repeat(4, f)]
    expect(restoreMaze(JSON.stringify(save))).toEqual(save)
    expect(restoreMaze(JSON.stringify(newMaze()))).toEqual(newMaze())
  })

  it('拒绝锁定关卡、非法循环、超大程序、损坏数据', () => {
    const initial = newMaze()
    const unlocked = { ...initial, level: 6, stars: levels.map((_, i) => i < 6 ? 3 : 0) }
    for (const value of [
      null, [], { ...initial, version: 2 }, { ...initial, level: 1 },
      { ...initial, stars: [0, 3, ...Array(7).fill(0)] }, { ...initial, hints: [] },
      { ...initial, program: commands(l) }, { ...initial, program: Array(13).fill({ type: f }) },
      { ...unlocked, program: [{ type: 'repeat', count: 1000, body: [f] }] },
      { ...unlocked, program: [{ type: 'repeat', count: 2, body: [repeat(2, f)] }] },
      { ...unlocked, program: [{ type: 'repeat', count: 2, body: Array(7).fill(f) }] },
    ]) expect(restoreMaze(JSON.stringify(value))).toBeNull()
    expect(restoreMaze('broken')).toBeNull()
  })
})
