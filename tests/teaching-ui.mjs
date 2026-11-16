import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
const { chromium, request, expect } = createRequire(path.resolve('web/package.json'))('@playwright/test')
const base = process.env.MINI_UI_BASE
assert.ok(base && ['127.0.0.1', 'localhost'].includes(new URL(base).hostname))
const output = path.resolve(process.env.TEACHING_UI_OUTPUT || 'artifacts/remove-curriculum-20261115/mini')
await mkdir(output, { recursive: true })
const browser = await chromium.launch()
const api = await request.newContext({ baseURL: base })
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
async function localRequests(route) {
  const req = route.request(), url = new URL(req.url())
  if (url.pathname.startsWith('/api/v1/')) {
    if (req.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: { 'access-control-allow-origin': base, 'access-control-allow-credentials': 'true', 'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS', 'access-control-allow-headers': req.headers()['access-control-request-headers'] || '*' } }); return
    }
    const response = await route.fetch({ url: base + url.pathname + url.search, headers: { ...req.headers(), origin: base }, timeout: 20000 })
    await route.fulfill({ response, headers: { ...response.headers(), 'access-control-allow-origin': base, 'access-control-allow-credentials': 'true' } }); return
  }
  if (url.origin === new URL(base).origin || ['data:', 'blob:'].includes(url.protocol)) await route.continue()
  else await route.abort()
}
await context.route('**/*', localRequests)
const page = await context.newPage()
const errors = []
page.on('pageerror', e => errors.push(e.message))
try {
  const login = await (await api.post('/api/v1/mini/login-password', { data: { username: 'ui_reader', password: 'reader-pass-123' } })).json()
  const token = { Authorization: 'Bearer ' + login.token }
  for (const [method, suffix] of [['GET',''], ['PUT',''], ['GET','/recommendations'], ['GET','/textbooks'], ['DELETE','/old']]) {
    const response = await api.fetch('/api/v1/mini/curriculum' + suffix, { method, headers: token })
    assert.equal(response.status(), 410)
  }
  await page.goto(base + '/#/pages/login/index?returnTo=%2Fpages%2Faccount%2Findex')
  await page.getByRole('checkbox', { name: '已阅读并同意用户协议和隐私政策' }).click()
  await page.locator('.login-primary').click()
  await page.locator('.account-login-sheet .login-form input').nth(0).fill('ui_reader')
  await page.locator('.account-login-sheet .login-form input').nth(1).fill('reader-pass-123')
  await page.locator('.account-login-sheet').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.locator('.learning-card')).toBeVisible()
  let unread = 1
  await page.route('**/api/v1/mini/messages?*', route => route.fulfill({ json: { items: [], total: 0, has_more: false, unread }, headers: { 'access-control-allow-origin': base, 'access-control-allow-credentials': 'true' } }))
  for (const width of [390, 320, 768]) {
    await page.setViewportSize({ width, height: 844 })
    await expect(page.getByText('教材关注与上新', { exact: true })).toHaveCount(0)
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), '个人中心不应横向溢出')
    await page.screenshot({ path: path.join(output, 'account-' + width + '.png'), fullPage: true })
    for (const count of [1, 99, 100]) {
      unread = count
      await page.reload()
      const badge = page.locator('.unread-badge')
      await expect(badge).toHaveText(count > 99 ? '99+' : String(count))
      await badge.scrollIntoViewIfNeeded()
      const geometry = await badge.evaluate(element => {
        const r = element.getBoundingClientRect(), button = element.closest('uni-button').getBoundingClientRect()
        const x = (r.left + r.right) / 2, y = (r.top + r.bottom) / 2
        const points = [[x,y], [r.left+4,y], [r.right-4,y], [x,r.top+4], [x,r.bottom-4]]
        return {
          contained: r.left >= button.left && r.right <= button.right && r.top >= button.top && r.bottom <= button.bottom,
          uncovered: points.every(([px,py]) => element.contains(document.elementFromPoint(px,py))),
        }
      })
      assert.ok(geometry.contained, `${width}px / ${count} 未读角标必须完整位于按钮内部`)
      assert.ok(geometry.uncovered, `${width}px / ${count} 未读角标不应被覆盖`)
      await page.screenshot({ path: path.join(output, `badge-${width}-${count}.png`), fullPage: true })
    }
  }
  await page.unroute('**/api/v1/mini/messages?*')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(base + '/#/pages/library/index')
  await expect(page.locator('.search-field input').first()).toBeVisible()
  await page.locator('.search-field input').first().fill('十以内')
  await page.locator('.search-submit').first().click()
  await expect(page.getByText('十以内加法同步资料', { exact: true })).toBeVisible()
  await page.screenshot({ path: path.join(output, 'library-search.png'), fullPage: true })
  await page.goto(base + '/#/subpages/privacy/index?kind=privacy')
  await expect(page.locator('.legal-title')).toBeVisible()
  await expect(page.getByText(/教材关注/)).toHaveCount(0)
  const guest = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
  try {
    await guest.route('**/*', localRequests)
    const guestPage = await guest.newPage()
    guestPage.on('pageerror', e => errors.push(e.message))
    for (const width of [390, 320]) {
      await guestPage.setViewportSize({ width, height: 844 })
      await guestPage.goto(base + '/#/pages/account/index')
      await expect(guestPage.locator('.guest-services')).toBeVisible()
      await expect(guestPage.getByText('教材关注与上新', { exact: true })).toHaveCount(0)
      assert.ok(await guestPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      await guestPage.screenshot({ path: path.join(output, 'account-guest-' + width + '.png'), fullPage: true })
    }
  } finally { await guest.close() }
  assert.deepEqual(errors, [])
  console.log('PASS 教材关注下线：旧接口410、登录与访客入口移除、习题库搜索、隐私正文、消息角标与390/320/768宽度')
} catch (cause) {
  await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true })
  throw cause
} finally {
  await context.close(); await api.dispose(); await browser.close()
}
