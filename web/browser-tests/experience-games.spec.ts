import { expect,test,type Page } from '@playwright/test'
import { experienceIds,newExperience,type ExperienceId,type ExperienceSave } from '../src/games/experience-games'
import { gameKey,games } from '../src/games/catalog'
import { crops,farmAnimals } from '../src/games/little-farm'
import { instruments } from '../src/games/music-studio'
import { packItems,clothingItems,weatherOutfits } from '../src/games/daily-life'
import { ecoAnimals,ecoLitter } from '../src/games/eco-guardian'
const read=(page:Page,id:ExperienceId)=>page.evaluate(key=>JSON.parse(localStorage.getItem(key)!) as ExperienceSave,gameKey(id))
async function open(page:Page,id:ExperienceId){await page.goto('/#/games/'+id);await expect(page.getByRole('heading',{name:games.find(game=>game.id===id)!.title+'.',exact:true})).toBeVisible()}
async function catchAll(page:Page){const {round}=await read(page,'animal-catch');if(round.kind!=='animal-catch')throw new Error();await page.getByRole('button',{name:'开始接食物',exact:true}).click()
  for(let index=0;index<round.goal;index++){const current=(await read(page,'animal-catch')).round;if(current.kind!=='animal-catch')throw new Error();const food=page.locator(`.falling-food[data-food="${current.animal}"]`).first();await expect(food).toBeVisible();const serial=await food.getAttribute('data-drop'),left=parseFloat((await food.getAttribute('style'))!.match(/left:\s*([\d.]+)/)![1]);const field=page.getByRole('group',{name:'接食物游戏区'}),box=(await field.boundingBox())!;await field.click({position:{x:box.width*left/100,y:box.height-20}});await expect(page.locator(`[data-drop="${serial}"]`)).toHaveCount(0,{timeout:8000});await expect.poll(async()=>{const save=await read(page,'animal-catch');return save.round.kind==='animal-catch'?save.round.caught:0}).toBe(index+1)}
}
async function solve(page:Page,id:ExperienceId){const {round}=await read(page,id)
  switch(round.kind){
    case 'rhythm-band':await page.getByRole('button',{name:'跟着演奏',exact:true}).click();for(const [index,instrument] of round.pattern.entries()){await expect(page.locator(`[data-playing-note="${index}"]`)).toBeVisible();await page.getByRole('button',{name:'敲击'+instruments[instrument].name,exact:true}).click()}break
    case 'little-farm': {
      const needed=[...round.orders!]
      round.fed.forEach((_,index)=>needed[farmAnimals[index].food]++)
      for(const [crop,count] of needed.entries())for(let n=0;n<count;n++){
        await page.getByRole('button',{name:'🌱 播种',exact:true}).click()
        await page.getByRole('combobox',{name:'选择种子'}).selectOption(String(crop))
        await page.locator('[data-plot="0"]').click()
        await page.getByRole('button',{name:'💧 浇水',exact:true}).click()
        for(let day=0;day<crops[crop].days;day++){await page.locator('[data-plot="0"]').click();await page.getByRole('button',{name:'迎接下一天',exact:true}).click()}
        await page.getByRole('button',{name:'🧺 收获',exact:true}).click();await page.locator('[data-plot="0"]').click()
      }
      for(const [index] of round.fed.entries())await page.getByRole('button',{name:'喂'+farmAnimals[index].name,exact:true}).click()
      for(const [index,count] of round.orders!.entries())for(let n=0;n<count;n++)await page.locator('.farm-orders>div').nth(index).getByRole('button',{name:'交付一份',exact:true}).click()
      break
    }
    case 'science-lab':for(const mission of round.missions){await page.locator(`[data-mission="${mission.id}"]`).click();await page.getByRole('button',{name:mission.type==='float'?'放入水中':mission.type==='magnet'?'靠近磁铁':'混合颜料',exact:true}).click()}break
    case 'forest-rescue':for(const id of ['guide','observe','ask','space'])await page.locator(`[data-choice="${id}"]`).click();break
    case 'creative-studio':await page.getByRole('button',{name:'选择花朵印章',exact:true}).click();await page.getByRole('img',{name:'创意画布',exact:true}).click({position:{x:90,y:60}});await page.getByRole('button',{name:'保存作品',exact:true}).click();await expect(page.getByRole('region',{name:'本机小画廊'})).toBeVisible();break
    case 'animal-catch':await catchAll(page);break
    case 'daily-life':for(const id of round.required)await page.getByRole('button',{name:'书包物品 '+packItems.find(item=>item.id===id)!.name,exact:true}).click();await page.getByRole('button',{name:'检查书包',exact:true}).click();for(const id of weatherOutfits[round.weather].items)await page.getByRole('button',{name:'出门衣物 '+clothingItems.find(item=>item.id===id)!.name,exact:true}).click();await page.getByRole('button',{name:'准备出门',exact:true}).click();await page.getByRole('button',{name:'等行人绿灯',exact:true}).click();await page.getByRole('button',{name:'观察左侧',exact:true}).click();await page.getByRole('button',{name:'观察右侧',exact:true}).click();await page.getByRole('button',{name:'和大人一起过街',exact:true}).click();break
    case 'eco-guardian':for(const [index,litter] of round.litter.entries()){await page.locator(`[data-litter="${index}"]`).click();await page.locator(`[data-bin="${ecoLitter[litter].bin}"]`).click()}for(const animal of ecoAnimals)await page.getByRole('button',{name:animal.action,exact:true}).click();break
  }
  if(id!=='creative-studio')await expect(page.getByRole('status',{name:'完成反馈'})).toBeVisible({timeout:10000})
  expect((await read(page,id)).rounds).toBe(1)
}
test('八款体验游戏实际操作完成、刷新恢复，无后端和外部图标请求',async({page},info)=>{
  test.setTimeout(180000);await page.emulateMedia({reducedMotion:'reduce'})
  const errors:string[]=[],api:string[]=[],external:string[]=[];page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(request.url().includes('/api/'))api.push(request.url())});await page.route(/https:\/\/(?:api\.iconify\.design|api\.simplesvg\.com|api\.unisvg\.com)\//,route=>{external.push(route.request().url());return route.abort()})
  for(const id of experienceIds){await open(page,id);await solve(page,id);await page.screenshot({path:info.outputPath(id+'-complete.png'),fullPage:true});await page.reload();await expect(page.getByRole('heading',{name:games.find(game=>game.id===id)!.title+'.',exact:true})).toBeVisible();expect((await read(page,id)).rounds).toBe(1);expect((await read(page,id)).round.finished).toBe(true)}expect(errors).toEqual([]);expect(api).toEqual([]);expect(external).toEqual([])
})
test('八款游戏在 320、390、768 宽度完整显示，说明、难度取消和提示可用',async({page},info)=>{
  test.setTimeout(120000)
  for(const width of [320,390,768]){await page.setViewportSize({width,height:844});for(const id of experienceIds){await open(page,id);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(await page.locator('.explore-play').evaluate(element=>element.getBoundingClientRect().width)).toBeGreaterThanOrEqual(width);await page.getByRole('button',{name:'给我提示',exact:true}).click();await expect(page.getByRole('status',{name:'操作反馈'})).not.toContainText('按照自己的节奏');if(id!=='creative-studio'){await page.getByRole('button',{name:'挑战',exact:true}).click();await page.getByRole('button',{name:'继续当前游戏',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);expect((await read(page,id)).difficulty).toBe('starter')}if(width===390)await page.screenshot({path:info.outputPath(id+'-mobile.png'),fullPage:true})}}
  await page.getByRole('button',{name:'怎么玩',exact:true}).click();await expect(page.getByRole('dialog')).toContainText('模拟夹子');await page.getByRole('button',{name:'知道啦',exact:true}).click()
})
test('自由编曲确实产生声音，停止播放和刷新后保留编曲',async({page})=>{
  await page.addInitScript(()=>{const original=AudioContext.prototype.createOscillator;AudioContext.prototype.createOscillator=function(){document.documentElement.dataset.tones=String(Number(document.documentElement.dataset.tones||0)+1);return original.call(this)}})
  await open(page,'rhythm-band');await page.getByRole('button',{name:'自由编曲',exact:true}).click();await page.locator('[data-sequence="0-0"]').click();await page.locator('[data-sequence="2-1"]').click();await page.getByRole('button',{name:'播放我的节奏',exact:true}).click();await expect.poll(()=>page.evaluate(()=>Number(document.documentElement.dataset.tones||0))).toBeGreaterThanOrEqual(2);await page.getByRole('button',{name:'停止演奏',exact:true}).click();await page.reload();await expect(page.locator('[data-sequence="0-0"]')).toHaveAttribute('aria-pressed','true');await expect(page.locator('[data-sequence="2-1"]')).toHaveAttribute('aria-pressed','true')
})
test('画笔触控、撤回、画廊与 PNG 导出，换画纸保留已存作品',async({page,context},info)=>{
  await page.setViewportSize({width:390,height:844});await open(page,'creative-studio');const canvas=page.getByRole('img',{name:'创意画布',exact:true});await canvas.scrollIntoViewIfNeeded();const box=(await canvas.boundingBox())!;await page.mouse.move(box.x+30,box.y+30);await page.mouse.down();await page.mouse.move(box.x+140,box.y+85,{steps:10});await page.mouse.up();let save=await read(page,'creative-studio');expect(save.round.kind==='creative-studio' && save.round.marks[0].kind==='stroke' && save.round.marks[0].points.length>1).toBe(true)
  await page.getByRole('button',{name:'撤回一步',exact:true}).click();save=await read(page,'creative-studio');expect(save.round.kind==='creative-studio' && save.round.marks.length).toBe(0)
  await page.getByRole('button',{name:'选择星星印章',exact:true}).click();await canvas.scrollIntoViewIfNeeded();const stampBox=(await canvas.boundingBox())!;await canvas.dispatchEvent('pointerdown',{pointerId:7,pointerType:'touch',isPrimary:true,button:0,clientX:stampBox.x+100,clientY:stampBox.y+65});await page.getByRole('button',{name:'保存作品',exact:true}).click();const download=page.waitForEvent('download');await page.getByRole('button',{name:'导出图片',exact:true}).click();const file=await download;expect(file.suggestedFilename()).toMatch(/\.png$/);await file.saveAs(info.outputPath('artwork.png'));await expect(page.getByRole('status',{name:'操作反馈'})).toContainText('1200 × 800')
  await page.getByRole('button',{name:'重新开始',exact:true}).click();await expect(page.getByRole('region',{name:'本机小画廊'})).toBeVisible();await page.reload();await expect(page.getByRole('region',{name:'本机小画廊'})).toBeVisible();expect(context.pages()).toHaveLength(1)
})
test('接食物可暂停并用触摸移动，过街与垃圾分类允许纠错撤回',async({page})=>{
  await page.setViewportSize({width:390,height:844});await open(page,'animal-catch');await page.getByRole('button',{name:'开始接食物',exact:true}).click();await expect(page.locator('.falling-food')).toHaveCount(1);await page.getByRole('button',{name:'暂停游戏',exact:true}).click();const position=await page.locator('.falling-food').getAttribute('style');await page.waitForTimeout(700);expect(await page.locator('.falling-food').getAttribute('style')).toBe(position);const field=page.getByRole('group',{name:'接食物游戏区'}),box=(await field.boundingBox())!;await field.dispatchEvent('pointermove',{pointerType:'touch',buttons:1,clientX:box.x+box.width*.8,clientY:box.y+200});expect(await page.locator('.catch-basket').getAttribute('style')).toContain('80%');await page.reload();await expect(page.getByRole('button',{name:'开始接食物',exact:true})).toBeVisible()
  await open(page,'eco-guardian');const {round}=await read(page,'eco-guardian');if(round.kind!=='eco-guardian')throw new Error();await page.locator('[data-litter="0"]').click();await page.locator(`[data-bin="${(ecoLitter[round.litter[0]].bin+1)%4}"]`).click();await expect(page.getByRole('status',{name:'操作反馈'})).toContainText('应放进');await page.getByRole('button',{name:'撤回一步',exact:true}).click();expect((await read(page,'eco-guardian')).round.mistakes).toBe(0)
})
test('损坏存档、存储失败和账号隔离，体验游戏不上传云存档',async({page,context})=>{
  const guest=newExperience('little-farm'),writes:string[]=[];await context.addInitScript(({key,save})=>{localStorage.setItem('lc_uid','7');localStorage.setItem('lc_u7_migrated','1');localStorage.setItem(key,save)},{key:gameKey('little-farm'),save:JSON.stringify(guest)});await context.route('**/api/v1/auth/me',route=>route.fulfill({json:{id:7,username:'teacher',role:'user'}}));await context.route('**/api/v1/me/games**',route=>{if(route.request().method()!=='GET')writes.push(route.request().url());return route.fulfill({json:{items:[]}})})
  await open(page,'little-farm');await page.locator('[data-plot="0"]').click();await expect.poll(()=>page.evaluate(key=>JSON.parse(localStorage.getItem(key)!).round.moves,gameKey('little-farm','7'))).toBe(1);await page.waitForTimeout(1600);expect(await page.evaluate(key=>localStorage.getItem(key),gameKey('little-farm'))).toBe(JSON.stringify(guest));expect(writes).toEqual([])
  await page.evaluate(key=>localStorage.setItem(key,'{"version":1,"round":{"marks":null}}'),gameKey('creative-studio','7'));await open(page,'creative-studio');await expect(page.getByRole('img',{name:'创意画布',exact:true})).toBeVisible()
  await page.addInitScript(()=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(key.includes('game_science_lab'))throw new DOMException('full','QuotaExceededError');original.call(this,key,value)}});await page.goto('about:blank');await open(page,'science-lab');await expect(page.getByRole('alert')).toContainText('仍可继续');await page.getByRole('button',{name:'放入水中',exact:true}).click();await expect(page.getByRole('status',{name:'实验记录'})).toBeVisible()
})
