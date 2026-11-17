import { describe,expect,it } from 'vitest'
import { advancePattern,answerPattern,balanceCombination,brainHint,brainIds,brainSolved,drawStroke,findDifference,moveBrainSokoban,moveBrainSort,moveBrainTangram,newBrain,paintMirror,restoreBrain,strokeSolution,weighBrain,type BrainSave } from '../games/brain-games'
import { puzzleDifficulties } from '../games/puzzle-games'
import { tangramAtoms,tangramLayouts,tangramPolygon } from '../games/tangram'
import { sokobanMap,sokobanSolution } from '../games/sokoban'

function seeded(seed: number) { return () => { seed = (Math.imul(seed,1664525)+1013904223)>>>0; return seed/4294967296 } }
const sokoPaths = new Map<number,number[]>()
function solve(save: BrainSave) {
  const round = save.round
  switch (round.kind) {
    case 'tangram': tangramLayouts[round.layout].solution.forEach((placement,index)=>moveBrainTangram(save,index,placement)); break
    case 'sokoban': {
      const path = sokoPaths.get(round.level) || sokobanSolution(round)
      expect(path).not.toBeNull(); sokoPaths.set(round.level,path!)
      path!.forEach(direction=>expect(moveBrainSokoban(save,direction)).toBe(true)); break
    }
    case 'pattern-train': for (const question of round.questions) { expect(answerPattern(save,question.answer)).toBe(true); expect(advancePattern(save)).toBe(true) }; break
    case 'one-stroke': { const path = strokeSolution(round); expect(path).not.toBeNull(); path!.forEach(node=>expect(drawStroke(save,node)).toBe(true)); break }
    case 'balance-scale': { const counts = balanceCombination(round); expect(counts).not.toBeNull(); counts!.forEach((count,index)=>{ for (let n=0;n<count;n++) expect(weighBrain(save,index,1)).toBe(true) }); break }
    case 'color-sort': for (const [from,to] of [...round.route]) { if (!round.finished) expect(moveBrainSort(save,from,to)).toBe(true) }; break
    case 'mirror-draw': round.solution.forEach((color,index)=>{ if (!round.fixed.includes(index) && round.cells[index] !== color) expect(paintMirror(save,index,color)).toBe(true) }); break
    case 'spot-difference': round.differences.forEach(index=>expect(findDifference(save,index)).toBe('found')); break
  }
}

describe('新增八款益智游戏',()=>{
  for (const id of brainIds) for (const {id:difficulty} of puzzleDifficulties) {
    it(`${id} / ${difficulty}：有解、真实操作通关与存档恢复`,()=>{
      for(let seed=1;seed<=8;seed++) {
        const save = newBrain(id,difficulty,seeded(seed))
        expect(brainSolved(save.round)).toBe(false)
        expect(restoreBrain(JSON.stringify(save),id)).toEqual(save)
        solve(save)
        expect(save.round.finished).toBe(true); expect(save.rounds).toBe(1)
        expect(brainSolved(save.round)).toBe(true)
        expect(restoreBrain(JSON.stringify(save),id)).toEqual(save)
        expect(brainHint(save)).toBeNull()
      }
    })
  }
  it('七巧板三种轮廓都是七块无重叠覆盖，允许交换两块大三角',()=>{
    for(const [layout,value] of tangramLayouts.entries()) {
      const areas = value.solution.map((piece,index)=>tangramAtoms(tangramPolygon(index,piece)))
      expect(areas.map(area=>area.length).sort((a,b)=>a-b)).toEqual([4,4,8,8,8,16,16])
      expect(new Set(areas.flat()).size).toBe(64)
      const save = newBrain('tangram'); if(save.round.kind !== 'tangram') throw new Error()
      save.round.layout=layout
      const solution = [...value.solution]; [solution[0],solution[1]]=[solution[1],solution[0]]
      solution.forEach((piece,index)=>expect(moveBrainTangram(save,index,piece)).toBe(true))
      expect(save.round.finished).toBe(true)
    }
  })
  it('推箱子九张地图均有解，墙壁不会被穿过',()=>{
    for(let level=0;level<9;level++) {
      const save = newBrain('sokoban',puzzleDifficulties[Math.floor(level/3)].id)
      if(save.round.kind !== 'sokoban') throw new Error()
      const map=sokobanMap(level); Object.assign(save.round,{level,player:map.player,boxes:map.boxes})
      expect(sokobanSolution(save.round)).not.toBeNull()
    }
    const save = newBrain('sokoban'); if(save.round.kind !== 'sokoban') throw new Error()
    save.round.player=sokobanMap(save.round.level).width+1
    expect(moveBrainSokoban(save,0)).toBe(false)
  })
  it('规律题答错后显示结果，不能重复计分；换下一题后可继续',()=>{
    const save=newBrain('pattern-train'), round=save.round
    if(round.kind !== 'pattern-train') throw new Error()
    const question=round.questions[0], wrong=question.options.find(value=>value !== question.answer)!
    expect(answerPattern(save,wrong)).toBe(false)
    expect(answerPattern(save,question.answer)).toBeNull()
    expect(round.mistakes).toBe(1); expect(advancePattern(save)).toBe(true)
    expect(restoreBrain(JSON.stringify(save),'pattern-train')).toEqual(save)
  })
  it('一笔画不能重复走线，天平不能使用超出库存的砝码',()=>{
    const stroke=newBrain('one-stroke'), round=stroke.round
    if(round.kind !== 'one-stroke') throw new Error()
    const path=strokeSolution(round)!
    expect(drawStroke(stroke,path[0])).toBe(true); expect(drawStroke(stroke,path[1])).toBe(true)
    expect(drawStroke(stroke,path[0])).toBe(false)
    const scale=newBrain('balance-scale'); expect(weighBrain(scale,0,-1)).toBe(false)
    expect(weighBrain(scale,20,1)).toBe(false)
  })
  it('颜色排序限制接收颜色，镜面已知格不能修改，找到的不同不能重复计数',()=>{
    const sort=newBrain('color-sort'); expect(moveBrainSort(sort,0,0)).toBe(false)
    const mirror=newBrain('mirror-draw'); if(mirror.round.kind !== 'mirror-draw') throw new Error()
    expect(paintMirror(mirror,mirror.round.fixed[0],2)).toBe(false)
    const difference=newBrain('spot-difference'); if(difference.round.kind !== 'spot-difference') throw new Error()
    const index=difference.round.differences[0]
    expect(findDifference(difference,index)).toBe('found'); expect(findDifference(difference,index)).toBeNull()
    const diffRound=difference.round
    const same=diffRound.left.findIndex((_,index)=>!diffRound.differences.includes(index))
    expect(findDifference(difference,same)).toBe('same')
    expect(difference.round.found).toHaveLength(1)
  })
  it('提示不自动改棋盘，损坏、串用及伪造完成的存档被拒绝',()=>{
    for(const id of brainIds) {
      const save=newBrain(id), before=JSON.stringify(save.round)
      expect(brainHint(save)).not.toBeNull()
      const expected=JSON.parse(before); expected.hints++
      expect(save.round).toEqual(expected)
      const broken=JSON.parse(JSON.stringify(save)) as BrainSave; broken.round.finished=true
      expect(restoreBrain(JSON.stringify(broken),id)).toBeNull()
      expect(restoreBrain(JSON.stringify(save),brainIds.find(other=>other !== id)!)).toBeNull()
      expect(restoreBrain('{',id)).toBeNull()
    }
  })
})
