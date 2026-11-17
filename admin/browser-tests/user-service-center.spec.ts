import { expect, test, type BrowserContext, type Page } from '@playwright/test'

test.use({ reducedMotion: 'reduce' })

async function fixture(context: BrowserContext) {
  const reads: { path: string; query: URLSearchParams }[] = [], writes: { path: string; body: Record<string, unknown> }[] = []
  const request = { id: 'request-one', title: '想要三年级口算资料', username: 'reader', nickname: '资料读者', grade: '三年级', subject: '数学',
    status: 'planned', reply: '', details: '希望包含答案', revision: 1, catalog_id: null, paper_title: null, updated_at: 1793770000 }
  const feedback = { id: 'mini-one', username: 'reader', nickname: '小程序读者', kind: 'download', body: '下载的资料打不开',
    catalog_id: null, paper_title: '三年级练习', status: 'pending', reply: '', internal_note: '', revision: 1, updated_at: 1793770000 }
  const support = { revision: 1, wechat: 'study-help', phone: '', email: '', hours: '工作日 9:00–18:00', benefits: '学习资料服务', qr_url: '' }
  await context.route('**/api/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname
    let data: unknown
    if (req.method() === 'GET') reads.push({ path, query: url.searchParams })
    else writes.push({ path, body: req.postDataJSON() })
    if (path === '/api/v1/auth/me') data = { id: 1, username: 'admin', role: 'admin', is_super_admin: true }
    else if (path === '/api/v1/admin/engagement/requests') data = { items: [request], total: 42, demand: [] }
    else if (path === '/api/v1/admin/engagement/requests/request-one' && req.method() === 'PUT') data = Object.assign(request, req.postDataJSON(), { revision: request.revision + 1 })
    else if (path === '/api/v1/admin/experience/feedback') data = { items: [feedback], total: 1 }
    else if (path === '/api/v1/admin/experience/feedback/mini-one' && req.method() === 'PUT') data = Object.assign(feedback, req.postDataJSON(), { revision: feedback.revision + 1 })
    else if (path === '/api/v1/admin/experience/support') {
      if (req.method() === 'PUT') Object.assign(support, req.postDataJSON(), { revision: support.revision + 1 })
      data = support
    } else if (path === '/api/v1/admin/feedbacks') data = { feedbacks: [{ id: 7, username: '出题教师', game_id: 'worksheet-seven', is_oob: true, comment: '题目超过三年级范围', created_at: '2026-11-04 10:00' }] }
    else throw new Error('用户服务测试出现未声明请求：' + req.method() + ' ' + path)
    await route.fulfill({ json: data })
  })
  return { reads, writes }
}

const serviceNav = (page: Page) => page.getByRole('navigation', { name: '用户服务功能', exact: true })
async function expectService(page: Page, label: string) {
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('用户服务中心')
  await expect(serviceNav(page).getByRole('button', { name: label, exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('region', { name: label, exact: true })).toBeVisible()
  await expect(page.getByRole('navigation', { name: '管理后台导航', includeHidden: true }).getByRole('button', { name: '用户服务中心', exact: true, includeHidden: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByLabel('选择管理页面')).toHaveValue('resourceRequests')
}

test('侧栏只有一个服务中心，页内切换和旧链接保留需求筛选', async ({ page, context }, info) => {
  const server = await fixture(context)
  await context.addInitScript(() => localStorage.setItem('lc-admin-favorites:1', JSON.stringify(['resourceRequests', 'supportCenter', 'feedback'])))
  await page.goto('/admin/#resourceRequests?status=planned&page=2')
  await expectService(page, '资料需求')
  await expect(page.getByText('想要三年级口算资料', { exact: true })).toBeVisible()
  expect([...new Set(server.reads.filter(item => item.path !== '/api/v1/auth/me').map(item => item.path))]).toEqual(['/api/v1/admin/engagement/requests'])
  expect(server.reads.at(-1)!.query.get('status')).toBe('planned')
  expect(server.reads.at(-1)!.query.get('offset')).toBe('20')
  const center = page.getByRole('region', { name: '用户服务中心', exact: true })
  await center.evaluate(element => { (element as HTMLElement).dataset.preserved = 'yes' })
  const sidebar = page.getByRole('navigation', { name: '管理后台导航' })
  await expect(sidebar.getByRole('button', { name: '用户服务中心', exact: true })).toHaveCount(1)
  for (const label of ['资料需求', '小程序服务与反馈', '出题用户反馈']) await expect(sidebar.getByRole('button', { name: label, exact: true })).toHaveCount(0)
  await expect(sidebar.getByRole('button', { name: '移出常用：用户服务中心', exact: true })).toHaveCount(1)
  await serviceNav(page).getByRole('button', { name: '小程序反馈', exact: true }).click()
  await expectService(page, '小程序反馈')
  await expect(page.getByText('下载的资料打不开', { exact: true })).toBeVisible()
  await expect(page.getByText('想要三年级口算资料', { exact: true })).toBeHidden()
  await expect(page.getByRole('tab', { name: '会员与联系设置', exact: true })).toHaveCount(0)
  await serviceNav(page).getByRole('button', { name: '出题质量反馈', exact: true }).click()
  await expectService(page, '出题质量反馈')
  await expect(page.getByText('题目超过三年级范围', { exact: true })).toBeVisible()
  await sidebar.getByRole('button', { name: '用户服务中心', exact: true }).click()
  await expectService(page, '出题质量反馈')
  await expect(center).toHaveAttribute('data-preserved', 'yes')
  await page.goBack(); await expectService(page, '小程序反馈')
  await page.goBack(); await expectService(page, '资料需求')
  await expect(page).toHaveURL(/#resourceRequests\?status=planned&page=2$/)
  await expect.poll(() => server.reads.filter(item => item.path.endsWith('/requests')).at(-1)!.query.get('offset')).toBe('20')
  await page.reload(); await expectService(page, '资料需求')
  await expect(page.getByText('想要三年级口算资料', { exact: true })).toBeVisible()
  await page.screenshot({ path: info.outputPath('service-center-desktop.png') })
  expect(server.writes).toEqual([])
})

for (const width of [320, 390]) {
  test(`手机导航和页内切换直达功能，快捷搜索可找到服务中心 ${width}px`, async ({ page, context }, info) => {
    await fixture(context); await page.setViewportSize({ width, height: 950 })
    await page.goto('/admin/#feedback')
    await expectService(page, '出题质量反馈')
    await expect(page.getByText('题目超过三年级范围', { exact: true })).toBeVisible()
    const nav = serviceNav(page)
    for (const label of ['资料需求', '小程序反馈', '出题质量反馈']) await expect(nav.getByRole('button', { name: label, exact: true })).toBeInViewport()
    await nav.getByRole('button', { name: '资料需求', exact: true }).click()
    await expectService(page, '资料需求'); await expect(page).toHaveURL(/#resourceRequests$/)
    await expect(page.getByLabel('选择管理页面').locator('option[value="supportCenter"], option[value="feedback"]')).toHaveCount(0)
    await nav.getByRole('button', { name: '小程序反馈', exact: true }).click()
    await expectService(page, '小程序反馈')
    await page.getByLabel('选择管理页面').selectOption('membershipContact')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('会员与联系设置')
    await expect(page.getByRole('textbox', { name: '客服微信号', exact: true })).toHaveValue('study-help')
    await expect(nav).toHaveCount(0)
    await page.getByLabel('选择管理页面').selectOption('resourceRequests')
    await expectService(page, '小程序反馈')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath('service-center-mobile.png') })
    await page.getByRole('button', { name: '搜索页面', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '快速导航', exact: true })
    await dialog.getByLabel('搜索管理页面', { exact: true }).fill('用户服务中心')
    await expect(dialog.getByRole('option')).toHaveCount(3)
    await dialog.getByLabel('搜索管理页面', { exact: true }).fill('出题质量')
    await dialog.getByRole('option', { name: /出题质量反馈/ }).click()
    await expectService(page, '出题质量反馈')
  })
}

test('会员与联系设置独立位于运营配置，切换页面保护未保存内容', async ({ page, context }) => {
  const server = await fixture(context)
  await page.goto('/admin/#membershipContact')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('会员与联系设置')
  await expect(page.locator('#nav-panel-operations').getByRole('button', { name: '会员与联系设置', exact: true })).toHaveAttribute('aria-current', 'page')
  expect([...new Set(server.reads.filter(item => item.path !== '/api/v1/auth/me').map(item => item.path))]).toEqual(['/api/v1/admin/experience/support'])
  const contact = page.getByRole('textbox', { name: '客服微信号', exact: true })
  await contact.fill('new-help-contact')
  const sidebar = page.getByRole('navigation', { name: '管理后台导航' })
  await sidebar.getByRole('button', { name: '用户服务', exact: true }).click()
  page.once('dialog', dialog => dialog.dismiss())
  await sidebar.getByRole('button', { name: '用户服务中心', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('会员与联系设置')
  await expect(contact).toHaveValue('new-help-contact')
  await expect(page).toHaveURL(/#membershipContact$/)
  await page.getByRole('button', { name: '保存服务信息', exact: true }).click()
  await expect(page.getByText('会员权益和联系方式已更新', { exact: true })).toBeVisible()
  await sidebar.getByRole('button', { name: '用户服务中心', exact: true }).click()
  await expectService(page, '资料需求')
  await serviceNav(page).getByRole('button', { name: '小程序反馈', exact: true }).click()
  await expectService(page, '小程序反馈')
  await sidebar.getByRole('button', { name: '会员与联系设置', exact: true }).click()
  await expect(contact).toHaveValue('new-help-contact')
  expect(server.writes).toEqual([{ path: '/api/v1/admin/experience/support', body: expect.objectContaining({ wechat: 'new-help-contact', revision: 1 }) }])
})

test('需求和小程序回复分别保存，浏览器返回被取消后保留未保存回复', async ({ page, context }) => {
  const server = await fixture(context)
  await page.goto('/admin/#resourceRequests')
  await page.getByRole('button', { name: '处理需求', exact: true }).click()
  let dialog = page.getByRole('dialog', { name: '处理资料需求', exact: true })
  await dialog.getByRole('textbox', { name: '回复用户', exact: true }).fill('明天补齐口算练习')
  await dialog.getByRole('button', { name: '保存处理结果', exact: true }).click()
  await expect(dialog).toBeHidden()
  await serviceNav(page).getByRole('button', { name: '小程序反馈', exact: true }).click()
  await page.getByRole('button', { name: '处理与回复', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '处理小程序反馈', exact: true })
  await dialog.getByRole('textbox', { name: '回复用户', exact: true }).fill('请更新阅读器后重试')
  page.once('dialog', prompt => prompt.dismiss())
  await page.goBack()
  await expect(page).toHaveURL(/#supportCenter$/)
  await expect(dialog.getByRole('textbox', { name: '回复用户', exact: true })).toHaveValue('请更新阅读器后重试')
  await dialog.getByRole('button', { name: '保存处理结果', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(server.writes).toEqual([
    { path: '/api/v1/admin/engagement/requests/request-one', body: expect.objectContaining({ reply: '明天补齐口算练习' }) },
    { path: '/api/v1/admin/experience/feedback/mini-one', body: expect.objectContaining({ reply: '请更新阅读器后重试' }) },
  ])
})
