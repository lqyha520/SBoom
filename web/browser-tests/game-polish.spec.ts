import { expect, test, type Page } from '@playwright/test'
import { gameKey, type GameId } from '../src/games/catalog'
import { newFraction, type FractionSave } from '../src/games/fraction-pizza'
import { newMemory, type MemorySave } from '../src/games/memory-match'
import { newPuzzle } from '../src/games/puzzle-games'
import { newBrain, newBrainRound, type BrainSave } from '../src/games/brain-games'
import { newExperience, type ExperienceSave } from '../src/games/experience-games'
import { newLife, weatherOutfits } from '../src/games/daily-life'
import { newPoem } from '../src/games/poem-order'
import { newSpell } from '../src/games/word-spell'
import { newMarket, type MarketSave } from '../src/games/word-market'
test.use({reducedMotion:'reduce'})

const read=async<T>(page:Page,id:GameId)=>{await expect(page.locator(`a[aria-current="page"][href$="/games/${id}"]`)).toHaveCount(1);await expect.poll(()=>page.evaluate(key=>!!localStorage.getItem(key),gameKey(id))).toBe(true);return page.evaluate(key=>JSON.parse(localStorage.getItem(key)!) as T,gameKey(id))}
const pageErrors=new WeakMap<Page,string[]>()
test.beforeEach(async({page})=>{const errors:string[]=[];pageErrors.set(page,errors);page.on('pageerror',error=>errors.push(error.message))})
test.afterEach(async({page})=>{expect(pageErrors.get(page)).toEqual([])})
async function load(page:Page,id:GameId,save:unknown){await page.goto('/#/games/'+id);await expect(page.locator(`a[aria-current="page"][href$="/games/${id}"]`)).toHaveCount(1);await page.evaluate(({key,save})=>localStorage.setItem(key,save),{key:gameKey(id),save:JSON.stringify(save)});await page.reload();await expect(page.locator(`a[aria-current="page"][href$="/games/${id}"]`)).toHaveCount(1)}
async function mobile(page:Page,path:string){await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path,fullPage:true})}

test('分数比较真正显示同大小披萨，比较可作答，刷新保留进度',async({page},info)=>{
  const save=newFraction('master'),compare=save.flight.questions.findIndex(q=>q.mode==='compare');save.flight.index=compare;save.flight.correct=compare
  await load(page,'fraction-pizza',save);await expect(page.locator('.compare-pizzas figure')).toHaveCount(2)
  const q=save.flight.questions[compare];await page.locator('[data-fraction]').filter({hasText:q.answer}).click();await expect(page.getByRole('status',{name:'答题反馈'})).toContainText('共同分母')
  await page.reload();expect((await read<FractionSave>(page,'fraction-pizza')).flight.answered).toBe(q.answer)
  await mobile(page,info.outputPath('fraction-compare-mobile.png'))
})
test('翻牌在两张展开时刷新不会卡住，慢慢看支持自己收牌',async({page},info)=>{
  await page.goto('/#/games/memory-match');const save=await read<MemorySave>(page,'memory-match'),cards=save.round.cards
  const first=cards[0],second=cards.find(card=>card.pairId!==first.pairId)!
  await page.getByRole('checkbox',{name:'翻牌慢慢看'}).check();await page.locator(`[data-card-id="${first.id}"]`).click();await page.locator(`[data-card-id="${second.id}"]`).click()
  await expect(page.getByRole('button',{name:'记住了，收起卡片'})).toBeVisible();await page.reload()
  await expect.poll(async()=>(await read<MemorySave>(page,'memory-match')).round.flipped.length).toBe(0)
  await page.getByRole('checkbox',{name:'翻牌慢慢看'}).check();await page.locator(`[data-card-id="${first.id}"]`).click();await page.locator(`[data-card-id="${second.id}"]`).click();await page.getByRole('button',{name:'记住了，收起卡片'}).click()
  expect((await read<MemorySave>(page,'memory-match')).round.flipped).toEqual([])
  await mobile(page,info.outputPath('memory-control-mobile.png'))
})
test('数独显示候选，像素棋盘标出冲突行，华容道键盘有效',async({page},info)=>{
  const sudoku=newPuzzle('shape-sudoku');await load(page,'shape-sudoku',sudoku);const blank=sudoku.round.cells.indexOf(0)
  await page.locator(`[data-cell="${blank}"]`).click();await expect(page.getByLabel('当前格候选')).toBeVisible()
  await page.getByRole('button',{name:'给我提示',exact:true}).click();await expect(page.getByRole('status',{name:'游戏提示'})).toBeVisible()
  const pixel=newPuzzle('picture-logic');await load(page,'picture-logic',pixel)
  const row=Math.floor(pixel.round.solution.indexOf(1)/pixel.round.size)
  await page.getByRole('button',{name:'标空',exact:true}).click();for(let offset=0;offset<pixel.round.size;offset++)await page.locator(`[data-cell="${row*pixel.round.size+offset}"]`).click()
  await expect(page.locator('.clue-conflict').first()).toBeVisible();await mobile(page,info.outputPath('pixel-feedback-mobile.png'))
  await page.goto('/#/games/sliding-puzzle');await page.locator('.puzzle-grid').focus();const before=await page.evaluate(()=>localStorage.getItem('lc_game_sliding_puzzle_v1_guest'));await page.keyboard.press('ArrowUp');await page.keyboard.press('ArrowDown');expect(await page.evaluate(()=>localStorage.getItem('lc_game_sliding_puzzle_v1_guest'))).not.toBe(before)
})
test('天平砝码数量要求、中间缺项和镜面符号在手机可见',async({page},info)=>{
  for(const id of ['balance-scale','pattern-train','mirror-draw','spot-difference'] as const){const save=newBrain(id,'master');save.round=newBrainRound(id,'master',Math.random,8);save.round.stage=8;await load(page,id,save);await mobile(page,info.outputPath(id+'-mobile.png'))}
  await page.goto('/#/games/balance-scale');await expect(page.getByText(/挑战要求：最多/)).toBeVisible()
  await page.goto('/#/games/mirror-draw');await expect(page.locator('.mirror-cell').filter({hasText:'●'}).first()).toBeVisible()
})
test('诗句与拼写支持局部换位，集市反向词义不泄露图片答案',async({page},info)=>{
  const poem=newPoem();await load(page,'poem-order',poem);for(const id of [poem.round.questions[0].answer[1],poem.round.questions[0].answer[0]])await page.locator(`[data-tile-id="${id}"]`).click()
  await page.locator('.sequence-adjust summary').click();await page.getByRole('button',{name:'第 2 个诗句前移'}).click();expect((await read<typeof poem>(page,'poem-order')).round.selected).toEqual(poem.round.questions[0].answer.slice(0,2))
  const spell=newSpell();await load(page,'word-spell',spell);for(const id of spell.round.questions[0].answer.slice(0,2))await page.locator(`[data-tile-id="${id}"]`).click()
  await page.locator('.sequence-adjust summary').click();await page.getByRole('button',{name:'第 2 个字母前移'}).click();await mobile(page,info.outputPath('spell-reorder-mobile.png'))
  const market=newMarket('explorer');market.round.index=1;market.round.correct=1;await load(page,'word-market',market);await expect(page.locator('.prompt-emoji')).toHaveCount(0);await expect(page.locator('.prompt-copy strong')).toHaveText(market.round.questions[1].wordId)
  await page.locator(`[data-word="${market.round.questions[1].wordId}"]`).click();expect((await read<MarketSave>(page,'word-market')).round.correct).toBe(2)
})
test('编曲范例可编辑、长编曲可刷新，播放期间不能改节奏',async({page},info)=>{
  await page.goto('/#/games/rhythm-band');await page.getByRole('button',{name:'自由编曲',exact:true}).click();await page.getByRole('button',{name:'16 拍',exact:true}).click();await page.getByRole('button',{name:'三拍摇摆',exact:true}).click()
  await expect(page.locator('[data-sequence]')).toHaveCount(64);const before=(await read<ExperienceSave<'rhythm-band'>>(page,'rhythm-band')).round.grid
  await page.reload();expect((await read<ExperienceSave<'rhythm-band'>>(page,'rhythm-band')).round.grid).toEqual(before)
  await page.getByRole('button',{name:'播放我的节奏',exact:true}).click();await expect(page.locator('[data-sequence="0-0"]')).toBeDisabled();await page.getByRole('button',{name:'停止演奏',exact:true}).click();await mobile(page,info.outputPath('music-16-mobile.png'))
})
test('路口等待车辆并重新观察才能完成；画室可删除一笔并保存',async({page},info)=>{
  const life=newExperience('daily-life','master');life.round=newLife('master',Math.random,3);life.round.stage=3;life.round.phase=2;life.round.packed=[...life.round.required];life.round.clothes=[...weatherOutfits[life.round.weather].items];life.round.light='green'
  await load(page,'daily-life',life);await page.getByRole('button',{name:'观察左侧',exact:true}).click();await page.getByRole('button',{name:'和大人一起过街',exact:true}).click();await expect(page.getByRole('status',{name:'完成反馈'})).toHaveCount(0)
  await page.getByRole('button',{name:'等车辆停稳',exact:true}).click();await page.getByRole('button',{name:'观察左侧',exact:true}).click();await page.getByRole('button',{name:'观察右侧',exact:true}).click();await page.getByRole('button',{name:'和大人一起过街',exact:true}).click();await expect(page.getByRole('status',{name:'完成反馈'})).toBeVisible();await mobile(page,info.outputPath('road-mobile.png'))
  await page.goto('/#/games/creative-studio');await page.getByRole('button',{name:'选择花朵印章',exact:true}).click();await page.getByRole('img',{name:'创意画布',exact:true}).click({position:{x:60,y:60}});await page.getByRole('button',{name:'橡皮擦',exact:true}).click();await page.getByRole('img',{name:'创意画布',exact:true}).click({position:{x:60,y:60}});await expect.poll(async()=>(await read<ExperienceSave<'creative-studio'>>(page,'creative-studio')).round.marks.length).toBe(0)
})
test('农场播种计划包含动物口粮，批量工具有效，实验有预测和比较',async({page},info)=>{
  await page.goto('/#/games/little-farm');await expect(page.getByLabel('还需播种计划')).toBeVisible();await page.locator('[data-plot="0"]').click();await page.locator('[data-plot="1"]').click();await page.getByRole('button',{name:'给未浇水作物浇水'}).click();expect((await read<ExperienceSave<'little-farm'>>(page,'little-farm')).round.plots.filter(plot=>plot.watered).length).toBe(2)
  await mobile(page,info.outputPath('farm-plan-mobile.png'));await page.goto('/#/games/science-lab');await page.getByRole('button',{name:'会下沉',exact:true}).click();await page.getByRole('button',{name:'放入水中',exact:true}).click();await expect(page.getByRole('status',{name:'操作反馈'})).toContainText('你刚才猜');await page.getByRole('button',{name:'同材料换一种实验'}).click();await expect(page.getByRole('button',{name:'靠近磁铁',exact:true})).toBeVisible()
})
