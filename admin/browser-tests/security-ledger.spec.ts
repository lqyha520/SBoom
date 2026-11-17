import { expect, test } from '@playwright/test'

test('生成审核旧书签回到概览且不请求已移除的接口', async ({ page }) => {
  const retiredCalls: string[] = []
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.includes('generation-reviews')) retiredCalls.push(path)
    if (path === '/api/v1/auth/me') return route.fulfill({ json: { id: 1, username: 'admin', role: 'admin', is_super_admin: true, admin_permissions: {}, permissions_revision: 1 } })
    if (path === '/api/v1/admin/stats') return route.fulfill({ json: { users: 1, activeUsers: 1, admins: 1, templates: 0, llmConfigured: 0, feedbacks: 0, feedbacksOob: 0, server: { model: '', encryption: '', version: '' } } })
    return route.fulfill({ json: { items: [] } })
  })
  await page.goto('/admin/#generationReview')
  await expect(page.getByRole('heading', { name: '待办与概览', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '生成结果审核', exact: true })).toHaveCount(0)
  expect(retiredCalls).toEqual([])
})

test('管理员可完成两步登录并管理自己的安全设置', async ({ page }) => {
  let authenticated = false, enabled = false
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    const user = { id: 1, username: 'admin', role: 'admin', is_super_admin: true, admin_permissions: {}, permissions_revision: 1 }
    if (path === '/api/v1/auth/me') return route.fulfill({ status: authenticated ? 200 : 401, json: authenticated ? user : { detail: { error: '请先登录' } } })
    if (path === '/api/v1/auth/login') return route.fulfill({ json: { mfa_required: true, challenge: 'test-challenge-1234567890', username: 'admin' } })
    if (path === '/api/v1/auth/mfa/verify') { authenticated = true; return route.fulfill({ json: user }) }
    if (path === '/api/v1/auth/mfa/status') return route.fulfill({ json: { enabled } })
    if (path === '/api/v1/auth/mfa/setup') return route.fulfill({ json: { secret: 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP', otpauth_url: 'otpauth://totp/LearnCoach%3Ademo?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=LearnCoach&algorithm=SHA1&digits=6&period=30' } })
    if (path === '/api/v1/auth/mfa/confirm') { enabled = true; return route.fulfill({ json: { enabled } }) }
    if (path === '/api/v1/admin/sessions') return route.fulfill({ json: { sessions: [{ id: 'current', created_at: 1794600000, last_seen_at: 1794600000, expires_at: 1799900000, revoked_at: 0, user_agent: 'Chrome / Windows', client_ip: '127.0.0.1', current: true }] } })
    return route.fulfill({ json: { items: [] } })
  })
  await page.goto('/admin/#accountSecurity')
  await page.getByPlaceholder('输入用户名').fill('admin')
  await page.getByPlaceholder('输入密码', { exact: true }).fill('fixture-password')
  await page.getByRole('button', { name: '登录管理后台', exact: true }).click()
  await page.getByPlaceholder('输入验证器中的 6 位验证码').fill('123456')
  await page.getByRole('button', { name: '验证并登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '我的账号安全' })).toBeVisible()
  await expect(page.getByRole('link', { name: '打开微软官方下载页面' })).toBeVisible()
  await page.getByRole('button', { name: '手机已准备好，生成二维码' }).click()
  const qr = page.getByRole('img', { name: '用手机验证器扫描此二维码，添加 LearnCoach 账号' })
  await expect(qr).toBeVisible()
  await expect(qr).toHaveJSProperty('naturalWidth', 240)
  await expect(page.getByLabel('设置密钥', { exact: true })).toBeHidden()
  await page.locator('summary').filter({ hasText: '无法扫码' }).click()
  await expect(page.getByLabel('设置密钥', { exact: true })).toHaveValue('JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP')
  await page.locator('summary').filter({ hasText: '无法扫码' }).click()
  await page.screenshot({ path: '../artifacts/mfa-help-20261114/security-setup-demo.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(qr).toBeVisible()
  await expect(page.getByRole('button', { name: '验证并开启', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByPlaceholder('6 位验证码', { exact: true }).fill('123457')
  await page.getByRole('button', { name: '验证并开启' }).click()
  await expect(page.getByText('登录二次验证已开启。其他设备已退出，下次登录时请输入验证器中的 6 位验证码。')).toBeVisible()
  await expect(qr).toHaveCount(0)
  await expect(page.getByText('Chrome / Windows')).toBeVisible()
  await page.screenshot({ path: '../artifacts/p0-p1-completion-20261114/security.png', fullPage: true })
})

test('经营账本创建后刷新', async ({ page }) => {
  let entries: Record<string, unknown>[] = []
  let releaseSave!: () => void
  const saving = new Promise<void>(resolve => { releaseSave = resolve })
  await page.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (path === '/api/v1/auth/me') return route.fulfill({ json: { id: 1, username: 'admin', role: 'admin', is_super_admin: true, admin_permissions: {}, permissions_revision: 1 } })
    if (path === '/api/v1/admin/finance-ledger') {
      if (request.method() === 'POST') { await saving; entries = [{ ...request.postDataJSON(), id: 'ledger-one', status: 'active', revision: 1, created_at: 1, updated_at: 1 }]; return route.fulfill({ status: 201, json: entries[0] }) }
      return route.fulfill({ json: { items: entries, total: entries.length, page: 1, page_size: 30, summary: { income_fen: 0, expense_fen: entries.length ? 1234 : 0, net_fen: entries.length ? -1234 : 0, tax_fen: 0 } } })
    }
    return route.fulfill({ json: { items: [] } })
  })
  await page.goto('/admin/#financeLedger')
  await page.getByRole('button', { name: '新增收支', exact: true }).click()
  await page.getByPlaceholder('如会员收入、报销、服务费').fill('服务费')
  await page.getByLabel('含税金额（元）', { exact: true }).fill('12.34')
  await page.getByRole('button', { name: '保存记录', exact: true }).click()
  try {
    await expect(page.getByLabel('含税金额（元）', { exact: true })).toBeDisabled()
    await expect(page.getByPlaceholder('如会员收入、报销、服务费')).toBeDisabled()
    await expect(page.getByRole('button', { name: '取消', exact: true })).toBeDisabled()
  } finally { releaseSave() }
  await expect(page.getByText('账本记录已保存')).toBeVisible()
  await expect(page.getByRole('cell', { name: '服务费', exact: true })).toBeVisible()
  await page.screenshot({ path: '../artifacts/p0-p1-completion-20261114/ledger.png', fullPage: true })
})
