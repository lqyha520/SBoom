import { describe,expect,it } from 'vitest'
import { contentDeck,freshJourney,seededRandom } from '../games/challenge-journey'
import { brainIds,newBrain,nextBrain,newBrainRound,restoreBrain,strokeSolution,drawStroke,moveBrainSokoban,visitSokoban } from '../games/brain-games'
import { sokobanCampaign,sokobanSolution,sokobanSolved,newSokoban,moveSokoban,sokobanDeadlocks } from '../games/sokoban'
import { tangramLayouts,tangramConflicts,tangramSolved,newTangram } from '../games/tangram'
import { newSort,pourSort,sortSolved } from '../games/color-sort'
import { newPuzzle,nextPuzzle,newPuzzleRound,puzzleSolved,puzzleIds,restorePuzzle } from '../games/puzzle-games'
import { newShop,nextDay,currentOrder,submitPacking,submitAmount,nextCustomer,basketTotal,payment,products,restoreShop } from '../games/little-shop'
import { newMemoryRound,newMemory,restartMemory,restoreMemory } from '../games/memory-match'
import { newFraction,restartFraction,restoreFraction } from '../games/fraction-pizza'
import { newRocket,restartRocket } from '../games/rocket-math'
import { newClock,restartClock,submitClockDial,turnClock,restoreClock,advanceClock } from '../games/clock-town'
import { newExperience,restoreExperience } from '../games/experience-games'
import { poemPools } from '../games/poem-order'
import { idiomPools } from '../games/idiom-fill'
import { englishWords } from '../games/english-words'

const tiers = ['starter','explorer','master'] as const
describe('关卡内容与连续挑战质量',()=>{
  it('72 张推箱子地图均可解、最少推动正确，结构和镜像不重复且难度递进',()=>{
    const signatures = new Set<string>()
    for(const [index,level] of sokobanCampaign.entries()) {
      const round=newSokoban(tiers[Math.floor(index/24)],seededRandom(1),index%24+1)
      const path=sokobanSolution(round)
      expect(path,level.name).not.toBeNull()
      for(const direction of path!)expect(moveSokoban(round,direction),level.name).toBe(true)
      expect(sokobanSolved(round),level.name).toBe(true)
      expect(round.pushes,level.name).toBe(level.pushes)
      const variants:string[]=[]
      let rows: string[]=[...level.rows]
      for(let rotate=0;rotate<4;rotate++) {
        variants.push(rows.join('\n').replace('@',' ').replace('+','.'),rows.map(row=>row.split('').reverse().join('')).join('\n').replace('@',' ').replace('+','.'))
        rows=Array.from({length:rows[0].length},(_,col)=>rows.map(row=>row[col]).reverse().join(''))
      }
      const signature=variants.sort()[0]
      expect(signatures.has(signature),level.name).toBe(false);signatures.add(signature)
      expect(sokobanDeadlocks(newSokoban(tiers[Math.floor(index/24)],seededRandom(1),index%24+1))).toEqual([])
    }
    expect(Math.min(...sokobanCampaign.slice(0,24).map(level=>level.pushes))).toBe(6)
    expect(Math.min(...sokobanCampaign.slice(24,48).map(level=>level.pushes))).toBeGreaterThanOrEqual(12)
    expect(sokobanCampaign[71].pushes).toBeGreaterThan(sokobanCampaign[48].pushes)
  },60_000)
  it('七巧板的全部 27 个轮廓有合法、不重叠的参考摆法',()=>{
    expect(tangramLayouts).toHaveLength(27)
    for(const [index,layout] of tangramLayouts.entries()) {
      const round={...newTangram('starter',seededRandom(1)),layout:index,pieces:layout.solution}
      expect(tangramConflicts(round),layout.name).toEqual([])
      expect(tangramSolved(round),layout.name).toBe(true)
    }
  })
  it('水管、一笔画和颜色排序跨种子合法可解，后续布局有变化',()=>{
    for(const tier of tiers){const pipeRoutes=new Set<string>(),strokeRoutes=new Set<string>()
      for(let seed=1;seed<=16;seed++){
        const pipe=newPuzzleRound('pipe-connect',tier,seededRandom(seed),seed)
        expect(new Set(pipe.route).size).toBe(pipe.size**2)
        expect(puzzleSolved({...pipe,cells:pipe.solution})).toBe(true)
        pipeRoutes.add(pipe.route.join(','))
        const brain=newBrain('one-stroke',tier,seededRandom(seed))
        brain.round=newBrainRound('one-stroke',tier,seededRandom(seed),seed)
        if(brain.round.kind!=='one-stroke')throw new Error()
        const path=strokeSolution(brain.round);expect(path).not.toBeNull()
        strokeRoutes.add(JSON.stringify(brain.round.edges))
        for(const node of path!)expect(drawStroke(brain,node)).toBe(true)
        expect(brain.round.finished).toBe(true)
        const sort=newSort(tier,seededRandom(seed),seed),route=sort.route.map(move=>[...move] as [number,number])
        expect(sortSolved(sort)).toBe(false)
        for(const [from,to] of route)expect(pourSort(sort,from,to)).toBe(true)
        expect(sortSolved(sort)).toBe(true)
      }
      expect(pipeRoutes.size).toBeGreaterThan(8);expect(strokeRoutes.size).toBeGreaterThan(8)
    }
    expect(newSort('master',seededRandom(1),9).colors).toBe(6)
  })
  it('重试保留同一内容，通关下一关变化，最终仓库不会自动循环',()=>{
    for(const id of brainIds){const save=newBrain(id,'starter',seededRandom(8)),original=JSON.stringify(save.round);nextBrain(save,save.difficulty,true);expect(JSON.stringify(save.round)).toBe(original);expect(restoreBrain(JSON.stringify(save),id)).not.toBeNull()}
    for(const id of puzzleIds){const save=newPuzzle(id,'master',seededRandom(8)),original=JSON.stringify(save.round);nextPuzzle(save,save.difficulty,true);expect(JSON.stringify(save.round)).toBe(original);expect(restorePuzzle(JSON.stringify(save),id)).not.toBeNull()}
    const save=newBrain('sokoban','starter',seededRandom(1)),first=save.round
    if(first.kind!=='sokoban')throw new Error()
    for(const move of sokobanSolution(first)!)moveBrainSokoban(save,move)
    nextBrain(save);expect(save.round.stage).toBe(2)
    if(save.round.kind!=='sokoban')throw new Error()
    expect(save.round.level).not.toBe(first.level)
    save.difficulty='master';save.journey!.completed.master=23;expect(visitSokoban(save,24)).toBe(true)
    if(save.round.kind!=='sokoban')throw new Error()
    for(const move of sokobanSolution(save.round)!)moveBrainSokoban(save,move)
    const last=JSON.stringify(save.round);nextBrain(save);expect(JSON.stringify(save.round)).toBe(last)
    expect(visitSokoban(save,1)).toBe(true);nextBrain(save);expect(save.round.stage).toBe(2)
    save.journey!.completed.starter=24;nextBrain(save,'starter');expect(save.round.stage).toBe(1);expect(save.difficulty).toBe('starter')
  },30_000)
  it('店长连续 30 天订单轮换，库存始终能交付四单，旧存档兼容',()=>{
    const save=newShop('change');const days=new Set<string>()
    expect(restoreShop(JSON.stringify(save))).toEqual(save)
    for(let day=1;day<=30;day++){
      const orders:string[]=[]
      for(let customer=0;customer<4;customer++){
        const order=currentOrder(save);orders.push(JSON.stringify(order))
        for(const product of products)expect(save.stock[product.id]).toBeGreaterThanOrEqual(order[product.id])
        save.bag={...order};expect(submitPacking(save)).toBe(true)
        expect(submitAmount(save,basketTotal(order))).toBe(true)
        expect(submitAmount(save,payment(save)-basketTotal(order))).toBe(true)
        expect(restoreShop(JSON.stringify(save))).not.toBeNull();nextCustomer(save)
      }
      expect(new Set(orders).size).toBe(4);days.add(orders.join('|'));nextDay(save)
    }
    expect(days.size).toBe(30)
  })
  it('口算和分数优先新内容，入门有限池先用完再轮换',()=>{
    const rocket=newRocket('pilot',seededRandom(1)),previous=rocket.flight.questions.map(q=>q.expression)
    restartRocket(rocket,seededRandom(1));expect(rocket.flight.questions.some(q=>previous.includes(q.expression))).toBe(false)
    const fraction=newFraction('starter',seededRandom(1)),before=fraction.flight.questions.map(q=>`${q.shaded}/${q.total}`)
    restartFraction(fraction,seededRandom(1));expect(fraction.flight.questions.filter(q=>before.includes(`${q.shaded}/${q.total}`))).toHaveLength(6)
    fraction.flights=8;restartFraction(fraction,seededRandom(1));expect(Math.max(...fraction.flight.questions.map(q=>q.total))).toBeGreaterThan(5);expect(restoreFraction(JSON.stringify(fraction))).not.toBeNull()
    expect(contentDeck([1,2,3,4],2,String,['1','2','3','4'],seededRandom(1))).toEqual([1,2])
  })
  it('记忆卡逐步增加，拨钟跨整点、错误可纠正、草稿能恢复',()=>{
    expect(newMemoryRound('cozy',seededRandom(1),7).cards).toHaveLength(16)
    const memory=newMemory('master',seededRandom(1));memory.rounds=7;restartMemory(memory,seededRandom(1));expect(memory.round.cards).toHaveLength(24);expect(restoreMemory(JSON.stringify(memory))).not.toBeNull()
    const clock=newClock('master',seededRandom(1));clock.mode='set';clock.round.dial=[12,55]
    expect(turnClock(clock,'minute',1)).toBe(true);expect(clock.round.dial).toEqual([1,0])
    const q=clock.round.questions[0];clock.round.dial=[q.hour===12?1:q.hour+1,q.minute];expect(submitClockDial(clock)).toBe(false);expect(clock.round.answered).toBeNull();expect(restoreClock(JSON.stringify(clock))).not.toBeNull()
    clock.round.dial=[q.hour,q.minute];expect(submitClockDial(clock)).toBe(true);advanceClock(clock);expect(clock.round.dial).toBeUndefined()
    const times=clock.round.questions.map(q=>q.answer);restartClock(clock,seededRandom(1));expect(clock.round.questions.some(q=>times.includes(q.answer))).toBe(false)
  })
  it('新增语言内容的 ID、字数与选项合法，体验游戏旧进度保留',()=>{
    for(const [tier,pool] of Object.entries(poemPools)){expect(new Set(pool.map(p=>p.id)).size).toBe(pool.length);for(const poem of pool){expect(poem.lines).toHaveLength(4);for(const [index,line] of poem.lines.entries())expect([...line.replace(/[，。！？]/g,'')]).toHaveLength(poem.id==='yonge' && index===0?3:tier==='starter'?5:7)}}
    for(const pool of Object.values(idiomPools)){expect(new Set(pool.map(p=>p.id)).size).toBe(pool.length);for(const idiom of pool){expect([...idiom.text]).toHaveLength(4);expect(idiom.text[idiom.blank]).toBe(idiom.answer);expect(new Set(idiom.options).size).toBe(4);expect(idiom.options).toContain(idiom.answer)}}
    for(const [tier,pool] of Object.entries(englishWords)){expect(new Set(pool.map(w=>w.word)).size).toBe(pool.length);for(const word of pool){expect(word.word).toMatch(/^[a-z]+$/);expect(word.word.length).toBeGreaterThanOrEqual(tier==='starter'?3:tier==='explorer'?5:8);expect(word.word.length).toBeLessThanOrEqual(tier==='starter'?4:tier==='explorer'?6:10)}}
    const old=newExperience('eco-guardian');delete old.journey;delete old.round.stage;old.rounds=3
    expect(restoreExperience(JSON.stringify(old),'eco-guardian')?.journey?.completed.starter).toBe(3)
    const journey=freshJourney();journey.completed.starter=4
    const next=newExperience('science-lab','starter',seededRandom(1),journey);expect(next.round.stage).toBe(5)
  })
})
