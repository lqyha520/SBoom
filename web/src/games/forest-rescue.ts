import { experienceRank,freshExperience,integer,type ExperienceBase,type ExperienceDifficulty } from './experience-types'
import { forestEpisodes } from './forest-missions'
export interface ForestChoice {id:string;label:string;next:string;message:string;rescue?:string;unsafe?:boolean}
export const forestScenes:Record<string,{title:string;text:string;animal:string;place:string;choices:ForestChoice[]}>= {
  start:{title:'护林站集合',text:'你和护林员一起出发。小队听到小鸟叫声，先选一条安全的路线吧。',animal:'🧑‍🌾',place:'营地',choices:[{id:'sign',label:'按地图和路标走',next:'sign',message:'你把地图装进小背包，沿着标记清楚的小路前进。'},{id:'guide',label:'请护林员带路',next:'bird',message:'护林员带你走熟悉的林间小路，一路介绍树木。'}]},
  sign:{title:'岔路口的发现',text:'路标指向树林，另一条小路通往观察台。你想怎样继续？',animal:'🌳',place:'林间小路',choices:[{id:'direct',label:'沿路标去树林',next:'bird',message:'你认真辨认路标，来到了小鸟附近。'},{id:'view',label:'和护林员去观察台看看',next:'view',message:'你们绕到观察台，远远看见鸟巢的位置。'}]},
  view:{title:'观察台上的鸟巢',text:'远处的树上有一个鸟巢。安静观察时，你发现地上的小鸟还在扑动翅膀。',animal:'🔭',place:'观察台',choices:[{id:'quiet',label:'保持安静，和护林员去查看',next:'bird',message:'你记下鸟巢的位置，也给动物留出安静的空间。'}]},
  bird:{title:'树林里的小鸟',text:'一只幼鸟落在树下。它的亲鸟可能就在附近，先由护林员判断它是否需要帮助。',animal:'🐦',place:'树林',choices:[{id:'observe',label:'远远观察，请护林员判断',next:'creek',rescue:'bird',message:'护林员确认幼鸟正在学飞。你们留出空间，亲鸟回来照顾它。'},{id:'report',label:'告诉护林员鸟巢的位置',next:'creek',rescue:'bird',message:'你提供了鸟巢线索，护林员仔细确认幼鸟安全后继续前进。'},{id:'chase',label:'追着小鸟，把它带回家',next:'bird',unsafe:true,message:'追赶会让小鸟害怕，野生动物也不适合带回家。先保持距离，请护林员判断。'}]},
  creek:{title:'小溪边的乌龟',text:'乌龟旁边有塑料袋。你和护林员站在岸上观察，怎样帮它恢复干净的环境？',animal:'🐢',place:'小溪',choices:[{id:'clean',label:'用夹子收走岸边垃圾',next:'clean',rescue:'turtle',message:'在护林员陪同下，你用夹子收起岸边的塑料袋，没有进入水里。'},{id:'ask',label:'请护林员清理，自己记录位置',next:'clearing',rescue:'turtle',message:'你准确描述了垃圾的位置，护林员完成清理，小溪又干净了。'},{id:'water',label:'自己跳进小溪寻找垃圾',next:'creek',unsafe:true,message:'小溪的水深和水流不容易判断。留在岸上，交给同行的护林员处理。'}]},
  clean:{title:'垃圾带回收集站',text:'垃圾已经装好。要把它放在哪里，才能继续保护小溪？',animal:'♻️',place:'岸边',choices:[{id:'take',label:'带到营地的垃圾收集站',next:'clearing',message:'小队带走垃圾，也没有打扰小溪里的动物。'}]},
  clearing:{title:'草地上的小兔',text:'倒下的树枝挡住了小兔离开的路。护林员检查后，准备清理树枝。你可以怎样配合？',animal:'🐇',place:'草地',choices:[{id:'space',label:'退后一点，留出离开的路',next:'home',rescue:'rabbit',message:'你给小兔留出足够空间。护林员移开树枝，小兔自己跑回草丛。'},{id:'quiet',label:'提醒伙伴保持安静',next:'home',rescue:'rabbit',message:'大家安静等待，小兔沿护林员清理出的通道回到了草丛。'},{id:'grab',label:'把小兔抓起来检查',next:'clearing',unsafe:true,message:'陌生人的抓抱会让野生动物紧张。保持距离，让护林员处理障碍。'}]},
  home:{title:'带着故事回营地',text:'小鸟、乌龟和小兔都得到了合适的帮助。你学会了观察、合作，也懂得给动物留出空间。',animal:'🏕️',place:'营地',choices:[]},
}
forestEpisodes.forEach((episode,tour)=>{
  const prefix=`tour-${tour}`
  forestScenes[prefix+'-hub']={title:episode.title,text:'护林员带来了三条新线索。先选择一个地点，观察发现，再决定怎样配合。',animal:'🧑‍🌾',place:'护林站',choices:episode.missions.map((mission,index)=>({id:`${prefix}-visit-${index}`,label:'前往'+mission.place+'：'+mission.name,next:`${prefix}-${index}-observe`,message:'小队沿指定小路前往'+mission.place+'。'}))}
  episode.missions.forEach((mission,index)=>{
    const id=`${prefix}-${index}`
    forestScenes[id+'-observe']={title:mission.name,animal:mission.animal,place:mission.place,text:mission.question,choices:[{id:id+'-observe',label:mission.observe,next:id+'-action',message:mission.clue},{id:id+'-wrong',label:mission.wrong,next:id+'-observe',unsafe:true,message:'先保持距离，和护林员一起观察，判断动物真正需要什么。'}]}
    forestScenes[id+'-action']={title:'根据线索行动',animal:mission.animal,place:mission.place,text:mission.clue,choices:[{id:id+'-help',label:mission.action,next:prefix+'-hub',rescue:id,message:mission.result},{id:id+'-watch',label:'再安静观察一会儿',next:id+'-action',message:'小队继续保持距离观察，随后可以按线索采取合适行动。'}]}
  })
  forestScenes[prefix+'-home']={title:episode.title+'完成',text:'三条巡护线索都处理好了。你观察到了不同的环境问题，也学会了和护林员分工合作。',animal:'🏕️',place:'护林站',choices:[]}
})
export interface ForestRound extends ExperienceBase {kind:'forest-rescue';scene:string;rescued:string[];log:Array<{choice:string;text:string}>;level:number;episode?:number}
export function newForest(difficulty:ExperienceDifficulty,stage=1):ForestRound {const episode=stage===1?undefined:(stage-2)%forestEpisodes.length;return {...freshExperience(),kind:'forest-rescue',scene:episode===undefined?'start':`tour-${episode}-hub`,rescued:[],log:[],level:experienceRank(difficulty),...(episode===undefined?{}:{episode})}}
export function forestScene(round:ForestRound){const scene=forestScenes[round.scene];return round.scene.endsWith('-hub')?{...scene,choices:scene.choices.filter(choice=>!round.rescued.includes(choice.next.replace('-observe','')))}:scene}
export function forestStops(round:ForestRound){return round.episode===undefined?[{animal:'🐦',place:'树林',id:'bird'},{animal:'🐢',place:'小溪',id:'turtle'},{animal:'🐇',place:'草地',id:'rabbit'}]:forestEpisodes[round.episode].missions.map((mission,index)=>({animal:mission.animal,place:mission.place,id:`tour-${round.episode}-${index}`}))}
export function forestChoose(round:ForestRound,index:number):string|null {
  const choice=forestScene(round)?.choices[index];if(round.finished || !choice || round.log.length>=500)return null
  round.moves++;if(choice.unsafe)round.mistakes++;else {round.scene=round.level===0 && choice.next==='sign'?'bird':choice.next;if(choice.rescue && !round.rescued.includes(choice.rescue))round.rescued.push(choice.rescue)}
  if(round.episode!==undefined && round.rescued.length===3)round.scene=`tour-${round.episode}-home`
  round.log.push({choice:choice.id,text:choice.message});return choice.message
}
export const forestPassed=(round:ForestRound)=>(round.scene==='home' || round.scene.endsWith('-home')) && round.rescued.length===3
export function validForest(round:ForestRound):boolean {return (round.episode===undefined || integer(round.episode,0,forestEpisodes.length-1) && round.scene.startsWith(`tour-${round.episode}-`)) && typeof round.scene==='string' && !!forestScenes[round.scene] && integer(round.level,0,2) && Array.isArray(round.rescued) && round.rescued.length<=3 && new Set(round.rescued).size===round.rescued.length && round.rescued.every(id=>forestStops(round).some(stop=>stop.id===id)) && Array.isArray(round.log) && round.log.length<=500 && round.log.every(item=>item && typeof item.choice==='string' && Object.values(forestScenes).some(scene=>scene.choices.some(choice=>choice.id===item.choice)) && typeof item.text==='string' && item.text.length<=300)}
