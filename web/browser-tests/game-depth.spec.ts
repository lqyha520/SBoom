import { expect,test,type Page } from '@playwright/test'
import { newBrain,type BrainSave } from '../src/games/brain-games'
import { sokobanSolution } from '../src/games/sokoban'
import { gameKey,games } from '../src/games/catalog'
import { newExperience,type ExperienceSave } from '../src/games/experience-games'
import { forestScene } from '../src/games/forest-rescue'
import { type ClockSave } from '../src/games/clock-town'
import { levels,newMaze } from '../src/games/robot-maze'

const read=async<T>(page:Page,id:Parameters<typeof gameKey>[0])=>{await expect(page.locator(`a[aria-current="page"][href$="/games/${id}"]`)).toHaveCount(1);await expect.poll(()=>page.evaluate(key=>!!localStorage.getItem(key),gameKey(id))).toBe(true);return page.evaluate(key=>JSON.parse(localStorage.getItem(key)!) as T,gameKey(id))}
test('32 款游戏加载正常，动态图标也不请求外部服务',async({page})=>{
  const errors:string[]=[],external:string[]=[]
  page.on('pageerror',error=>errors.push(error.message))
  await page.route(/https:\/\/(?:api\.iconify\.design|api\.simplesvg\.com|api\.unisvg\.com)\//,route=>{external.push(route.request().url());return route.abort()})
  for(const game of games){await page.goto('/#/games/'+game.id);await expect(page.locator('h1')).toBeVisible();await expect(page.getByRole('link',{name:game.title,exact:true})).toHaveAttribute('aria-current','page')}
  expect(errors).toEqual([]);expect(external).toEqual([])
})
async function warehouse(page:Page){const save=await read<BrainSave>(page,'sokoban');if(save.round.kind!=='sokoban')throw new Error();await page.locator('.soko-board').focus();for(const direction of sokobanSolution(save.round)!)await page.keyboard.press(['ArrowUp','ArrowRight','ArrowDown','ArrowLeft'][direction]);await expect(page.getByRole('status',{name:'过关反馈'})).toBeVisible()}
test('推箱子连续三关不同，重试保留布局，刷新和最后一关回顾可用',async({page},info)=>{
  test.setTimeout(90000);await page.setViewportSize({width:390,height:844});await page.goto('/#/games/sokoban')
  const levelsSeen:number[]=[]
  for(let stage=1;stage<=3;stage++){
    const save=await read<BrainSave>(page,'sokoban');if(save.round.kind!=='sokoban')throw new Error();levelsSeen.push(save.round.level)
    if(stage===2){const layout=JSON.stringify(save.round);await page.getByRole('button',{name:'重新开始',exact:true}).click();await page.getByRole('button',{name:'重试本关',exact:true}).click();expect(JSON.stringify((await read<BrainSave>(page,'sokoban')).round)).toBe(layout);await page.reload();expect((await read<BrainSave>(page,'sokoban')).round.stage).toBe(2)}
    await warehouse(page);await page.getByRole('button',{name:'前往下一关',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0)
  }
  expect(new Set(levelsSeen).size).toBe(3);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.screenshot({path:info.outputPath('sokoban-mobile-next.png'),fullPage:true})
  const final=newBrain('sokoban','master');final.journey!.completed.master=23
  const {visitSokoban}=await import('../src/games/brain-games');visitSokoban(final,24)
  await page.evaluate(({key,save})=>localStorage.setItem(key,save),{key:gameKey('sokoban'),save:JSON.stringify(final)});await page.reload();await warehouse(page)
  await expect(page.getByText('三章仓库挑战全部完成！可以回顾地图，用更少推动赢取三星。')).toBeVisible()
  await page.getByRole('button',{name:'回顾第 1 关',exact:true}).click();expect((await read<BrainSave>(page,'sokoban')).round.stage).toBe(1)
  await page.screenshot({path:info.outputPath('sokoban-master-review.png'),fullPage:true})
})
test('新的森林三条任务实际通关，下一轮更换故事；环保地点和动物变化',async({page},info)=>{
  const journey=newExperience('forest-rescue').journey!;journey.completed.starter=1
  const save=newExperience('forest-rescue','starter',Math.random,journey)
  await page.addInitScript(({key,save})=>localStorage.setItem(key,save),{key:gameKey('forest-rescue'),save:JSON.stringify(save)})
  await page.goto('/#/games/forest-rescue')
  for(let step=0;step<9;step++){const current=await read<ExperienceSave<'forest-rescue'>>(page,'forest-rescue');if(current.round.finished)break;const choice=forestScene(current.round).choices.find(c=>!c.unsafe)!;await page.locator(`[data-choice="${choice.id}"]`).click()}
  await expect(page.getByRole('status',{name:'完成反馈'})).toBeVisible();await page.getByRole('button',{name:'下一段探索',exact:true}).click()
  expect((await read<ExperienceSave<'forest-rescue'>>(page,'forest-rescue')).round.episode).not.toBe(save.round.episode)
  await page.screenshot({path:info.outputPath('forest-new-story.png'),fullPage:true})
  const ecoJourney=newExperience('eco-guardian').journey!;ecoJourney.completed.starter=1
  const eco=newExperience('eco-guardian','starter',Math.random,ecoJourney)
  await page.evaluate(({key,save})=>localStorage.setItem(key,save),{key:gameKey('eco-guardian'),save:JSON.stringify(eco)})
  await page.goto('/#/games/eco-guardian');await expect(page.locator('.eco-beach')).toHaveAttribute('aria-label','社区公园清理区');await expect(page.getByRole('button',{name:'为小刺猬留出灌木通道',exact:true})).toBeVisible()
})
test('动手拨钟实际纠错、跨整点和刷新草稿，后期机器人手机地图完整',async({page},info)=>{
  await page.setViewportSize({width:390,height:844});await page.goto('/#/games/clock-town')
  await page.getByRole('button',{name:'动手拨时钟',exact:true}).click()
  const clock=await read<ClockSave>(page,'clock-town'),q=clock.round.questions[0]
  const wrong=q.hour%12+1;for(let n=0;n<wrong;n++)await page.getByRole('button',{name:'向前拨时针',exact:true}).click()
  await page.getByRole('button',{name:'拨好了，检查一下',exact:true}).click();await expect(page.getByText('还没拨对，看看时针和分针，再调整一下。')).toBeVisible()
  await page.reload();expect((await read<ClockSave>(page,'clock-town')).round.dial?.[0]).toBe(wrong)
  await page.getByRole('button',{name:'向后拨时针',exact:true}).click();await page.getByRole('button',{name:'拨好了，检查一下',exact:true}).click();await expect(page.getByRole('button',{name:'下一个时间',exact:true})).toBeVisible()
  await page.screenshot({path:info.outputPath('clock-dial-mobile.png'),fullPage:true})
  const maze=newMaze();maze.level=35;maze.stars=levels.map((_,index)=>index<35?3:0);maze.program=levels[35].reference!
  await page.evaluate(({key,save})=>localStorage.setItem(key,save),{key:gameKey('robot-maze'),save:JSON.stringify(maze)})
  await page.goto('/#/games/robot-maze');await expect(page.getByRole('heading',{name:levels[35].name,exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.screenshot({path:info.outputPath('robot-late-mobile.png'),fullPage:true})
})
