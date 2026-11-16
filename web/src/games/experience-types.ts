import type { ChallengeRound } from './challenge-journey'
import type { PuzzleDifficulty } from './puzzle-games'
export type { PuzzleDifficulty as ExperienceDifficulty }
export const experienceIds = ['rhythm-band','little-farm','science-lab','forest-rescue','creative-studio','animal-catch','daily-life','eco-guardian'] as const
export type ExperienceId = typeof experienceIds[number]
export const isExperienceId = (id: unknown): id is ExperienceId => experienceIds.some(value => value === id)
export interface ExperienceBase extends ChallengeRound { moves: number; mistakes: number; hints: number; finished: boolean }
export const freshExperience = (): ExperienceBase => ({ moves: 0, mistakes: 0, hints: 0, finished: false })
export const experienceRank = (difficulty: PuzzleDifficulty) => ['starter','explorer','master'].indexOf(difficulty)
export const integer = (value: unknown, min = 0, max = 1_000_000): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max
export const numberList = (value: unknown, min: number, max: number, length?: number): value is number[] => Array.isArray(value) && (length === undefined || value.length === length) && value.every(item => integer(item,min,max))
export const sameList = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right)
