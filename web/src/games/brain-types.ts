import type { ChallengeRound } from './challenge-journey'
export const brainIds = ['tangram', 'sokoban', 'pattern-train', 'one-stroke', 'balance-scale', 'color-sort', 'mirror-draw', 'spot-difference'] as const
export type BrainId = typeof brainIds[number]
export const isBrainId = (id: unknown): id is BrainId => brainIds.some(value => value === id)
export interface BrainBase extends ChallengeRound { moves: number; hints: number; mistakes: number; finished: boolean }
export const freshBrain = (): BrainBase => ({ moves: 0, hints: 0, mistakes: 0, finished: false })
