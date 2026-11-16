import { experienceRank, freshExperience, integer, numberList, type ExperienceBase, type ExperienceDifficulty } from './experience-types'
import { shuffle,type Rng } from './random'
export const crops = [{id:'carrot',name:'胡萝卜',icon:'🥕',days:2},{id:'wheat',name:'小麦',icon:'🌾',days:2},{id:'tomato',name:'番茄',icon:'🍅',days:3},{id:'corn',name:'玉米',icon:'🌽',days:3},{id:'berry',name:'草莓',icon:'🍓',days:2},{id:'pumpkin',name:'南瓜',icon:'🎃',days:4}] as const
export const farmAnimals = [{name:'小兔',icon:'🐇',food:0},{name:'小鸡',icon:'🐔',food:1},{name:'小牛',icon:'🐄',food:1}]
export interface FarmPlot { crop: number; growth: number; watered: boolean }
export interface FarmRound extends ExperienceBase { kind:'little-farm'; day:number; plots:FarmPlot[]; inventory:number[]; harvested:number; fed:number[]; goal:number; orders?:number[]; delivered?:number[] }
export function newFarm(difficulty:ExperienceDifficulty,rng:Rng=Math.random,stage=1):FarmRound {
  const rank=experienceRank(difficulty),orders=Array(crops.length).fill(0),available=shuffle(Array.from({length:crops.length},(_,index)=>index),rng)
  for(const index of available.slice(0,Math.min(4,2+rank)))orders[index]=1+((stage+index)%Math.min(3,rank+2))
  return {...freshExperience(),kind:'little-farm',day:1,plots:Array.from({length:rank?6:4},()=>({crop:-1,growth:0,watered:false})),inventory:Array(crops.length).fill(0),harvested:0,fed:Array(rank?3:2).fill(0),goal:orders.reduce((a,b)=>a+b,0),orders,delivered:Array(crops.length).fill(0)}
}
export function deliverFarm(round:FarmRound,index:number):boolean {
  if(round.finished || !round.orders || !round.delivered || !integer(index,0,crops.length-1) || round.delivered[index]>=round.orders[index] || !round.inventory[index])return false
  round.inventory[index]--;round.delivered[index]++;round.moves++;return true
}
export function farmNeeds(round:FarmRound):number[] {
  const needs=(round.orders||Array(crops.length).fill(0)).map((count,index)=>count-(round.delivered?.[index]||0))
  round.fed.forEach((fed,index)=>{if(!fed)needs[farmAnimals[index].food]++})
  round.inventory.forEach((count,index)=>needs[index]-=count)
  round.plots.forEach(plot=>{if(plot.crop>=0)needs[plot.crop]--})
  return needs.map(count=>Math.max(0,count))
}
export function farmBatch(round:FarmRound,tool:'water'|'harvest'):number {
  let changed=0;round.plots.forEach((_,index)=>{if(farmPlot(round,index,tool))changed++});return changed
}
export const farmSeason = (day:number) => ['春天','夏天','秋天','冬天'][Math.floor((day-1)/3)%4]
export function farmPlot(round:FarmRound,index:number,tool:'plant'|'water'|'harvest',crop=0):boolean {
  const plot=round.plots[index];if(round.finished || !plot)return false
  if(tool==='plant'){if(plot.crop!==-1 || !integer(crop,0,crops.length-1))return false;plot.crop=crop;plot.growth=0;plot.watered=false}
  else if(tool==='water'){if(plot.crop===-1 || plot.watered || plot.growth>=crops[plot.crop].days)return false;plot.watered=true}
  else {if(plot.crop===-1 || plot.growth<crops[plot.crop].days)return false;round.inventory[plot.crop]++;round.harvested++;plot.crop=-1;plot.growth=0;plot.watered=false}
  round.moves++;return true
}
export function farmDay(round:FarmRound):boolean {if(round.finished || round.day>=10000)return false;round.plots.forEach(plot=>{if(plot.crop>=0 && plot.watered)plot.growth=Math.min(crops[plot.crop].days,plot.growth+1);plot.watered=false});round.day++;round.moves++;return true}
export function feedFarm(round:FarmRound,index:number):boolean {if(round.finished || !integer(index,0,round.fed.length-1) || round.fed[index])return false;const food=farmAnimals[index].food;if(!round.inventory[food])return false;round.inventory[food]--;round.fed[index]=1;round.moves++;return true}
export const farmPassed=(round:FarmRound)=>round.harvested>=round.goal && round.fed.every(Boolean) && (!round.orders || !!round.delivered && round.orders.every((count,index)=>round.delivered![index]>=count))
export function validFarm(round:FarmRound):boolean {return integer(round.day,1,10000) && integer(round.goal,1,12) && integer(round.harvested) && (numberList(round.inventory,0,10000,3) || numberList(round.inventory,0,10000,crops.length)) && (round.orders===undefined || numberList(round.orders,0,3,crops.length) && numberList(round.delivered,0,3,crops.length) && round.delivered.every((count,index)=>count<=round.orders![index])) && numberList(round.fed,0,1) && [2,3].includes(round.fed.length) && Array.isArray(round.plots) && [4,6].includes(round.plots.length) && round.plots.every(plot=>plot && integer(plot.crop,-1,round.inventory.length-1) && integer(plot.growth,0,4) && (plot.crop<0?plot.growth===0:plot.growth<=crops[plot.crop].days) && typeof plot.watered==='boolean')}
