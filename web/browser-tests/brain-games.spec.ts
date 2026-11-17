import { expect,test,type Page } from '@playwright/test'
import { games,gameKey } from '../src/games/catalog'
import { balanceCombination,brainIds,newBrain,strokeSolution,type BrainId,type BrainSave } from '../src/games/brain-games'
import { colorNames } from '../src/games/color-sort'
import { pieceNames,tangramLayouts } from '../src/games/tangram'
import { sokoDirections,sokobanSolution } from '../src/games/sokoban'

const read=(page:Page,id:BrainId)=>page.evaluate(key=>JSON.parse(localStorage.getItem(key)!) as BrainSave,gameKey(id))
async function open(page:Page,id:BrainId) { await page.goto('/#/games/'+id);await expect(page.getByRole('heading',{name:games.find(game=>game.id===id)!.title+'.',exact:true})).toBeVisible() }
async function solve(page:Page,id:BrainId) {
  const save=await read(page,id),round=save.round
  switch(round.kind) {
    case 'tangram':
      for(const [index,piece] of tangramLayouts[round.layout].solution.entries()) {
        await page.getByRole('button',{name:'选择'+pieceNames[index],exact:true}).click()
        for(let rotate=0;rotate<piece.rotation;rotate++)await page.getByRole('button',{name:'旋转',exact:true}).click()
        if(piece.flipped)await page.getByRole('button',{name:'翻面',exact:true}).click()
        await page.locator(`[data-anchor="${piece.y*8+piece.x}"]`).click()
      }
      break
    case 'sokoban': {
      const path=sokobanSolution(round)!;await page.locator('.soko-board').focus()
      for(const direction of path)await page.keyboard.press(['ArrowUp','ArrowRight','ArrowDown','ArrowLeft'][direction])
      break
    }
    case 'pattern-train':
      for(const [index,question] of round.questions.entries()) { await page.getByRole('button',{name:'选择下一项 '+question.answer,exact:true}).click();await expect(page.getByRole('status',{name:'规律说明'})).toContainText(question.answer);await page.getByRole('button',{name:index===5?'查看结果':'下一题',exact:true}).click() }
      break
    case 'one-stroke': for(const node of strokeSolution(round)!)await page.locator(`[data-node="${node}"]`).click();break
    case 'balance-scale':
      for(const [index,count] of balanceCombination(round)!.entries())for(let n=0;n<count;n++)await page.getByRole('button',{name:`放入 ${round.weights[index]} 克砝码`,exact:true}).click()
      break
    case 'color-sort':
      for(const [from,to] of round.route) { if((await read(page,id)).round.finished)break;await page.locator(`[data-tube="${from}"]`).click();await page.locator(`[data-tube="${to}"]`).click() }
      break
    case 'mirror-draw':
      for(const [index,color] of round.solution.entries())if(!round.fixed.includes(index) && round.cells[index]!==color) { await page.getByRole('button',{name:'选择'+colorNames[color-1],exact:true}).click();await page.locator(`[data-mirror="${index}"]`).click() }
      break
    case 'spot-difference':for(const index of round.differences)await page.getByRole('region',{name:'右图',exact:true}).locator(`[data-spot="${index}"]`).click();break
  }
  await expect(page.getByRole('status',{name:'过关反馈'})).toContainText('你解开了这个小挑战')
  expect((await read(page,id)).rounds).toBe(1)
}

test('八款游戏通过真实点击和键盘通关，刷新恢复，游客无后端和外部图标请求',async({page},info)=>{
  test.setTimeout(120_000)
  await page.emulateMedia({reducedMotion:'reduce'})
  const errors:string[]=[],requests:string[]=[]
  page.on('pageerror',error=>errors.push(error.message))
  page.on('request',request=>{if(request.url().includes('/api/') || /https:\/\/(api\.iconify|api\.simplesvg|api\.unisvg)/.test(request.url()))requests.push(request.url())})
  for(const id of brainIds) {
    await open(page,id);await solve(page,id)
    await page.screenshot({path:info.outputPath(id+'-complete.png'),fullPage:true})
    await page.reload();await expect(page.getByRole('status',{name:'过关反馈'})).toBeVisible()
    expect((await read(page,id)).rounds).toBe(1)
  }
  expect(errors).toEqual([]);expect(requests).toEqual([])
})

test('320、390、768 宽度棋盘完整，难度切换可取消，说明和提示可用',async({page},info)=>{
  test.setTimeout(120_000)
  for(const width of [320,390,768]) {
    await page.setViewportSize({width,height:844})
    for(const id of brainIds) {
      await open(page,id)
      const difficulty=width===768?'进阶':'挑战'
      if((await read(page,id)).difficulty===(width===768?'explorer':'master'))await page.getByRole('button',{name:'重新开始',exact:true}).click()
      else await page.getByRole('button',{name:difficulty,exact:true}).click()
      await page.getByRole('button',{name:/^(开始新挑战|重试本关)$/,exact:true}).click()
      await expect(page.getByRole('dialog')).toHaveCount(0)
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
      expect(await page.locator('.brain-play').evaluate(element=>element.getBoundingClientRect().width)).toBeGreaterThanOrEqual(width)
      if(width===390)await page.screenshot({path:info.outputPath(id+'-mobile.png'),fullPage:true})
      await page.getByRole('button',{name:'给我提示',exact:true}).click()
      await expect(page.getByRole('status',{name:'游戏提示'})).toBeVisible()
    }
  }
  await page.getByRole('button',{name:'入门',exact:true}).click()
  await page.getByRole('button',{name:'继续当前游戏',exact:true}).click()
  expect((await read(page,'spot-difference')).difficulty).toBe('explorer')
  await page.getByRole('button',{name:'怎么玩',exact:true}).click()
  await expect(page.getByRole('dialog')).toContainText('比较两幅')
  await page.getByRole('button',{name:'知道啦',exact:true}).click()
})

test('规律题纠错与撤回，颜色排序限制移动，损坏存档和存储故障能继续玩',async({page})=>{
  await open(page,'pattern-train')
  const pattern=(await read(page,'pattern-train')).round
  if(pattern.kind!=='pattern-train')throw new Error()
  const wrong=pattern.questions[0].options.find(value=>value!==pattern.questions[0].answer)!
  await page.getByRole('button',{name:'选择下一项 '+wrong,exact:true}).click()
  await expect(page.getByRole('status',{name:'操作反馈'})).toContainText('规律说明')
  await page.getByRole('button',{name:'撤回一步',exact:true}).click()
  await expect(page.getByRole('status',{name:'规律说明'})).toHaveCount(0)
  await page.reload();expect((await read(page,'pattern-train')).round.mistakes).toBe(0)
  await open(page,'color-sort');const sort=(await read(page,'color-sort')).round
  if(sort.kind!=='color-sort')throw new Error()
  const source=sort.tubes.findIndex(tube=>tube.length),target=sort.tubes.findIndex((tube,index)=>index!==source && tube.length && tube.at(-1)!==sort.tubes[source].at(-1))
  if(target>=0) { await page.locator(`[data-tube="${source}"]`).click();await page.locator(`[data-tube="${target}"]`).click();await expect(page.getByRole('status',{name:'操作反馈'})).toContainText('顶部同色') }
  await page.evaluate(key=>localStorage.setItem(key,'{"version":1,"round":{"pieces":[]}}'),gameKey('tangram'))
  await open(page,'tangram');expect((await read(page,'tangram')).round.kind).toBe('tangram')
  await page.addInitScript(()=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(key.startsWith('lc_game_one_stroke'))throw new DOMException('full','QuotaExceededError');original.call(this,key,value)}})
  await page.goto('about:blank');await open(page,'one-stroke')
  await expect(page.getByRole('alert')).toContainText('仍可继续')
  await page.locator('.stroke-board button.start').first().click();await expect(page.getByRole('region',{name:'游戏进度'})).toContainText('1')
})

test('登录账号的益智存档与游客隔离，八款新游戏不向云端上传',async({page,context})=>{
  const guest=newBrain('sokoban'),requests:string[]=[]
  await context.addInitScript(({key,save})=>{localStorage.setItem('lc_uid','7');localStorage.setItem('lc_u7_migrated','1');localStorage.setItem(key,save)},{key:gameKey('sokoban'),save:JSON.stringify(guest)})
  await context.route('**/api/v1/auth/me',route=>route.fulfill({json:{id:7,username:'teacher',role:'user'}}))
  await context.route('**/api/v1/me/games**',route=>{if(route.request().method()!=='GET')requests.push(route.request().url());return route.fulfill({json:{items:[]}})})
  await open(page,'sokoban')
  const owned=await page.evaluate(key=>JSON.parse(localStorage.getItem(key)!) as BrainSave,gameKey('sokoban','7'))
  if(owned.round.kind!=='sokoban')throw new Error()
  const direction=sokobanSolution(owned.round)![0]
  await page.getByRole('button',{name:`向${sokoDirections[direction].name}走`,exact:true}).click()
  await expect.poll(()=>page.evaluate(key=>JSON.parse(localStorage.getItem(key)!).round.moves,gameKey('sokoban','7'))).toBe(1)
  await page.waitForTimeout(2100)
  expect(await page.evaluate(key=>localStorage.getItem(key),gameKey('sokoban'))).toBe(JSON.stringify(guest))
  expect(requests).toEqual([])
})
