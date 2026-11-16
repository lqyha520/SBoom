import { experienceRank, freshExperience, integer, type ExperienceBase, type ExperienceDifficulty } from './experience-types'
import { shuffle,type Rng } from './random'
export const labObjects=[
  {id:'wood',name:'干燥小木块',icon:'🪵',floats:true,magnetic:false,note:'这块干燥木块的平均密度比水小，所以浮在水面。'},
  {id:'stone',name:'小石子',icon:'🪨',floats:false,magnetic:false,note:'这颗石子的密度比水大，所以沉到水底。'},
  {id:'cork',name:'软木塞',icon:'🟤',floats:true,magnetic:false,note:'软木里面有许多小气孔，平均密度小，能浮起来。'},
  {id:'clip',name:'铁制回形针',icon:'🖇️',floats:false,magnetic:true,note:'铁制回形针能被磁铁吸引；放入水中后会沉下去。'},
  {id:'copper',name:'铜片',icon:'🟠',floats:false,magnetic:false,note:'铜片会沉入水中，也不会被普通磁铁明显吸引。不是所有金属都能被吸引。'},
  {id:'foil',name:'压紧的铝箔球',icon:'⚪',floats:false,magnetic:false,note:'压紧、排掉空气后的铝箔球会下沉；铝不会被普通磁铁明显吸引。'},
{"id":"wax","name":"小蜡块","icon":"🕯️","floats":true,"magnetic":false,"note":"蜡的密度比水小，能浮在水面，也不会被磁铁吸引。"},{"id":"glass","name":"玻璃弹珠","icon":"🔵","floats":false,"magnetic":false,"note":"实心玻璃弹珠的密度比水大，会下沉，也不会被普通磁铁吸引。"},{"id":"screw","name":"铁制螺钉","icon":"🔩","floats":false,"magnetic":true,"note":"铁制螺钉能被磁铁吸引，放入水中会下沉。"},{"id":"ball","name":"密封空心塑料球","icon":"⚪","floats":true,"magnetic":false,"note":"里面的空气让整个球的平均密度比水小，所以能浮起来。"},{"id":"washer","name":"铁制垫圈","icon":"⭕","floats":false,"magnetic":true,"note":"铁制垫圈会下沉，也能被磁铁吸引。材料与形状都值得观察。"},{"id":"rubber","name":"实心橡皮块","icon":"🟣","floats":false,"magnetic":false,"note":"这块实心橡皮的密度比水大，会下沉；它不会被普通磁铁吸引。"}] as const
export const pigments=[{name:'红色',color:'#d88480'},{name:'黄色',color:'#e7c263'},{name:'蓝色',color:'#7aa5c6'}]
export const mixes=[{pair:[0,1],name:'橙色',color:'#dd9c65'},{pair:[0,2],name:'紫色',color:'#a18abb'},{pair:[1,2],name:'绿色',color:'#89ad85'}]
export type LabMission={type:'float'|'magnet';object:number;id:string}|{type:'mix';pair:number[];id:string}
export interface ScienceRound extends ExperienceBase {kind:'science-lab';missions:LabMission[];done:string[];journal:Array<{id:string;text:string}>}
export function newScience(difficulty:ExperienceDifficulty,rng:Rng,_stage=1):ScienceRound {
  const rank=experienceRank(difficulty),pool:LabMission[]=[...shuffle(Array.from({length:labObjects.length},(_,object):LabMission=>({type:'float',object,id:'float-'+object})),rng).slice(0,rank+1),...shuffle(Array.from({length:labObjects.length},(_,object):LabMission=>({type:'magnet',object,id:'magnet-'+object})),rng).slice(0,rank+1),...shuffle(mixes.map(mix=>({type:'mix' as const,pair:[...mix.pair],id:'mix-'+mix.pair.join('-')})),rng).slice(0,rank+1)]
  return {...freshExperience(),kind:'science-lab',missions:shuffle(pool,rng),done:[],journal:[]}
}
export function experiment(round:ScienceRound,type:LabMission['type'],object:number,pair:number[]=[]):{id:string;text:string;color?:string;floats?:boolean;magnetic?:boolean}|null {
  if(round.finished)return null
  let result:{id:string;text:string;color?:string;floats?:boolean;magnetic?:boolean}
  if(type==='mix') {if(pair.length!==2 || pair.some(value=>!integer(value,0,2)))return null;const sorted=[...pair].sort(),mix=mixes.find(mix=>mix.pair[0]===sorted[0] && mix.pair[1]===sorted[1]);result={id:'mix-'+sorted.join('-'),text:mix?`${pigments[sorted[0]].name}和${pigments[sorted[1]].name}颜料混合，得到${mix.name}。不同颜料的实际效果会有差别。`:'同一种颜色混合，颜色基本保持不变。',color:mix?.color||pigments[sorted[0]].color}}
  else {if(!integer(object,0,labObjects.length-1))return null;const item=labObjects[object];result={id:`${type}-${object}`,text:type==='float'?`${item.name}${item.floats?'浮起来了':'沉下去了'}。${item.note}`:`${item.name}${item.magnetic?'被吸过来了':'没有被吸过来'}。${item.note}`,floats:item.floats,magnetic:item.magnetic}}
  if(!round.done.includes(result.id)){round.done.push(result.id);round.journal.push({id:result.id,text:result.text});if(round.journal.length>20)round.journal.shift()}
  round.moves++;return result
}
export const sciencePassed=(round:ScienceRound)=>round.missions.every(mission=>round.done.includes(mission.id))
export function validScience(round:ScienceRound):boolean {return Array.isArray(round.missions) && [3,6,9].includes(round.missions.length) && round.missions.every(mission=>mission && (mission.type==='mix'?Array.isArray(mission.pair) && mission.pair.length===2 && mixes.some(mix=>JSON.stringify(mix.pair)===JSON.stringify(mission.pair)) && mission.id==='mix-'+mission.pair.join('-'):['float','magnet'].includes(mission.type) && integer(mission.object,0,labObjects.length-1) && mission.id===mission.type+'-'+mission.object)) && Array.isArray(round.done) && round.done.length<=40 && new Set(round.done).size===round.done.length && round.done.every(id=>typeof id==='string' && /^(float-(?:[0-9]|1[01])|magnet-(?:[0-9]|1[01])|mix-[0-2]-[0-2])$/.test(id)) && Array.isArray(round.journal) && round.journal.length<=20 && round.journal.every(item=>item && typeof item.id==='string' && round.done.includes(item.id) && typeof item.text==='string' && item.text.length<500)}
