import { experienceRank, freshExperience, integer, numberList, type ExperienceBase, type ExperienceDifficulty } from './experience-types'
import { randomInt, type Rng } from './random'
export const instruments = [{name:'大鼓',icon:'🥁',color:'#d59c80'},{name:'小鼓',icon:'🪘',color:'#83acb6'},{name:'木琴',icon:'🎹',color:'#a591c0'},{name:'铃铛',icon:'🔔',color:'#c4b071'}]
export interface MusicRound extends ExperienceBase { kind: 'rhythm-band'; bpm: number; pattern: number[]; hits: number[]; grid: number[][]; mode: 'follow' | 'compose'; wrongBeats?: number[] }
export function newMusic(difficulty: ExperienceDifficulty, rng: Rng, stage = 1): MusicRound {
  const rank=experienceRank(difficulty), length=Math.min(16,[6,8,12][rank]+Math.floor((stage-1)/3)*2)
  return {...freshExperience(),kind:'rhythm-band',bpm:Math.min(120,[72,90,108][rank]+Math.min(stage-1,12)*2),pattern:Array.from({length},(_,index)=>index%4===0?0:randomInt(rng,0,Math.min(3,rank+1+Math.floor((stage-1)/3)))),hits:Array(length).fill(0),grid:Array.from({length:4},()=>Array(8).fill(0)),mode:'follow'}
}
export function musicTap(round: MusicRound, instrument: number, elapsed: number): 'hit' | 'wrong' | 'outside' {
  if(round.finished || !integer(instrument,0,3) || !Number.isFinite(elapsed))return 'outside'
  const beat=60000/round.bpm, index=Math.round(elapsed/beat)-1
  if(index<0 || index>=round.pattern.length || Math.abs(elapsed-(index+1)*beat)>beat*.4 || round.hits[index])return 'outside'
  round.moves++
  if(round.pattern[index]!==instrument){if(round.wrongBeats?.includes(index))return 'outside';(round.wrongBeats ||= []).push(index);round.mistakes++;return 'wrong'}
  round.hits[index]=1;return 'hit'
}
export const musicPassed = (round: MusicRound) => round.hits.reduce((sum,value)=>sum+value,0)>=Math.ceil(round.pattern.length*.7)
export function validMusic(value: MusicRound): boolean {
  return integer(value.bpm,48,144) && numberList(value.pattern,0,3) && integer(value.pattern.length,6,16) && value.pattern.length%2===0 && numberList(value.hits,0,1,value.pattern.length) && ['follow','compose'].includes(value.mode) && Array.isArray(value.grid) && value.grid.length===4 && value.grid.every(row=>numberList(row,0,1) && [8,12,16].includes(row.length) && row.length===value.grid[0].length) && (value.wrongBeats===undefined || numberList(value.wrongBeats,0,value.pattern.length-1) && new Set(value.wrongBeats).size===value.wrongBeats.length)
}
