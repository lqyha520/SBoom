import { expect, test, type BrowserContext } from '@playwright/test'

async function api(context: BrowserContext) {
  let status = 200, owner = 1
  const writes: Record<string, unknown>[] = []
  const documents = ['agreement', 'privacy'].map(key => ({ key, title: key === 'agreement' ? '用户协议' : '隐私政策', body: '原正文', revision: 1, updated_at: 1 }))
  await context.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (path === '/api/v1/auth/me' || path === '/api/v1/auth/login') { await route.fulfill({ json: { id: owner, username: 'admin', role: 'admin' } }); return }
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
  await page.getByPlaceholder('输入用户名').fill('admin')
  await page.getByPlaceholder('输入密码').fill('password123')
  server.status(200)
  await page.getByRole('button', { name: '登录管理后台' }).click()
  await expect(page.getByRole('heading', { name: '重新验证管理员身份' })).toBeHidden()
  await expect(page.locator('#doc-body')).toHaveValue('保留的协议草稿')
  expect(server.writes).toHaveLength(1)
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('用户协议已保存，小程序端立即生效')).toBeVisible()
  expect(server.writes).toHaveLength(2)
})

test('重认证使用另一账号会销毁旧账号工作区', async ({ context, page }) => {
  const server = await api(context)
  await page.goto('/admin/#documents')
  await page.locator('#doc-body').fill('不能传给其他账号的草稿')
  server.status(401)
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await page.getByPlaceholder('输入用户名').fill('other-admin')
  await page.getByPlaceholder('输入密码').fill('password123')
  server.owner(2); server.status(200)
  await page.getByRole('button', { name: '登录管理后台' }).click()
  await expect(page.locator('#doc-body')).toHaveValue('原正文')
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
