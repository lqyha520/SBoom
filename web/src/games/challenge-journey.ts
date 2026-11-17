import { randomInt, shuffle, type Rng } from './random'

export type ChallengeDifficulty = 'starter' | 'explorer' | 'master'
export interface ChallengeRound { seed?: number; stage?: number; challenge?: string }
export interface ChallengeJourney {
  completed: Record<ChallengeDifficulty, number>
  recent: Record<ChallengeDifficulty, string[]>
  stars: Record<string, number>
}
const difficulties: ChallengeDifficulty[] = ['starter', 'explorer', 'master']
export const freshJourney = (): ChallengeJourney => ({ completed: { starter: 0, explorer: 0, master: 0 }, recent: { starter: [], explorer: [], master: [] }, stars: {} })
export function seededRandom(seed: number): Rng {
  let state = seed >>> 0
  return () => { state += 0x6d2b79f5; let value = state; value = Math.imul(value ^ value >>> 15, value | 1); value ^= value + Math.imul(value ^ value >>> 7, value | 61); return ((value ^ value >>> 14) >>> 0) / 4294967296 }
}
export function challengeFingerprint(value: unknown): string {
  let hash = 2166136261
  for (const char of JSON.stringify(value)) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619)
  return (hash >>> 0).toString(36)
}
export function createChallenge<T extends ChallengeRound>(factory: (rng: Rng, stage: number) => T, difficulty: ChallengeDifficulty, journey: ChallengeJourney, rng: Rng = Math.random): T {
  const stage = journey.completed[difficulty] + 1, seed = randomInt(rng, 0, 0xffffffff)
  let round: T, signature = ''
  for (let attempt = 0; ; attempt++) {
    const nextSeed = (seed + Math.imul(attempt, 2654435761)) >>> 0
    round = factory(seededRandom(nextSeed), stage); signature = challengeFingerprint(round)
    round.seed = nextSeed; round.stage = stage; round.challenge = signature
    if (!journey.recent[difficulty].includes(signature) || attempt >= 31) break
  }
  journey.recent[difficulty] = [...journey.recent[difficulty].filter(id => id !== signature), signature].slice(-24)
  return round
}
export function completeChallenge(journey: ChallengeJourney | undefined, difficulty: ChallengeDifficulty, round: ChallengeRound, stars: number) {
  if (!journey || round.stage === undefined || !round.challenge) return
  journey.completed[difficulty] = Math.max(journey.completed[difficulty], round.stage)
  const key = difficulty + ':' + round.challenge
  journey.stars[key] = Math.max(journey.stars[key] || 0, stars)
  const keys = Object.keys(journey.stars)
  for (const key of keys.slice(0, Math.max(0, keys.length - 256))) delete journey.stars[key]
}
export function validJourney(value: unknown): boolean {
  if (value === undefined) return true
  const journey = value as ChallengeJourney
  return !!journey && !!journey.completed && !!journey.recent && !!journey.stars && difficulties.every(id => Number.isSafeInteger(journey.completed[id]) && journey.completed[id] >= 0 && journey.completed[id] <= 1_000_000 && Array.isArray(journey.recent[id]) && journey.recent[id].length <= 24 && journey.recent[id].every(key => typeof key === 'string' && /^[a-z0-9]{1,12}$/.test(key))) && Object.keys(journey.stars).length <= 256 && Object.entries(journey.stars).every(([key, stars]) => /^(starter|explorer|master):[a-z0-9]{1,12}$/.test(key) && Number.isInteger(stars) && stars >= 1 && stars <= 3)
}
export function validChallenge(round: ChallengeRound): boolean {
  return (round.seed === undefined || Number.isSafeInteger(round.seed) && round.seed >= 0 && round.seed <= 0xffffffff) && (round.stage === undefined || Number.isSafeInteger(round.stage) && round.stage >= 1 && round.stage <= 1_000_001) && (round.challenge === undefined || typeof round.challenge === 'string' && /^[a-z0-9]{1,12}$/.test(round.challenge))
}
/** 优先用未出现内容；用尽后从最早出现的内容开始轮换。 */
export function contentDeck<T>(pool: T[], count: number, key: (value: T) => string, history: string[], rng: Rng): T[] {
  const unseen = shuffle(pool.filter(value => !history.includes(key(value))), rng)
  const previous = pool.filter(value => history.includes(key(value))).sort((a, b) => history.lastIndexOf(key(a)) - history.lastIndexOf(key(b)))
  return [...unseen, ...previous].slice(0, count)
}
export interface ContentHistory { contentHistory?: Partial<Record<ChallengeDifficulty, string[]>> }
export function rememberContent(save: ContentHistory, difficulty: ChallengeDifficulty, ids: string[]): string[] {
  save.contentHistory ||= {}
  const history = [...(save.contentHistory[difficulty] || []).filter(id => !ids.includes(id)), ...ids].slice(-256)
  save.contentHistory[difficulty] = history
  return history
}
export function validContentHistory(value: unknown): boolean {
  return value === undefined || !!value && typeof value === 'object' && Object.entries(value).every(([key, list]) => difficulties.includes(key as ChallengeDifficulty) && Array.isArray(list) && list.length <= 256 && list.every(id => typeof id === 'string' && id.length <= 80))
}
