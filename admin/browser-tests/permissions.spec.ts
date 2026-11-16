import { expect, test, type BrowserContext } from '@playwright/test'

async function fixture(context: BrowserContext, superAdmin = false, initial: Record<string, string[]> = { categories: ['view', 'create'] }) {
  let grants = initial, revision = 1
  const writes: unknown[] = [], requests: string[] = []
  await context.route('**/api/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname
    requests.push(req.method() + ' ' + path)
    if (path === '/api/v1/auth/me') return route.fulfill({ json: { id: 1, username: superAdmin ? 'lqyha' : 'limited', role: 'admin', is_super_admin: superAdmin, admin_permissions: grants, permissions_revision: revision } })
    if (path === '/api/v1/admin/site/documents') return route.fulfill({ json: { items: [{ key: 'agreement', title: '用户协议', body: '协议正文', revision: 1, updated_at: 1 }] } })
    if (path === '/api/v1/admin/site/categories') return route.fulfill({ json: { items: [{ id: 'one', name: '数学', description: '', icon: '', sort_order: 0, is_visible: true, revision: 1, paper_count: 0 }] } })
    if (path === '/api/v1/admin/users') return route.fulfill({ json: { users: [{ id: 2, username: 'editor', role: 'admin', is_active: 1, is_super_admin: false, created_at: '', template_count: 0 }], total: 1, limit: 20, offset: 0 } })
    if (path === '/api/v1/admin/access/catalog') return route.fulfill({ json: { menus: [
      { id: 'papers', label: '公共习题', group: '内容资料', actions: ['view', 'create', 'update', 'delete', 'publish', 'export'], super_only: false },
      { id: 'adminAccounts', label: '管理员账号', group: '系统设置', actions: [], super_only: true },
    ], actions: { view: '查看', create: '新增', update: '修改', delete: '删除', publish: '发布', export: '导出/下载' } } })
    if (path === '/api/v1/admin/access/users/2') {
      if (req.method() === 'PUT') { writes.push(req.postDataJSON()); return route.fulfill({ json: {} }) }
      return route.fulfill({ json: { admin_permissions: {}, permissions_revision: 1 } })
    }
    return route.fulfill({ status: 403, json: { detail: { code: 'permission_denied', error: '未获授权' } } })
  })
  return { requests, writes, revoke: () => { grants = {}; revision++ } }
}

test('受限账号只看到授权菜单及新增按钮，直达其他菜单也被拦截', async ({ page, context }) => {
  const server = await fixture(context)
  await page.goto('/admin/#adminAccounts')
  await expect(page.getByRole('button', { name: '新建分类', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '编辑 数学', exact: true })).toBeHidden()
  await expect(page.getByRole('button', { name: '删除 数学', exact: true })).toBeHidden()
  await expect(page.locator('.admin-sidebar .nav-item')).toHaveCount(2)
  await expect(page.locator('.admin-sidebar .nav-item').filter({ hasText: '账号安全' })).toHaveCount(1)
  expect(server.requests).not.toContain('GET /api/v1/admin/users')
  await page.evaluate(() => { location.hash = 'llm' })
  await expect(page).toHaveURL(/#categories$/)
  await page.getByRole('button', { name: '新建分类', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  server.revoke()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page).toHaveURL(/#accountSecurity$/)
  await expect(page.getByRole('heading', { name: '我的账号安全' }).first()).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '管理员登录' })).toHaveCount(0)
})

test('超级管理员按按钮分配权限，新增自动包含查看', async ({ page, context }) => {
  const server = await fixture(context, true)
  await page.goto('/admin/#adminAccounts')
  await page.getByRole('button', { name: 'editor 的用户操作' }).click()
  await page.getByRole('menuitem', { name: '分配权限' }).click()
  const dialog = page.getByRole('dialog', { name: '分配权限 · editor' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('checkbox', { name: '公共习题：新增', exact: true }).check()
  await expect(dialog.getByRole('checkbox', { name: '公共习题：查看', exact: true })).toBeChecked()
  await expect(dialog.getByRole('checkbox', { name: '公共习题：修改', exact: true })).not.toBeChecked()
  await expect(dialog.getByRole('checkbox', { name: /管理员账号/ })).toHaveCount(0)
  await dialog.getByRole('button', { name: '保存权限', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  expect(server.writes).toEqual([{ revision: 1, permissions: { papers: ['view', 'create'] } }])
})


test('仅查看协议的账号可以阅读正文，不能编辑或保存', async ({ page, context }) => {
  const server = await fixture(context, false, { documents: ['view'] })
  await page.goto('/admin/#documents')
  await expect(page.locator('#doc-body')).toHaveValue('协议正文')
  await expect(page.locator('#doc-body')).toBeDisabled()
  await expect(page.getByRole('button', { name: '保存', exact: true })).toBeHidden()
  expect(server.requests.some(value => value.startsWith('PUT'))).toBe(false)
})

for (const superAdmin of [true, false]) {
  test(`公共习题显示${superAdmin ? '全部管理员范围和创建人' : '自己的资料范围'}`, async ({ page, context }) => {
    await fixture(context, superAdmin, { papers: ['view'] })
    await context.route('**/api/v1/admin/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/v1/admin/catalog/summary') return route.fulfill({ json: { total: 1, draft: 1, published: 0, withdrawn: 0, favorites: 0, downloads: 0 } })
      if (path === '/api/v1/admin/catalog/papers') return route.fulfill({ json: { items: [{
        id: 'owned', title: '管理员创建的习题', description: '', category: '', status: 'draft', revision: 1,
        featured: false, grade: '三年级', subject: '数学', version: 1, question_count: 3,
        page_count: 0, file_status: 'ready', thumbnail_url: null, updated_at: 1,
        publisher_id: 2, publisher_name: 'editor', download_mode: 'pdf',
        view_access: 'free', download_access: 'free', required_view: 'free', required_download: 'free',
      }], total: 1, has_more: false } })
      if (path.startsWith('/api/v1/admin/options/papers/') || path === '/api/v1/admin/site/dictionary') return route.fulfill({ json: { items: [] } })
      return route.fallback()
    })
    await page.goto('/admin/#papers')
    await expect(page.getByText(superAdmin ? /查看所有管理员创建的习题/ : /仅显示你创建的习题/)).toBeVisible()
    await expect(page.getByText('管理员创建的习题', { exact: true })).toBeVisible()
    if (superAdmin) await expect(page.getByText('创建人：editor', { exact: true })).toBeVisible()
    else await expect(page.getByText('创建人：editor', { exact: true })).toHaveCount(0)
  })
}
