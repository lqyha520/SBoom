import { experienceRank,freshExperience,integer,type ExperienceBase,type ExperienceDifficulty } from './experience-types'
import { shuffle,type Rng } from './random'
export const catchAnimals=[{name:'小兔',icon:'🐇',food:'🥕',foodName:'胡萝卜'},{name:'熊猫',icon:'🐼',food:'🎋',foodName:'竹子'},{name:'小猴',icon:'🐒',food:'🍌',foodName:'香蕉'},{name:'松鼠',icon:'🐿️',food:'🌰',foodName:'坚果'},{name:'小羊',icon:'🐑',food:'🌿',foodName:'青草'},{name:'小鸡',icon:'🐔',food:'🌾',foodName:'谷粒'}]
export const catchSpeeds=[{id:'gentle',name:'慢慢接',duration:5200,interval:2100},{id:'normal',name:'轻快接',duration:4000,interval:1600},{id:'quick',name:'挑战接',duration:3200,interval:1250}] as const
export interface CatchRound extends ExperienceBase {kind:'animal-catch';animal:number;goal:number;caught:number;missed:number;speed:typeof catchSpeeds[number]['id'];team?:number[];streak?:number;bestStreak?:number}
export function newCatch(difficulty:ExperienceDifficulty,rng:Rng,stage=1):CatchRound {const rank=experienceRank(difficulty),team=shuffle(Array.from({length:catchAnimals.length},(_,index)=>index),rng).slice(0,Math.min(6,rank+2+Math.floor((stage-1)/4)));return {...freshExperience(),kind:'animal-catch',animal:team[0],goal:Math.min([12,16,20][rank],[6,10,14][rank]+Math.floor((stage-1)/3)*2),caught:0,missed:0,speed:catchSpeeds[rank].id,team,streak:0,bestStreak:0}}
export function catchFood(round:CatchRound,food:number,hit:boolean):'good'|'wrong'|'miss'|null {
  if(round.finished || !integer(food,0,catchAnimals.length-1))return null
  round.moves++
  if(food===round.animal){if(hit){round.caught++;round.streak=(round.streak || 0)+1;round.bestStreak=Math.max(round.bestStreak || 0,round.streak);if(round.team)round.animal=round.team[Math.min(round.team.length-1,Math.floor(round.caught/Math.ceil(round.goal/round.team.length)))];return 'good'}round.missed++;round.streak=0;return 'miss'}
  if(hit){round.mistakes++;round.streak=0;return 'wrong'}return 'miss'
}
export const catchPassed=(round:CatchRound)=>round.caught>=round.goal
export function validCatch(round:CatchRound):boolean {return integer(round.animal,0,catchAnimals.length-1) && integer(round.goal,6,20) && round.goal%2===0 && integer(round.caught,0,round.goal) && integer(round.missed) && catchSpeeds.some(speed=>speed.id===round.speed) && (round.team===undefined || Array.isArray(round.team) && round.team.length>=2 && round.team.length<=6 && new Set(round.team).size===round.team.length && round.team.every(animal=>integer(animal,0,catchAnimals.length-1)) && round.animal===round.team[Math.min(round.team.length-1,Math.floor(round.caught/Math.ceil(round.goal/round.team.length)))]) && (round.streak===undefined || integer(round.streak,0,round.caught)) && (round.bestStreak===undefined || integer(round.bestStreak,round.streak || 0,round.caught))}
