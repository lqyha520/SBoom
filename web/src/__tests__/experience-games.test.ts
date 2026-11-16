import { describe,expect,it } from 'vitest'
import { experienceIds,finishExperience,newExperience,restoreExperience,type ExperienceSave } from '../games/experience-games'
import { instruments,musicPassed,musicTap } from '../games/music-studio'
import { crops,deliverFarm,farmAnimals,farmDay,farmPlot,feedFarm } from '../games/little-farm'
import { experiment } from '../games/science-lab'
import { forestChoose,forestScenes } from '../games/forest-rescue'
import { addArt,saveArtwork,setArtBackground } from '../games/creative-studio'
import { catchFood } from '../games/animal-catch'
import { crossRoad,observeRoad,selectLife,submitLife,waitRoad,weatherOutfits } from '../games/daily-life'
import { careEco,ecoLitter,sortLitter } from '../games/eco-guardian'
import { cloudGames,games,validSave } from '../games/catalog'
const seeded=(value:number)=>()=>{value=(Math.imul(value,1664525)+1013904223)>>>0;return value/4294967296}
function solve(save:ExperienceSave){const round=save.round
  switch(round.kind){
    case 'rhythm-band':round.pattern.forEach((instrument,index)=>expect(musicTap(round,instrument,(index+1)*60000/round.bpm)).toBe('hit'));finishExperience(save,musicPassed(round));break
    case 'little-farm': {
      const needed = [...round.orders!]
      round.fed.forEach((_,index)=>needed[farmAnimals[index].food]++)
      for (const [crop,count] of needed.entries()) for(let n=0;n<count;n++) {
        expect(farmPlot(round,0,'plant',crop)).toBe(true)
        for(let day=0;day<crops[crop].days;day++){expect(farmPlot(round,0,'water')).toBe(true);expect(farmDay(round)).toBe(true)}
        expect(farmPlot(round,0,'harvest')).toBe(true)
      }
      round.fed.forEach((_,index)=>expect(feedFarm(round,index)).toBe(true))
      round.orders!.forEach((count,index)=>{for(let n=0;n<count;n++)expect(deliverFarm(round,index)).toBe(true)})
      break
    }
    case 'science-lab':round.missions.forEach(mission=>expect(experiment(round,mission.type,mission.type==='mix'?0:mission.object,mission.type==='mix'?mission.pair:[])).not.toBeNull());break
    case 'forest-rescue':for(let step=0;round.scene!=='home' && step<20;step++){const choices=forestScenes[round.scene].choices,index=choices.findIndex(choice=>!choice.unsafe);expect(forestChoose(round,index)).not.toBeNull()}break
    case 'creative-studio':expect(addArt(round,{kind:'stroke',color:'#38564d',width:8,points:[[30,30],[70,80]]})).toBe(true);expect(saveArtwork(round)).toBe(true);break
    case 'animal-catch':for(let index=0;index<round.goal;index++)expect(catchFood(round,round.animal,true)).toBe('good');break
    case 'daily-life':round.required.forEach(id=>selectLife(round,'pack',id));expect(submitLife(round)?.passed).toBe(true);weatherOutfits[round.weather].items.forEach(id=>selectLife(round,'clothes',id));expect(submitLife(round)?.passed).toBe(true);waitRoad(round);observeRoad(round,0);observeRoad(round,1);expect(crossRoad(round)?.passed).toBe(true);break
    case 'eco-guardian':round.litter.forEach((item,index)=>expect(sortLitter(round,index,ecoLitter[item].bin)?.passed).toBe(true));for(let index=0;index<3;index++)expect(careEco(round,index)).toBe(true);break
  }finishExperience(save)
}
describe('体验游戏的完整流程与存档',()=>{
  for(const id of experienceIds)for(const difficulty of ['starter','explorer','master'] as const)it(`${id} / ${difficulty} 完整流程、完成计数及恢复`,async()=>{
    for(let seed=1;seed<=5;seed++){const save=newExperience(id,difficulty,seeded(seed));expect(restoreExperience(JSON.stringify(save),id)).toEqual(save);solve(save);expect(save.round.finished).toBe(true);expect(save.rounds).toBe(1);expect(finishExperience(save)).toBe(false);expect(save.rounds).toBe(1);expect(restoreExperience(JSON.stringify(save),id)).toEqual(save);expect(await validSave(id,JSON.stringify(save))).toBe(true)}
  })
  it('节奏窗口、错误乐器和重复敲击不会算成功，四种乐器都有说明',()=>{
    const {round}=newExperience('rhythm-band'),beat=60000/round.bpm
    expect(musicTap(round,round.pattern[0],beat*.4)).toBe('outside')
    expect(musicTap(round,(round.pattern[0]+1)%4,beat)).toBe('wrong')
    expect(round.hits[0]).toBe(0);expect(round.mistakes).toBe(1)
    expect(musicTap(round,round.pattern[0],beat)).toBe('hit')
    expect(musicTap(round,round.pattern[0],beat)).toBe('outside');expect(round.hits.reduce((sum,value)=>sum+value,0)).toBe(1)
    expect(instruments).toHaveLength(4)
  })
  it('作物没有浇水不会生长，水不能重复浇，食物会从仓库扣除',()=>{
    const {round}=newExperience('little-farm');farmPlot(round,0,'plant',0);farmDay(round);expect(round.plots[0].growth).toBe(0)
    expect(farmPlot(round,0,'harvest')).toBe(false);expect(farmPlot(round,0,'water')).toBe(true);expect(farmPlot(round,0,'water')).toBe(false)
    farmDay(round);expect(round.plots[0].growth).toBe(1);farmPlot(round,0,'water');farmDay(round);expect(farmPlot(round,0,'harvest')).toBe(true);expect(round.inventory[0]).toBe(1)
    expect(feedFarm(round,0)).toBe(true);expect(round.inventory[0]).toBe(0);expect(feedFarm(round,0)).toBe(false)
  })
  it('浮沉、金属吸引与颜料混合符合实验材料的实际性质',()=>{
    const {round}=newExperience('science-lab')
    expect(experiment(round,'float',0)?.floats).toBe(true);expect(experiment(round,'float',1)?.floats).toBe(false)
    expect(experiment(round,'magnet',3)?.magnetic).toBe(true);expect(experiment(round,'magnet',4)?.magnetic).toBe(false);expect(experiment(round,'magnet',5)?.magnetic).toBe(false)
    expect(experiment(round,'mix',0,[0,1])?.text).toContain('橙色');expect(experiment(round,'mix',0,[1,2])?.text).toContain('绿色');expect(experiment(round,'mix',0,[2,0])?.text).toContain('紫色')
    const total=round.done.length;experiment(round,'mix',0,[0,2]);expect(round.done).toHaveLength(total)
  })
  it('森林可以走不同路线，不合适的动作会说明原因并允许重选',()=>{
    const save=newExperience('forest-rescue','master'),round=save.round
    const choose=(id:string)=>forestChoose(round,forestScenes[round.scene].choices.findIndex(choice=>choice.id===id))
    choose('guide');expect(round.scene).toBe('bird');expect(choose('chase')).toContain('保持距离');expect(round.scene).toBe('bird');expect(round.rescued).toEqual([])
    choose('report');choose('ask');choose('quiet');finishExperience(save);expect(round.scene).toBe('home');expect(round.rescued).toHaveLength(3);expect(round.log.map(item=>item.choice)).toEqual(['guide','chase','report','ask','quiet'])
  })
  it('作品只能在内容更新后再次保存，画廊保留最近十二幅',()=>{
    const save=newExperience('creative-studio'),round=save.round
    expect(saveArtwork(round)).toBe(false)
    for(let index=0;index<14;index++){expect(addArt(round,{kind:'stamp',stamp:'flower',x:100+index*20,y:100,size:72,color:'#dc967e'})).toBe(true);expect(saveArtwork(round)).toBe(true);finishExperience(save);expect(saveArtwork(round)).toBe(false)}
    expect(save.rounds).toBe(1);expect(round.gallery).toHaveLength(12);expect(round.gallery[11].marks).toHaveLength(3)
    expect(setArtBackground(round,'night')).toBe(true);expect(round.finished).toBe(false);expect(addArt(round,{kind:'stroke',points:[[-1,0]],color:'#38564d',width:8})).toBe(false)
  })
  it('接错、漏接和目标食物分别记录，完成后不能重复计分',()=>{
    const save=newExperience('animal-catch'),round=save.round
    expect(catchFood(round,round.animal,false)).toBe('miss');expect(round.missed).toBe(1);expect(catchFood(round,(round.animal+1)%3,true)).toBe('wrong');expect(round.mistakes).toBe(1)
    solve(save);expect(catchFood(round,round.animal,true)).toBeNull();expect(round.caught).toBe(round.goal)
  })
  it('过街必须等行人绿灯并重新观察两侧，书包和衣物可以纠错',()=>{
    const save=newExperience('daily-life'),round=save.round;selectLife(round,'pack','toy');expect(submitLife(round)?.passed).toBe(false);selectLife(round,'pack','toy');round.required.forEach(id=>selectLife(round,'pack',id));submitLife(round)
    weatherOutfits[round.weather].items.forEach(id=>selectLife(round,'clothes',id));submitLife(round);observeRoad(round,0);observeRoad(round,1);expect(crossRoad(round)?.passed).toBe(false)
    waitRoad(round);expect(round.looked).toEqual([]);observeRoad(round,0);expect(crossRoad(round)?.passed).toBe(false);observeRoad(round,1);expect(crossRoad(round)?.passed).toBe(true)
  })
  it('分类错误不会移除垃圾，清理完成后才允许帮助动物',()=>{
    const {round}=newExperience('eco-guardian');expect(careEco(round,0)).toBe(false);const bin=ecoLitter[round.litter[0]].bin
    expect(sortLitter(round,0,(bin+1)%4)?.passed).toBe(false);expect(round.cleaned).toHaveLength(0);expect(sortLitter(round,0,bin)?.passed).toBe(true);expect(sortLitter(round,0,bin)).toBeNull()
  })
  it('拒绝损坏存档和非法完成状态，八款游戏都只有本机存档',()=>{
    for(const id of experienceIds){const save=newExperience(id);save.round.finished=true;expect(restoreExperience(JSON.stringify(save),id)).toBeNull();expect(restoreExperience('{}',id)).toBeNull();expect(restoreExperience('x'.repeat(800*1024),id)).toBeNull()}
    const art=newExperience('creative-studio');art.round.marks=[{kind:'stamp',color:'javascript:bad',size:72,x:0,y:0,stamp:'flower'}];expect(restoreExperience(JSON.stringify(art),'creative-studio')).toBeNull()
    expect(games).toHaveLength(32);expect(cloudGames).toHaveLength(10);expect(experienceIds.every(id=>games.some(game=>game.id===id && game.localOnly))).toBe(true)
  })
})
