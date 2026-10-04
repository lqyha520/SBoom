import { expect, test, type BrowserContext } from '@playwright/test'

async function api(context: BrowserContext) {
  let status = 200, owner = 1
  const writes: Record<string, unknown>[] = []
  const documents = ['agreement', 'privacy'].map(key => ({ key, title: key === 'agreement' ? '用户协议' : '隐私政策', body: '原正文', revision: 1, updated_at: 1 }))
  await context.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (path === '/api/v1/auth/me' || path === '/api/v1/auth/login') { await route.fulfill({ json: { id: owner, username: 'admin', role: 'admin' } }); return }
    if (path === '/api/v1/auth/logout') { await route.fulfill({ json: {} }); return }
    if (path === '/api/v1/admin/site/documents' && request.method() === 'GET') { await route.fulfill({ json: { items: documents } }); return }
    if (path.startsWith('/api/v1/admin/site/documents/') && request.method() === 'PUT') {
      const body = request.postDataJSON(); writes.push(body)
      if (status !== 200) { await route.fulfill({ status, json: { detail: { error: status === 401 ? '请重新验证身份' : '没有管理员权限', code: status === 401 ? 'reauth_required' : 'forbidden' } } }); return }
      const item = documents.find(item => path.endsWith(item.key))!
      Object.assign(item, body, { revision: item.revision + 1 })
      await route.fulfill({ json: item }); return
    }
    throw new Error('浏览器测试出现未声明请求：' + request.method() + ' ' + path)
  })
  return { writes, status: (value: number) => { status = value }, owner: (value: number) => { owner = value } }
}

for (const width of [1440, 320]) {
  test(`后台登录和管理页不再展示英文品牌 ${width}px`, async ({ page, context }, info) => {
    await api(context)
    await page.setViewportSize({ width, height: width === 320 ? 640 : 1000 })
    await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 401, json: {} }))
    await page.goto('/admin/#documents')
    await expect(page.getByRole('heading', { name: '管理员登录' })).toBeVisible()
    await expect(page.locator('.brand')).toHaveText('管理控制台')
    await expect(page.locator('body')).not.toContainText(/learning\s+coach/i)
    await expect(page.locator('.auth-footer, .brand-caption')).toHaveCount(0)
    await page.screenshot({ path: info.outputPath('admin-login.png') })
    await page.unroute('**/api/v1/auth/me')
    await page.reload()
    await expect(page.locator('#doc-body')).toBeVisible()
    await expect(page.locator('.brand')).toHaveText('管理控制台')
    await expect(page.locator('body')).not.toContainText(/learning\s+coach/i)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath('admin.png') })
  })
}

test('文档草稿在文档切换和401同账号重认证后仍可保存', async ({ context, page }) => {
  const server = await api(context)
  await page.goto('/admin/#documents')
  await page.locator('#doc-body').fill('保留的协议草稿')
  await page.getByRole('tab', { name: '隐私政策', exact: true }).click()
  await page.locator('#doc-body').fill('保留的隐私草稿')
  await page.getByRole('tab', { name: '用户协议', exact: true }).click()
  await expect(page.locator('#doc-body')).toHaveValue('保留的协议草稿')
  server.status(401)
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByRole('heading', { name: '重新验证管理员身份' })).toBeVisible()
  await expect(page.getByPlaceholder('输入用户名')).toHaveValue('admin')
  await expect(page.getByPlaceholder('输入用户名')).toHaveAttribute('readonly', '')
  await page.getByPlaceholder('输入密码').fill('password123')
  server.status(200)
  await page.getByRole('button', { name: '验证并继续' }).click()
  await expect(page.getByRole('heading', { name: '重新验证管理员身份' })).toBeHidden()
  await expect(page.locator('#doc-body')).toHaveValue('保留的协议草稿')
  expect(server.writes).toHaveLength(1)
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('用户协议已保存，小程序端立即生效')).toBeVisible()
  expect(server.writes).toHaveLength(2)
})

test('重认证不会接受不同账号，也不会丢弃原草稿', async ({ context, page }) => {
  const server = await api(context)
  await page.goto('/admin/#documents')
  await page.locator('#doc-body').fill('不能传给其他账号的草稿')
  server.status(401)
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByPlaceholder('输入用户名')).toHaveValue('admin')
  await page.getByPlaceholder('输入密码').fill('password123')
  server.owner(2); server.status(200)
  await page.getByRole('button', { name: '验证并继续' }).click()
  await expect(page.getByText('请使用原管理员账号验证，当前编辑尚未保存')).toBeVisible()
  await expect(page.locator('#doc-body')).toHaveValue('不能传给其他账号的草稿')
})

test('403 统一显示权限不足并停止后台操作', async ({ context, page }) => {
  const server = await api(context)
  await page.goto('/admin/#documents')
  await page.locator('#doc-body').fill('草稿')
  server.status(403)
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByRole('heading', { name: '当前账号没有管理员权限' })).toBeVisible()
  await expect(page.locator('#doc-body')).toHaveCount(0)
})

test('手机导航展示全部页面选择，活动页面无需横向寻找', async ({ context, page }) => {
  await api(context); await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/#documents')
  const select = page.getByLabel('选择管理页面')
  await expect(select).toBeVisible(); await expect(select).toHaveValue('documents')
  expect(await select.locator('option').count()).toBe(25)
  await expect(page.getByRole('navigation', { name: '管理后台导航' })).toBeHidden()
})

test('窄屏重验证表单紧凑且键盘焦点留在弹窗内', async ({ context, page }, info) => {
  const server = await api(context)
  await page.setViewportSize({ width: 320, height: 640 })
  await page.goto('/admin/#documents')
  await page.locator('#doc-body').fill('手机草稿')
  server.status(401)
  await page.getByRole('button', { name: '保存', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '重新验证管理员身份' })
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('.auth-page')).toHaveCount(0)
  await expect(dialog.getByRole('button', { name: '验证并继续' })).toBeInViewport()
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Tab')
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true)
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('reauth-320.png') })
})

test('反馈409可核对最新回复且不丢本地草稿', async ({ context, page }) => {
  await api(context)
  const item = { id: 'feedback', revision: 1, status: 'pending', kind: 'other', body: '请求协助', reply: '', internal_note: '', username: 'reader', updated_at: 1 }
  let conflict = true
  const writes: Record<string, unknown>[] = []
  await page.route('**/api/v1/admin/experience/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/support')) { await route.fulfill({ json: { revision: 0, wechat: '', phone: '', email: '', hours: '', benefits: '', qr_url: '' } }); return }
    if (route.request().method() === 'PUT') {
      writes.push(route.request().postDataJSON())
      if (conflict) {
        Object.assign(item, { revision: 2, reply: '另一位管理员的回复', internal_note: '已电话联系' })
        await route.fulfill({ status: 409, json: { detail: { error: '记录已更新' } } })
      } else await route.fulfill({ json: { ...item, ...route.request().postDataJSON(), revision: 3 } })
    } else await route.fulfill({ json: { items: [item], total: 1 } })
  })
  await page.goto('/admin/#supportCenter')
  await page.getByRole('button', { name: '处理与回复', exact: true }).click()
  await page.getByRole('textbox', { name: '回复用户', exact: true }).fill('我的未保存回复')
  page.once('dialog', dialog => dialog.dismiss())
  await page.getByRole('dialog', { name: '处理小程序反馈' }).getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '回复用户', exact: true })).toHaveValue('我的未保存回复')
  await page.getByRole('button', { name: '保存处理结果' }).click()
  await page.getByRole('button', { name: '载入最新并保留我的修改' }).click()
  await expect(page.getByText('另一位管理员的回复', { exact: true })).toBeVisible()
  await expect(page.getByText('已电话联系', { exact: true })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '回复用户', exact: true })).toHaveValue('我的未保存回复')
  conflict = false
  await page.getByRole('button', { name: '保存处理结果' }).click()
  await expect(page.getByRole('dialog', { name: '处理小程序反馈' })).toBeHidden()
  expect(writes.at(-1)).toMatchObject({ revision: 2, reply: '我的未保存回复' })
})
