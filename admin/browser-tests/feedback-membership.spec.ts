import { test, expect } from '@playwright/test'
for (const width of [1440, 390]) test(`会员身份与回复流程 ${width}px`, async ({ page, context }, info) => {
  await page.setViewportSize({ width, height: 1000 })
  const errors: string[] = [], writes: Record<string, unknown>[] = []
  page.on('pageerror', error => errors.push(String(error)))
  const identities = [
    { id: 'regular', nickname: '普通读者', membership: 'regular', is_vip: false, membership_status: 'regular', vip_expires_at: null },
    { id: 'vip', nickname: '有效会员', membership: 'vip', is_vip: true, membership_status: 'active', vip_expires_at: 2000000000 },
    { id: 'lifetime', nickname: '长期会员', membership: 'vip', is_vip: true, membership_status: 'active', vip_expires_at: null },
    { id: 'expired', nickname: '到期读者', membership: 'vip', is_vip: false, membership_status: 'expired', vip_expires_at: 1 },
  ]
  const items = identities.map(item => ({ ...item, username: item.id, catalog_id: null, paper_title: '', kind: 'membership', body: '咨询会员开通流程',
    status: 'pending', reply: '', internal_note: '', revision: 1, updated_at: 1793770000 }))
  await context.route('**/api/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname
    let data
    if (path === '/api/v1/auth/me') data = { id: 1, username: 'admin', role: 'admin' }
    else if (path === '/api/v1/admin/experience/support') data = { revision: 1, wechat: '', phone: '', email: '', hours: '', benefits: '' }
    else if (path === '/api/v1/admin/experience/feedback') data = { items, total: items.length }
    else if (path.startsWith('/api/v1/admin/experience/feedback/')) {
      data = items.find(item => path.endsWith('/' + item.id))
      if (!data) throw new Error('Unknown feedback: ' + path)
      if (req.method() === 'PUT') { const body = req.postDataJSON(); writes.push(body); Object.assign(data, body, { revision: data.revision + 1 }) }
    } else throw new Error('Unexpected request: ' + path)
    await route.fulfill({ json: data })
  })
  await page.goto('/admin/#supportCenter')
  await expect(page.getByRole('columnheader', { name: '当前身份' })).toBeVisible()
  for (const identity of identities) {
    const row = page.getByRole('row').filter({ has: page.getByRole('cell', { name: identity.nickname, exact: true }) })
    const label = identity.is_vip ? 'VIP 会员' : '普通用户'
    await expect(row.getByText(label, { exact: true })).toBeVisible()
    await expect(row.getByText('会员已到期', { exact: true })).toHaveCount(identity.id === 'expired' ? 1 : 0)
    await row.getByRole('button', { name: '处理与回复', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '处理小程序反馈', exact: true })
    await expect(dialog.getByText(label, { exact: true })).toBeVisible()
    await expect(dialog.getByText('会员已到期', { exact: true })).toHaveCount(identity.id === 'expired' ? 1 : 0)
    await dialog.getByRole('textbox', { name: '回复用户', exact: true }).fill('已收到反馈，我们会协助处理')
    if (identity.id === 'vip') await page.screenshot({ path: info.outputPath('membership-dialog.png') })
    await dialog.getByRole('button', { name: '保存处理结果', exact: true }).click()
    await expect(dialog).toBeHidden()
    await expect(row.getByText(label, { exact: true })).toBeVisible()
  }
  expect(writes).toHaveLength(4)
  for (const body of writes) expect(Object.keys(body).sort()).toEqual(['internal_note', 'reply', 'revision', 'status'])
  expect(errors).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('feedback-list.png') })
})
