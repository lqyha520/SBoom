import { describe, expect, it } from 'vitest'
import { balanceCombination, brainSolved, newBrain, newBrainRound, restoreBrain, type BalanceRound } from '../games/brain-games'
import { seededRandom } from '../games/challenge-journey'
import { newFraction, newFlight, restoreFraction } from '../games/fraction-pizza'
import { newMemory, restoreMemory } from '../games/memory-match'
import { linePossibilities, pictureLines, reasoningHint, sudokuCandidates } from '../games/puzzle-reasoning'
import { newPuzzle, newPuzzleRound, playPuzzle, restorePuzzle, sudokuSolutions } from '../games/puzzle-games'
import { movePoemTile, newPoem, poemHint, selectPoemTile } from '../games/poem-order'
import { checkSpell, moveSpellTile, newSpell, restoreSpell, selectSpellTile, spellHint } from '../games/word-spell'
import { crossRoad, observeRoad, waitTraffic, weatherOutfits } from '../games/daily-life'
import { newLife } from '../games/daily-life'
import { addArt, artColors, eraseArt, saveArtwork } from '../games/creative-studio'
import { finishExperience, newExperience, restoreExperience } from '../games/experience-games'
import { musicTap } from '../games/music-studio'
import { newMarket, restoreMarket } from '../games/word-market'
import { farmBatch, farmDay, farmNeeds, farmPlot } from '../games/little-farm'
import { catchAnimals, newCatch } from '../games/animal-catch'
import { ecoLitter, newEco } from '../games/eco-guardian'

describe('其他游戏的玩法与恢复',()=>{
  it('农场计划预留动物食物，播种、库存和交付都会减少需求，批量浇水只作用于未成熟地',()=>{
    const save=newExperience('little-farm');const round=save.round;round.orders=Array(6).fill(0);round.delivered=Array(6).fill(0)
    expect(farmNeeds(round).slice(0,2)).toEqual([1,1]);farmPlot(round,0,'plant',0);expect(farmNeeds(round)[0]).toBe(0)
    expect(farmBatch(round,'water')).toBe(1);expect(farmBatch(round,'water')).toBe(0);farmDay(round);farmBatch(round,'water');farmDay(round)
    expect(farmBatch(round,'water')).toBe(0);expect(farmBatch(round,'harvest')).toBe(1);expect(round.inventory[0]).toBe(1);expect(farmNeeds(round)[0]).toBe(0)
  })
  it('接接乐后续伙伴和目标增加，每一轮环保都会覆盖四类且没有重复物品',()=>{
    for(const difficulty of ['starter','explorer','master'] as const){
      const first=newCatch(difficulty,seededRandom(1),1),later=newCatch(difficulty,seededRandom(1),12)
      expect(later.goal).toBeGreaterThan(first.goal);expect(later.team!.length).toBeGreaterThan(first.team!.length);expect(later.team!.length).toBeLessThanOrEqual(catchAnimals.length)
      const save=newExperience('animal-catch',difficulty);save.round=later;expect(restoreExperience(JSON.stringify(save),'animal-catch')).not.toBeNull()
      for(let seed=0;seed<50;seed++){const eco=newEco(difficulty,seededRandom(seed),seed+1);expect(new Set(eco.litter.map(index=>ecoLitter[index].bin)).size).toBe(4);expect(new Set(eco.litter).size).toBe(eco.litter.length)}
    }
  })
  it('分数四种玩法每轮都有，连续关卡与固定随机源始终生成合法存档',()=>{
    for(const difficulty of ['starter','explorer','master'] as const) for(let seed=0;seed<50;seed++){
      const save=newFraction(difficulty,seededRandom(seed));save.flight=newFlight(difficulty,seededRandom(seed),[],1+seed%12)
      expect(restoreFraction(JSON.stringify(save))).toEqual(save)
      if(difficulty!=='starter')expect(new Set(save.flight.questions.map(q=>q.mode)).size).toBe(4)
    }
    expect(restoreFraction(JSON.stringify(newFraction('master',()=>0)))).not.toBeNull()
    const invalid=newFraction('master');const q=invalid.flight.questions.find(q=>q.mode==='compare')!;q.other!.shaded=q.other!.total
    expect(restoreFraction(JSON.stringify(invalid))).toBeNull()
  })
  it('翻牌有限题池不依赖随机碰运气，全部难度可用固定随机源恢复',()=>{
    for(const difficulty of ['cozy','focus','master'] as const){const save=newMemory(difficulty,()=>0);expect(restoreMemory(JSON.stringify(save))).toEqual(save)}
  })
  it('天平限定数量仍有解，超量的等重组合需要再调整',()=>{
    for(const difficulty of ['starter','explorer','master'] as const)for(let seed=0;seed<80;seed++){
      const save=newBrain('balance-scale',difficulty,seededRandom(seed));const round=newBrainRound('balance-scale',difficulty,seededRandom(seed),4) as BalanceRound;round.stage=4;save.round=round
      expect(restoreBrain(JSON.stringify(save),'balance-scale')).not.toBeNull()
      const solution=balanceCombination(round)!;expect(solution.reduce((a,b)=>a+b,0)).toBeLessThanOrEqual(round.maxPieces!)
      round.counts=solution;expect(brainSolved(round)).toBe(true)
    }
    const round={...newBrain('balance-scale').round,kind:'balance-scale',weights:[1,2,5],supply:[3,3,3],counts:[1,2,0],target:5,maxPieces:1} as BalanceRound
    expect(brainSolved(round)).toBe(false);round.counts=[0,0,1];expect(brainSolved(round)).toBe(true)
  })
  it('找规律中间缺项、更多不同处和横轴镜面都能恢复',()=>{
    for(const id of ['pattern-train','spot-difference','mirror-draw'] as const)for(let seed=0;seed<30;seed++){
      const save=newBrain(id,'master',seededRandom(seed));save.round=newBrainRound(id,'master',seededRandom(seed),8);save.round.stage=8
      expect(restoreBrain(JSON.stringify(save),id)).not.toBeNull()
    }
  })
  it('数独候选不提前透露答案，后续减少已知格仍保留唯一解',()=>{
    expect(sudokuCandidates(Array(16).fill(0),0)).toEqual([1,2,3,4])
    for(const difficulty of ['starter','explorer','master'] as const) for(let seed=0;seed<20;seed++){
      const round=newPuzzleRound('shape-sudoku',difficulty,seededRandom(seed),10)
      expect(sudokuSolutions(round.initial)).toBe(1)
      const save=newPuzzle('shape-sudoku',difficulty);save.round=round;round.stage=10
      expect(restorePuzzle(JSON.stringify(save),'shape-sudoku')).not.toBeNull()
      expect(reasoningHint(round)).not.toBeNull()
    }
  })
  it('像素线索通过可能排列推理，错误的标空会定位冲突行',()=>{
    expect(linePossibilities([3],[0,0,0,0,0])).toHaveLength(3)
    expect(linePossibilities([3],[0,0,2,0,0])).toHaveLength(0)
    const save=newPuzzle('picture-logic');save.round.solution=Array(25).fill(0);for(let index=0;index<5;index++)save.round.solution[index]=1
    playPuzzle(save,0,2)
    expect(pictureLines(save.round)[0].state).toBe('conflict')
    expect(reasoningHint(save.round)?.text).toContain('无法满足')
  })
  it('诗句和字母可以交换局部顺序，提示会接着正确前缀往下走',()=>{
    const poem=newPoem();const q=poem.round.questions[0]
    selectPoemTile(poem,q.answer[0]);expect(poemHint(poem)).toBe(q.tiles.find(tile=>tile.id===q.answer[1])!.text)
    selectPoemTile(poem,q.answer[2]);selectPoemTile(poem,q.answer[1]);expect(movePoemTile(poem,2,-1)).toBe(true);expect(poem.round.selected).toEqual(q.answer.slice(0,3))
    const spell=newSpell();const s=spell.round.questions[0]
    selectSpellTile(spell,s.answer[0]);expect(spellHint(spell)).toBe(s.word[1])
    selectSpellTile(spell,s.answer[2]);selectSpellTile(spell,s.answer[1]);expect(moveSpellTile(spell,2,-1)).toBe(true)
    for(const id of s.answer.slice(3))selectSpellTile(spell,id)
    expect(checkSpell(spell)).toBe(true);expect(restoreSpell(JSON.stringify(spell))).toEqual(spell)
  })
  it('同字母卡片交换后仍能拼写并恢复，不按卡片编号误判',()=>{
    const spell=newSpell('master',seededRandom(9));const q=spell.round.questions.find(q=>new Set(q.word).size<q.word.length)!
    if(!q)throw new Error('测试需重复字母')
    spell.round.questions[0]=q
    const groups=new Map<string,string[]>();q.tiles.forEach(tile=>groups.set(tile.letter,[...(groups.get(tile.letter)||[]),tile.id]))
    for(const letter of q.word)selectSpellTile(spell,groups.get(letter)!.pop()!)
    expect(checkSpell(spell)).toBe(true);expect(restoreSpell(JSON.stringify(spell))).not.toBeNull()
  })
  it('单词集市进阶同时训练两个翻译方向，旧存档可继续',()=>{
    const save=newMarket('explorer');expect(save.round.questions.filter(q=>q.direction==='meaning')).toHaveLength(4)
    expect(restoreMarket(JSON.stringify(save))).toEqual(save)
    save.round.questions.forEach(q=>delete q.direction);expect(restoreMarket(JSON.stringify(save))).not.toBeNull()
  })
  it('绿灯时车辆仍在移动，必须等待停稳并重新观察',()=>{
    const round=newLife('master',seededRandom(1),3);round.phase=2;round.light='green';round.packed=[...round.required];round.clothes=[...weatherOutfits[round.weather].items]
    observeRoad(round,0);observeRoad(round,1);expect(crossRoad(round)?.passed).toBe(false)
    expect(waitTraffic(round)).toBe(true);expect(round.looked).toEqual([])
    observeRoad(round,0);observeRoad(round,1);expect(crossRoad(round)?.passed).toBe(true)
  })
  it('节奏同一拍多次敲错只扣一次，可在窗口内纠正；长编曲能恢复',()=>{
    const save=newExperience('rhythm-band');const round=save.round,beat=60000/round.bpm,wrong=(round.pattern[0]+1)%4
    expect(musicTap(round,wrong,beat)).toBe('wrong');expect(musicTap(round,wrong,beat)).toBe('outside');expect(round.mistakes).toBe(1)
    expect(musicTap(round,round.pattern[0],beat)).toBe('hit')
    round.grid=round.grid.map(row=>[...row,...Array(8).fill(0)]);expect(restoreExperience(JSON.stringify(save),'rhythm-band')).not.toBeNull()
  })
  it('橡皮擦删除最上层笔画，画作改动后重新保存不会重复累计通关',()=>{
    const save=newExperience('creative-studio');const round=save.round
    addArt(round,{kind:'stroke',color:artColors[0],width:8,points:[[10,10],[200,10]]})
    addArt(round,{kind:'stamp',color:artColors[1],stamp:'flower',size:48,x:100,y:10})
    expect(eraseArt(round,100,10)).toBe(true);expect(round.marks[0].kind).toBe('stroke')
    saveArtwork(round);finishExperience(save);expect(save.rounds).toBe(1)
    addArt(round,{kind:'stamp',color:artColors[1],stamp:'flower',size:48,x:200,y:50});saveArtwork(round);finishExperience(save)
    expect(save.rounds).toBe(1);expect(restoreExperience(JSON.stringify(save),'creative-studio')).not.toBeNull()
    expect(eraseArt(round,100,10)).toBe(true);expect(round.marks).toHaveLength(1)
  })
})
