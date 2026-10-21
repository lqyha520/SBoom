import { expect, test, type Page } from '@playwright/test'

const storageKey = 'lc_game_little_shop_v1_guest'
async function getState(page: Page) {
  return page.evaluate(key => JSON.parse(localStorage.getItem(key)!), storageKey)
}
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
}
async function packFirst(page: Page) {
  await page.getByRole('button', { name: '装入一个苹果', exact: true }).click({ clickCount: 2 })
  await page.getByRole('button', { name: '装入一个香蕉', exact: true }).click()
  await page.getByRole('button', { name: '装好了，去结账', exact: true }).click()
}

test('免登录试玩：装货纠错、算总价、找零钱、刷新恢复和整日升级', async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const errors: string[] = []
  const apiRequests: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => { if (request.url().includes('/api/')) apiRequests.push(request.url()) })
  await page.goto('/#/games/little-shop')
  await expect(page.getByRole('heading', { name: '小小店长.' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('little-shop-desktop.png'), fullPage: true })
  await noOverflow(page)
  await page.getByRole('button', { name: '装好了，去结账' }).click()
  await expect(page.getByRole('status', { name: '订单反馈' })).toContainText('购物单')
  await packFirst(page)
  await page.getByRole('button', { name: '数字9', exact: true }).click()
  await page.getByRole('button', { name: '确认总价', exact: true }).click()
  await expect(page.getByRole('status', { name: '订单反馈' })).toContainText('每种水果的钱')
  await page.getByRole('button', { name: '清空总价', exact: true }).click()
  await page.getByRole('button', { name: '数字8', exact: true }).click()
  await page.getByRole('button', { name: '确认总价', exact: true }).click()
  await page.screenshot({ path: info.outputPath('little-shop-change.png'), fullPage: true })
  await page.getByRole('button', { name: '放入1元', exact: true }).click()
  await page.getByRole('button', { name: '找好了，交给顾客', exact: true }).click()
  await expect(page.getByRole('status', { name: '订单反馈' })).toContainText('顾客付的钱')
  await page.getByRole('button', { name: '放入1元', exact: true }).click()
  await page.getByRole('button', { name: '找好了，交给顾客', exact: true }).click()
  await expect(page.getByText('水果和钱都算对了！')).toBeVisible()
  expect((await getState(page)).revenue).toBe(8)
  await page.reload()
  await expect(page.getByText('水果和钱都算对了！')).toBeVisible()
  expect((await getState(page)).revenue).toBe(8)
  const orders = [{ banana: 2, pear: 1, total: 8, change: 2 }, { apple: 1, orange: 1, total: 8, change: 2 }, { pear: 2, orange: 1, total: 13, change: 7 }]
  for (const order of orders) {
    await page.getByRole('button', { name: '接待下一位顾客', exact: true }).click()
    for (const [id, name] of [['apple', '苹果'], ['banana', '香蕉'], ['pear', '梨子'], ['orange', '橙子']] as const) {
      const count = order[id as keyof typeof order] || 0
      for (let n = 0; n < count; n++) await page.getByRole('button', { name: '装入一个' + name, exact: true }).click()
    }
    await page.getByRole('button', { name: '装好了，去结账', exact: true }).click()
    for (const digit of String(order.total)) await page.getByRole('button', { name: '数字' + digit, exact: true }).click()
    await page.getByRole('button', { name: '确认总价', exact: true }).click()
    if (order.change >= 5) await page.getByRole('button', { name: '放入5元', exact: true }).click()
    await page.getByRole('button', { name: '放入2元', exact: true }).click()
    await page.getByRole('button', { name: '找好了，交给顾客', exact: true }).click()
  }
  await page.getByRole('button', { name: '结束营业，看看收获', exact: true }).click()
  await expect(page.getByRole('heading', { name: '今天也是好店长！' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('little-shop-summary.png'), fullPage: true })
  expect((await getState(page)).profit).toBe(21)
  await page.getByRole('button', { name: '升级', exact: true }).click()
  expect((await getState(page)).cash).toBe(9)
  await page.getByRole('button', { name: '开始第 2 天', exact: true }).click()
  await expect(page.getByText('第 2 天', { exact: true })).toBeVisible()
  expect((await getState(page)).stock.apple).toBe(10)
  expect(apiRequests).toEqual([])
  expect(errors).toEqual([])
})

test('手机试玩：提示、移除商品、暂停和难度切换', async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#/games/little-shop')
  await expect(page.getByRole('heading', { name: '小小店长.' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('little-shop-mobile.png'), fullPage: true })
  await noOverflow(page)
  await page.getByRole('button', { name: '暂停游戏', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: '继续营业', exact: true }).click()
  await page.getByRole('button', { name: '给我一点提示', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('苹果 2 个')
  await page.getByRole('button', { name: '装入一个橙子', exact: true }).click()
  await page.getByRole('button', { name: '从购物袋取出一个橙子', exact: true }).click()
  expect((await getState(page)).bag.orange).toBe(0)
  await page.getByRole('button', { name: '数一数', exact: true }).click()
  await page.getByRole('button', { name: '继续当前游戏', exact: true }).click()
  expect((await getState(page)).difficulty).toBe('change')
  await page.getByRole('button', { name: '数一数', exact: true }).click()
  await page.getByRole('button', { name: '切换并开始', exact: true }).click()
  await packFirst(page)
  await expect(page.getByText('水果种类和数量都装对了！')).toBeVisible()
  await page.getByRole('button', { name: '查看店长徽章', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('我的店长徽章')
  await page.getByRole('button', { name: '关闭徽章', exact: true }).click()
  await noOverflow(page)
  await page.setViewportSize({ width: 320, height: 740 })
  await noOverflow(page)
})

test('工作台进入游戏前保存草稿，返回后仍能编辑保存；账号与访客进度隔离', async ({ page, context }) => {
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let json: unknown
    if (path === '/api/v1/auth/me') json = { id: 7, username: 'teacher', role: 'user' }
    else if (path === '/api/v1/scope/available') json = { available: { 小学三年级: ['数学'] } }
    else if (path === '/api/v1/scope') json = { allowed: ['加减法'] }
    else if (path === '/api/v1/me/templates') json = { templates: [] }
    else if (path === '/api/v1/me/usage') json = { requests: 0, daily_limit: 0 }
    else throw new Error('未声明的请求：' + path)
    await route.fulfill({ json })
  })
  await page.goto('/')
  const title = page.getByRole('textbox', { name: '试卷标题', exact: true })
  await title.fill('游戏前的草稿')
  await page.getByRole('button', { name: '学习游戏', exact: true }).click()
  await expect(page.getByRole('heading', { name: '小小店长.' })).toBeVisible()
  await page.getByRole('button', { name: '装入一个苹果', exact: true }).click()
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('lc_u7_game_little_shop_v1')!).bag.apple)).toBe(1)
  expect(await page.evaluate(key => localStorage.getItem(key), storageKey)).toBeNull()
  await page.getByRole('link', { name: '返回工作台', exact: true }).click()
  await expect(title).toHaveValue('游戏前的草稿')
  await title.fill('游戏后的草稿')
  await page.getByRole('button', { name: '学习游戏', exact: true }).click()
  await expect(page.getByRole('heading', { name: '小小店长.' })).toBeVisible()
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('lc_u7_game_little_shop_v1')!).bag.apple)).toBe(1)
  await page.getByRole('link', { name: '返回工作台', exact: true }).click()
  await expect(title).toHaveValue('游戏后的草稿')
  await page.setViewportSize({ width: 390, height: 844 })
  await noOverflow(page)
})
