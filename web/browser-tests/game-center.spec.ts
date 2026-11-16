import { expect, test } from '@playwright/test'
import { newRocket } from '../src/games/rocket-math'
import { gameKey } from '../src/games/catalog'

test('游客按学科与年龄发现游戏，继续本机进度，手机端完整显示', async ({ page }, info) => {
  const errors: string[] = [], api: string[] = [], externalIcons: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => { if (request.url().includes('/api/')) api.push(request.url()) })
  await page.route(/https:\/\/(?:api\.iconify\.design|api\.simplesvg\.com|api\.unisvg\.com)\//, route => { externalIcons.push(route.request().url()); return route.abort() })
  await page.goto('/#/games')
  await expect(page.getByRole('heading', { name: /学习游戏中心/ })).toBeVisible()
  await expect(page.locator('.game-card')).toHaveCount(32)
  await page.getByRole('button', { name: '益智', exact: true }).click()
  await expect(page.locator('.game-card')).toHaveCount(14)
  await page.getByRole('button', { name: '英语', exact: true }).click()
  await expect(page.locator('.game-card')).toHaveCount(2)
  await page.getByRole('combobox', { name: '按年龄筛选' }).selectOption('4')
  await expect(page.getByText('这个组合暂时没有游戏')).toBeVisible()
  await page.getByRole('button', { name: '查看全部游戏' }).click()
  await page.screenshot({ path: info.outputPath('game-center-desktop.png'), fullPage: true })
  await page.getByRole('link', { name: '开始口算火箭' }).click()
  await expect(page.getByRole('heading', { name: '口算火箭.' })).toBeVisible()
  const state = await page.evaluate(key => JSON.parse(localStorage.getItem(key)!), gameKey('rocket-math'))
  await page.getByRole('button', { name: `选择答案 ${state.flight.questions[0].answer}`, exact: true }).click()
  await page.getByRole('link', { name: '学习游戏中心', exact: true }).click()
  await expect(page.getByRole('region', { name: '最近玩过' })).toBeVisible()
  await page.getByRole('region', { name: '最近玩过' }).getByRole('link', { name: '继续口算火箭' }).click()
  await expect(page.getByRole('status', { name: '答题反馈' })).toContainText('答对了')
  await page.reload()
  await expect(page.getByRole('status', { name: '答题反馈' })).toContainText('答对了')
  await page.getByRole('link', { name: '学习游戏中心', exact: true }).click()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.game-card')).toHaveCount(32)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('game-center-mobile.png'), fullPage: true })
  expect(errors).toEqual([]); expect(api).toEqual([]); expect(externalIcons).toEqual([])
})

test('登录后从云端恢复，多设备竞争要求选取存档，账号变化停止同步', async ({ page, context }) => {
  let remote = { game_id: 'rocket-math', revision: 1, mutation_id: 'cloud-first', progress: newRocket(), updated_at: 100 }
  let writes = 0
  await context.addInitScript(() => { localStorage.setItem('lc_uid', '7'); localStorage.setItem('lc_u7_migrated', '1') })
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/auth/me') return route.fulfill({ json: { id: 7, username: 'teacher', role: 'user' } })
    if (path === '/api/v1/me/games') return route.fulfill({ json: { items: [remote] } })
    if (path === '/api/v1/me/games/rocket-math' && route.request().method() === 'PUT') {
      expect(route.request().headers()['x-workspace-user']).toBe('7')
      const body = route.request().postDataJSON()
      if (body.revision !== remote.revision) return route.fulfill({ status: 409, json: { detail: { error: '另一台设备已更新', code: 'game_progress_conflict' } } })
      writes++; remote = { ...remote, ...body, revision: body.revision + 1, updated_at: 200 }
      return route.fulfill({ json: remote })
    }
    throw new Error('未声明的游戏请求：' + path)
  })
  await page.goto('/#/games/rocket-math')
  await expect(page.getByRole('heading', { name: '口算火箭.' })).toBeVisible()
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)!), gameKey('rocket-math', '7'))).toEqual(remote.progress)
  expect(await page.evaluate(key => localStorage.getItem(key), gameKey('rocket-math'))).toBeNull()
  const answer = remote.progress.flight.questions[0].answer
  remote = { ...remote, revision: 2, progress: newRocket('explorer') }
  await page.getByRole('button', { name: `选择答案 ${answer}`, exact: true }).click()
  await expect(page.getByText('口算火箭有两份不同的进度')).toBeVisible()
  expect(writes).toBe(0)
  await page.getByRole('button', { name: '保留本机并同步' }).click()
  await expect(page.getByText('口算火箭有两份不同的进度')).toHaveCount(0)
  await expect.poll(() => writes).toBe(1)
  expect(remote.progress.flight.answered).toBe(answer)
  await page.evaluate(() => window.dispatchEvent(new StorageEvent('storage', { key: 'lc_uid', newValue: '8' })))
  await expect(page.getByText('登录状态已变化，本机进度已保留。请刷新后继续。')).toBeVisible()
  await expect(page.getByRole('heading', { name: '口算火箭.' })).toHaveCount(0)
})
