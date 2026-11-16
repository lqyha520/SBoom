import { completeChallenge, createChallenge, freshJourney, seededRandom, validChallenge, validJourney, type ChallengeJourney } from './challenge-journey'
import { integer,isExperienceId,type ExperienceBase,type ExperienceDifficulty,type ExperienceId } from './experience-types'
import { newMusic,validMusic,type MusicRound } from './music-studio'
import { farmPassed,newFarm,validFarm,type FarmRound } from './little-farm'
import { newScience,sciencePassed,validScience,type ScienceRound } from './science-lab'
import { forestPassed,newForest,validForest,type ForestRound } from './forest-rescue'
import { artPassed,newArt,validArt,type ArtRound } from './creative-studio'
import { catchPassed,newCatch,validCatch,type CatchRound } from './animal-catch'
import { lifePassed,newLife,validLife,type LifeRound } from './daily-life'
import { ecoPassed,newEco,validEco,type EcoRound } from './eco-guardian'
import type { Rng } from './random'
export { experienceIds,isExperienceId } from './experience-types'
export type { ExperienceId,ExperienceDifficulty }
export interface ExperienceRoundMap {'rhythm-band':MusicRound;'little-farm':FarmRound;'science-lab':ScienceRound;'forest-rescue':ForestRound;'creative-studio':ArtRound;'animal-catch':CatchRound;'daily-life':LifeRound;'eco-guardian':EcoRound}
export type ExperienceRound = ExperienceRoundMap[ExperienceId]
export interface ExperienceSave<I extends ExperienceId=ExperienceId> {version:1;difficulty:ExperienceDifficulty;round:ExperienceRoundMap[I];best:Record<ExperienceDifficulty,number>;rounds:number;journey?:ChallengeJourney}
export function newExperience<I extends ExperienceId>(id:I,difficulty:ExperienceDifficulty='starter',rng:Rng=Math.random,journey:ChallengeJourney=freshJourney(),retry?:ExperienceRoundMap[I]):ExperienceSave<I> {
  const factory=(random:Rng,stage:number)=>{
    const factories={'rhythm-band':()=>newMusic(difficulty,random,stage),'little-farm':()=>newFarm(difficulty,random,stage),'science-lab':()=>newScience(difficulty,random,stage),'forest-rescue':()=>newForest(difficulty,stage),'creative-studio':()=>newArt(stage),'animal-catch':()=>newCatch(difficulty,random,stage),'daily-life':()=>newLife(difficulty,random,stage),'eco-guardian':()=>newEco(difficulty,random,stage)}
    return factories[id]() as ExperienceRoundMap[I]
  }
  const round=retry?.seed!==undefined?Object.assign(factory(seededRandom(retry.seed),retry.stage || 1),{seed:retry.seed,stage:retry.stage,challenge:retry.challenge}):createChallenge(factory,difficulty,journey,rng)
  return {version:1,difficulty,round,best:{starter:0,explorer:0,master:0},rounds:0,journey}
}
export const experienceStars=(round:ExperienceBase)=>round.mistakes===0 && round.hints===0?3:round.mistakes<=3 && round.hints<=2?2:1
export function experiencePassed(round:ExperienceRound):boolean {switch(round.kind){case 'rhythm-band':return false;case 'little-farm':return farmPassed(round);case 'science-lab':return sciencePassed(round);case 'forest-rescue':return forestPassed(round);case 'creative-studio':return artPassed(round);case 'animal-catch':return catchPassed(round);case 'daily-life':return lifePassed(round);case 'eco-guardian':return ecoPassed(round)}}
export function finishExperience(save:ExperienceSave,passed=experiencePassed(save.round)):boolean {if(save.round.finished || !passed)return false;save.round.finished=true;const completed = save.journey?.completed[save.difficulty] || 0;if(!save.round.stage || save.round.stage>completed)save.rounds++;completeChallenge(save.journey,save.difficulty,save.round,experienceStars(save.round));save.best[save.difficulty]=Math.max(save.best[save.difficulty],experienceStars(save.round));return true}
export function restoreExperience<I extends ExperienceId>(raw:string|null,id:I):ExperienceSave<I>|null {
  if(!raw || raw.length>2048*1024 || !isExperienceId(id))return null
  try {
    const save=JSON.parse(raw) as ExperienceSave<I>,round=save.round
    if(!save || save.version!==1 || !['starter','explorer','master'].includes(save.difficulty) || !integer(save.rounds) || !save.best || !['starter','explorer','master'].every(level=>integer(save.best[level as ExperienceDifficulty],0,3)))return null
    if(!validJourney(save.journey) || !round || !validChallenge(round) || round.kind!==id || typeof round.finished!=='boolean' || ![round.moves,round.mistakes,round.hints].every(value=>integer(value)))return null
    const validators={'rhythm-band':validMusic,'little-farm':validFarm,'science-lab':validScience,'forest-rescue':validForest,'creative-studio':validArt,'animal-catch':validCatch,'daily-life':validLife,'eco-guardian':validEco}
    if(!(validators[id] as (value:ExperienceRound)=>boolean)(round))return null
    if(round.kind!=='rhythm-band' && round.finished!==experiencePassed(round))return null
    if(round.kind==='rhythm-band' && round.finished && round.hits.reduce((sum,value)=>sum+value,0)<Math.ceil(round.pattern.length*.7))return null
    if(round.kind==='little-farm' && round.inventory.length===3)round.inventory.push(0,0,0)
    if(!save.journey){save.journey=freshJourney();save.journey.completed[save.difficulty]=save.rounds}
    return save
  }catch{return null}
}
