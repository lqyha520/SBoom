import { expect, test, type Page } from '@playwright/test'
import { games, gameKey } from '../src/games/catalog'
import { hanoiHint, pipeTurns, puzzleIds, shapeNames, type PuzzleId, type PuzzleSave } from '../src/games/puzzle-games'

const state = (page: Page, id: PuzzleId) => page.evaluate(key => JSON.parse(localStorage.getItem(key)!) as PuzzleSave, gameKey(id))
async function open(page: Page, id: PuzzleId) {
  await page.goto(`/#/games/${id}`)
  await expect(page.getByRole('heading', { name: games.find(game => game.id === id)!.title + '.', exact: true })).toBeVisible()
  await expect(page.getByRole('status', { name: '游戏进度保存状态' })).toContainText('当前浏览器')
}
async function solve(page: Page, id: PuzzleId) {
  let save = await state(page, id)
  if (id === 'sliding-puzzle' || id === 'tower-hanoi') {
    for (let step = 0; step < 100 && !save.round.finished; step++) {
      if (id === 'sliding-puzzle') await page.locator(`[data-cell="${save.round.route[0]}"]`).click()
      else { const move = hanoiHint(save.round)!; await page.locator('.hanoi-peg').nth(move.from).click(); await page.locator('.hanoi-peg').nth(move.to).click() }
      save = await state(page, id)
    }
  } else if (id === 'lights-out') {
    for (const index of save.round.plan.flatMap((value, index) => value ? [index] : [])) { if (!(await state(page, id)).round.finished) await page.locator(`[data-cell="${index}"]`).click() }
  } else if (id === 'picture-logic') {
    for (let mode = 1; mode <= 2; mode++) {
      await page.getByRole('button', { name: mode === 1 ? '填色' : '标空', exact: true }).click()
      for (const [index, value] of save.round.solution.entries()) if ((value ? 1 : 2) === mode) await page.locator(`[data-cell="${index}"]`).click()
    }
  } else {
    for (const [index, value] of save.round.solution.entries()) {
      if ((await state(page, id)).round.finished) break
      if (id === 'shape-sudoku' && !save.round.fixed.includes(index)) {
        await page.locator(`[data-cell="${index}"]`).click()
        await page.getByRole('button', { name: `填入${shapeNames[value]}`, exact: true }).click()
      } else if (id === 'pipe-connect') {
        for (let turn = pipeTurns(save.round.cells[index], value); turn > 0; turn--) await page.locator(`[data-cell="${index}"]`).click()
      }
    }
  }
  await expect(page.getByRole('status', { name: '过关反馈' })).toContainText('你解开了这个小挑战')
  expect((await state(page, id)).rounds).toBe(1)
}

test('六款益智游戏实际操作通关，刷新保留进度，游客不请求后端和外部图标', async ({ page }, info) => {
  test.setTimeout(120_000)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const errors: string[] = [], requests: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => { if (request.url().includes('/api/') || /https:\/\/(api\.iconify|api\.simplesvg|api\.unisvg)/.test(request.url())) requests.push(request.url()) })
  for (const id of puzzleIds) {
    await open(page, id)
    await solve(page, id)
    await page.screenshot({ path: info.outputPath(`${id}-complete.png`), fullPage: true })
    await page.reload()
    await expect(page.getByRole('status', { name: '过关反馈' })).toBeVisible()
    expect((await state(page, id)).rounds).toBe(1)
  }
  expect(errors).toEqual([]); expect(requests).toEqual([])
})

test('手机上三档棋盘不溢出，提示、撤回、取消换局和玩法窗口可用', async ({ page }, info) => {
  test.setTimeout(90_000)
  for (const width of [320, 390, 768]) {
    await page.setViewportSize({ width, height: 844 })
    for (const id of puzzleIds) {
      await open(page, id)
      if ((await state(page, id)).difficulty === 'master') await page.getByRole('button', { name: '重新开始', exact: true }).click()
      else await page.getByRole('button', { name: '挑战', exact: true }).click()
      await page.getByRole('button', { name: /^(开始新挑战|重试本关)$/, exact: true }).click()
      await expect(page.getByRole('dialog')).toHaveCount(0)
      expect((await state(page, id)).difficulty).toBe('master')
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      const visible = await page.locator('nav[aria-label="游戏导航"] [aria-current="page"]').evaluate(link => { const r = link.getBoundingClientRect(), nav = link.parentElement!.getBoundingClientRect(); return r.left >= nav.left - 1 && r.right <= nav.right + 1 })
      expect(visible).toBe(true)
      if (width === 390) await page.screenshot({ path: info.outputPath(`${id}-mobile.png`), fullPage: true })
    }
  }
  await open(page, 'shape-sudoku')
  const before = await state(page, 'shape-sudoku')
  await page.getByRole('button', { name: '给我提示', exact: true }).click()
  await expect(page.getByRole('status', { name: '游戏提示' })).toBeVisible()
  expect((await state(page, 'shape-sudoku')).round.cells).toEqual(before.round.cells)
  const index = before.round.cells.findIndex((value, index) => value !== before.round.solution[index])
  await page.locator(`[data-cell="${index}"]`).focus(); await page.keyboard.press('Enter')
  await page.getByRole('button', { name: `填入${shapeNames[before.round.solution[index]]}`, exact: true }).focus(); await page.keyboard.press('Space')
  expect((await state(page, 'shape-sudoku')).round.cells[index]).toBe(before.round.solution[index])
  await page.getByRole('button', { name: '撤回一步', exact: true }).click()
  expect((await state(page, 'shape-sudoku')).round.cells[index]).toBe(before.round.cells[index])
  await page.getByRole('button', { name: '入门', exact: true }).click()
  await page.getByRole('button', { name: '继续当前游戏', exact: true }).click()
  expect((await state(page, 'shape-sudoku')).difficulty).toBe('master')
  await page.getByRole('button', { name: '怎么玩', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('每行、每列')
  await page.getByRole('button', { name: '知道啦', exact: true }).click()
})

test('汉诺塔阻止大盘压小盘，损坏存档重新生成棋盘，存储失败仍能操作', async ({ page }) => {
  await open(page, 'tower-hanoi')
  await page.locator('.hanoi-peg').nth(0).click(); await page.locator('.hanoi-peg').nth(2).click()
  await page.locator('.hanoi-peg').nth(0).click(); await page.locator('.hanoi-peg').nth(2).click()
  await expect(page.getByRole('status', { name: '操作反馈' })).toContainText('大圆盘不能')
  expect((await state(page, 'tower-hanoi')).round.moves).toBe(1)
  await page.evaluate(key => localStorage.setItem(key, '{"version":1,"round":{"cells":[99]}}'), gameKey('pipe-connect'))
  await open(page, 'pipe-connect')
  expect((await state(page, 'pipe-connect')).round.cells).toHaveLength(9)
  await page.addInitScript(() => { const original = Storage.prototype.setItem; Storage.prototype.setItem = function(key, value) { if (key.startsWith('lc_game_lights_out')) throw new DOMException('full', 'QuotaExceededError'); original.call(this, key, value) } })
  await page.goto('about:blank')
  await open(page, 'lights-out')
  await expect(page.getByRole('alert')).toContainText('仍可继续')
  await page.locator('[data-cell="0"]').click()
  await expect(page.getByRole('region', { name: '游戏进度' })).toContainText('1')
})
