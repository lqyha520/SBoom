/** Run against profile_ui_fixture.py. Supply Playwright via NODE_PATH if needed. */
const assert = require('node:assert/strict')
const { mkdir, writeFile, stat } = require('node:fs/promises')
const path = require('node:path')
const { randomBytes } = require('node:crypto')
const { createRequire } = require('node:module')
const { chromium, request } = require('playwright')
const sharp = createRequire(path.resolve(__dirname, '../miniprogram/package.json'))('sharp')

const base = process.env.PROFILE_UI_BASE || 'http://127.0.0.1:8349'
const output = path.resolve(__dirname, '../artifacts/profile-membership')
const shots = []
const checks = []
const check = (name, result = true) => { assert.ok(result, name); checks.push(name); console.log('PASS ' + name) }
const settle = page => page.waitForLoadState('networkidle')
async function screenshot(page, name) {
  const file = path.join(output, name + '.png')
  await page.waitForTimeout(450) // Wot bottom-sheet transition before visual capture.
  await page.screenshot({ path: file, fullPage: false })
  shots.push(file)
}
async function noOverflow(page) {
  const sizes = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, screen: innerWidth }))
  assert.ok(sizes.content <= sizes.screen + 1, JSON.stringify(sizes))
}
async function visibleAvatar(page, container, source) {
  const ready = await page.waitForFunction(({ container, source }) => {
    const frame = document.querySelector(container)
    const image = frame?.querySelector('.photo img')
    if (!image?.complete || !image.naturalWidth || !image.src.includes(source)) return false
    const bounds = image.getBoundingClientRect(), outer = frame.getBoundingClientRect()
    return bounds.width >= 48 && bounds.height >= 48 && bounds.width <= outer.width && bounds.height <= outer.height
  }, { container, source }, { timeout: 8000 })
  await ready.dispose()
  return true
}

async function main() {
  assert.ok(['127.0.0.1', 'localhost'].includes(new URL(base).hostname), 'Only local disposable fixtures are supported')
  await mkdir(output, { recursive: true })
  const api = await request.newContext({ baseURL: base })
  const health = await (await api.get('/health')).json()
  assert.equal(health.fixture, true, 'Never seed or modify a real user database')
  const login = await (await api.post('/api/v1/mini/login-password', { data: { username: 'ui_reader', password: 'reader-pass-123' } })).json()
  assert.ok(login.token)
  assert.equal((await api.put('/api/v1/mini/me', { headers: { Authorization: 'Bearer ' + login.token }, data: { nickname: '小海豚', avatar: 'fox' } })).status(), 200)
  assert.equal((await api.post('/api/v1/auth/login', { data: { username: 'admin_console', password: 'admin-pass-123' } })).status(), 200)
  const accounts = await (await api.get('/api/v1/admin/mini-users', { params: { q: 'ui_reader' } })).json()
  const reader = accounts.items.find(item => item.id === login.user.id)
  assert.equal((await api.put('/api/v1/admin/mini-users/' + reader.id, { data: { revision: reader.revision, membership: 'regular', vip_expires_at: null, is_active: true } })).status(), 200)
  const browser = await chromium.launch({ headless: true, channel: 'chrome' })
  const context = await browser.newContext({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true, permissions: ['clipboard-read', 'clipboard-write'] })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  let orderPosts = 0
  page.on('request', req => { if (req.method() === 'POST' && new URL(req.url()).pathname === '/api/v1/mini/orders') orderPosts++ })
  try {
    await page.goto(base + '/#/pages/login/index?returnTo=%2Fpages%2Faccount%2Findex')
    await page.getByRole('checkbox', { name: '已阅读并同意用户协议和隐私政策' }).click()
    await page.locator('.login-primary').click()
    await page.locator('.account-login-sheet .login-form input').nth(0).fill('ui_reader')
    await page.locator('.account-login-sheet .login-form input').nth(1).fill('reader-pass-123')
    await page.locator('.account-login-sheet').getByRole('button', { name: '登录', exact: true }).click()
    await page.waitForURL('**/#/pages/account/index'); await settle(page)
    await page.locator('.profile-name').filter({ hasText: '小海豚' }).waitFor()
    check('Profile is at the top with no page title or settings button',
      (await page.locator('.identity-card').boundingBox()).y < 45 && await page.locator('.profile-hero .hero-title, .profile-hero .settings-button').count() === 0)
    await noOverflow(page); await screenshot(page, '01-account-375')
    await page.setViewportSize({ width: 320, height: 640 }); await noOverflow(page); await screenshot(page, '02-account-320')
    await page.setViewportSize({ width: 375, height: 812 })
    await page.getByRole('button', { name: '编辑个人资料', exact: true }).click()
    await page.getByRole('dialog', { name: '编辑资料', exact: true }).waitFor()
    check('Exactly five local default avatars are available', await page.locator('.preset-option').count() === 5)
    for (const [label, image] of [['小狐狸', 'fox.png'], ['小熊猫', 'panda.png'], ['小企鹅', 'penguin.png'], ['小鹿', 'deer.png'], ['小兔子', 'rabbit.png']]) {
      const choice = page.getByRole('radio', { name: label, exact: true })
      await choice.click()
      assert.equal(await choice.getAttribute('aria-checked'), 'true')
      await visibleAvatar(page, '.profile-preview', image)
    }
    await screenshot(page, '03-edit-profile-375')
    if (process.argv.includes('--capture-only')) {
      await page.getByRole('button', { name: '关闭编辑资料', exact: true }).click()
      await page.getByRole('button', { name: '查看会员服务', exact: true }).click()
      await page.locator('.plan-card').nth(2).waitFor(); await settle(page)
      await screenshot(page, '04-membership-375')
      await page.setViewportSize({ width: 320, height: 640 }); await noOverflow(page); await screenshot(page, '05-membership-320')
      await page.setViewportSize({ width: 375, height: 812 })
      await page.getByRole('button', { name: '联系客服咨询会员', exact: true }).click()
      await page.getByRole('dialog', { name: '会员客服', exact: true }).waitFor()
      await screenshot(page, '06-member-support-375')
      return
    }
    const presetResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/mini/me') && response.request().method() === 'PUT')
    await page.getByRole('button', { name: '保存资料', exact: true }).click()
    const preset = await (await presetResponse).json()
    check('The selected default avatar is saved without changing the login account', preset.avatar === 'rabbit' && preset.username === login.user.username)
    await page.locator('.profile-sheet').waitFor({ state: 'hidden' })
    await page.reload(); await settle(page)
    check('A saved default avatar survives reload and is visibly rendered', await visibleAvatar(page, '.avatar', 'rabbit.png'))

    const upload = path.join(output, 'large-selected-photo.png')
    await sharp(randomBytes(4200 * 900 * 3), { raw: { width: 4200, height: 900, channels: 3 } }).png().toFile(upload)
    assert.ok((await stat(upload)).size > 2 * 1024 * 1024)
    await page.getByRole('button', { name: '编辑个人资料', exact: true }).click()
    const [chooser] = await Promise.all([page.waitForEvent('filechooser'), page.locator('.choose-avatar').click()])
    await chooser.setFiles(upload)
    await page.locator('.nickname-field input').fill('向阳小鹿')
    const failUpload = route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: { error: '头像保存暂时失败，请重试' } }) })
    await page.route('**/api/v1/mini/me/avatar', failUpload)
    await page.getByRole('button', { name: '保存资料', exact: true }).click()
    await page.locator('.profile-sheet .error-strip').filter({ hasText: '请重试' }).waitFor()
    check('An upload failure retains the editable photo draft for retry', await page.locator('.profile-preview .photo img').getAttribute('src').then(src => src.startsWith('data:image/jpeg')))
    await page.unroute('**/api/v1/mini/me/avatar', failUpload)
    const uploadResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/mini/me/avatar') && response.request().method() === 'POST')
    await page.getByRole('button', { name: '保存资料', exact: true }).click()
    const response = await uploadResponse
    assert.equal(response.status(), 200)
    const photo = await response.json()
    check('A photo over 2 MB and 4096 px is resized, uploaded and saved with its nickname', photo.avatar.startsWith('photo:') && photo.nickname === '向阳小鹿')
    const encoded = response.request().postDataJSON().image
    assert.ok(Buffer.from(encoded, 'base64').length < 2 * 1024 * 1024)
    await page.locator('.profile-sheet').waitFor({ state: 'hidden' })
    await page.reload(); await settle(page)
    check('The uploaded photo survives reload and visibly loads with authentication', await visibleAvatar(page, '.avatar', 'blob:'))

    await page.getByRole('button', { name: '查看会员服务', exact: true }).click(); await settle(page)
    await page.locator('.plan-card').first().waitFor()
    const contactBox = await page.locator('.contact-entry').boundingBox()
    check('Customer support is visible on the first membership screen', contactBox.y > 0 && contactBox.y + contactBox.height < 600)
    check('All three plans appear without repeated benefit lists', await page.locator('.plan-card').count() === 3)
    await screenshot(page, '04-membership-375')
    await page.setViewportSize({ width: 320, height: 640 }); await noOverflow(page); await screenshot(page, '05-membership-320')
    await page.setViewportSize({ width: 375, height: 812 })
    await page.locator('.plan-card').nth(1).click()
    check('Selecting a plan updates the choice without creating an order', await page.locator('.plan-card').nth(1).getAttribute('aria-checked') === 'true' && orderPosts === 0)
    await page.getByRole('button', { name: '咨询开通', exact: true }).click()
    await page.getByRole('dialog', { name: '会员客服', exact: true }).waitFor()
    check('Unsupported online checkout opens real support actions', await page.getByRole('button', { name: '复制客服微信', exact: true }).isVisible() && orderPosts === 0)
    await screenshot(page, '06-member-support-375')
    await page.getByRole('button', { name: '复制客服微信', exact: true }).click()
    check('Support WeChat can be copied', await page.evaluate(() => navigator.clipboard.readText()) === 'learn_coach_demo')
    check('Phone support is available as a direct action', await page.getByRole('button', { name: '拨打客服电话', exact: true }).isVisible())
    await page.getByRole('button', { name: '关闭会员客服', exact: true }).click()

    await page.locator('.redeem-box input').fill('NOT-A-VALID-CARD')
    await page.getByRole('button', { name: '兑换会员卡密', exact: true }).click()
    await page.locator('.redeem-error').waitFor()
    check('An invalid card shows an inline error and preserves the input', await page.locator('.redeem-box input').inputValue() === 'NOT-A-VALID-CARD')
    const cardResult = await api.post('/api/v1/admin/commerce/cards', { data: { days: 30, quantity: 1 } })
    assert.equal(cardResult.status(), 201)
    const card = (await cardResult.json()).items[0].code
    await page.locator('.redeem-box input').fill(card)
    await page.getByRole('button', { name: '兑换会员卡密', exact: true }).click()
    await page.locator('.redeem-success').waitFor()
    check('Successful redemption updates membership and shows the new expiry', (await page.locator('.redeem-success').innerText()).includes('30 天') && (await page.locator('.member-title').innerText()) === 'VIP 会员')
    await page.reload(); await settle(page)
    assert.equal(await page.locator('.member-title').innerText(), 'VIP 会员')

    const noSupport = route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ revision: 0, wechat: '', phone: '', email: '', hours: '', benefits: '' }) })
    await page.route('**/api/v1/site/support', noSupport)
    await page.reload(); await settle(page)
    await page.getByRole('button', { name: '联系客服咨询会员', exact: true }).click()
    await page.getByRole('button', { name: '留言咨询', exact: true }).click()
    await page.waitForURL('**/#/pages/support/index?kind=membership')
    check('Missing contact channels fall back to membership feedback, with no dead button')
    await page.unroute('**/api/v1/site/support', noSupport)

    const brokenSupport = route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: { error: '暂时不可用' } }) })
    await page.route('**/api/v1/site/support', brokenSupport)
    await page.goto(base + '/#/pages/membership/index'); await settle(page)
    await page.locator('.plan-card').nth(2).waitFor()
    check('A contact load failure does not hide membership plans', await page.locator('.plan-card').count() === 3)
    await page.getByRole('button', { name: '联系客服', exact: true }).click()
    await page.getByText('联系方式暂时没加载成功，可以重试或留言咨询。', { exact: true }).waitFor()
    await page.unroute('**/api/v1/site/support', brokenSupport)
    await page.getByRole('button', { name: '重新加载', exact: true }).click()
    await page.getByRole('button', { name: '复制客服微信', exact: true }).waitFor()
    check('Customer support can recover after a failed load')
    await page.getByRole('button', { name: '关闭会员客服', exact: true }).click()

    for (const account of ['ui_lifetime', 'ui_expired']) {
      const member = await (await api.post('/api/v1/mini/login-password', { data: { username: account, password: 'reader-pass-123' } })).json()
      await page.evaluate(token => localStorage.setItem('lc-consumer-session-v2', token), member.token)
      await page.reload(); await settle(page)
      if (account === 'ui_lifetime') check('Lifetime members cannot accidentally redeem or buy another term', await page.locator('.redeem-box').count() === 0 && await page.getByRole('button', { name: '去挑选习题', exact: true }).isVisible())
      else check('Expired members see their real state and can renew', (await page.locator('.member-status').innerText()) === '会员已到期' && await page.locator('.redeem-box').isVisible())
    }
    check('No page JavaScript errors', errors.length === 0)
    await writeFile(path.join(output, 'checks.json'), JSON.stringify({ checks, screenshots: shots }, null, 2))
  } catch (error) {
    await screenshot(page, 'failure')
    await writeFile(path.join(output, 'failure.txt'), await page.locator('body').innerText())
    throw error
  } finally { await context.close(); await browser.close(); await api.dispose() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
