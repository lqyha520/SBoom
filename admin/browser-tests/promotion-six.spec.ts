import { expect, test } from '@playwright/test'
import { businessFixture } from './promotion-business-fixtures'

test('付款预检阻止已占用与缺资料单据，所选金额可重新核对', async ({ page, context }) => {
  const server = await businessFixture(context)
  const item = server.statements[0]!
  await context.route('**/api/v1/admin/settlements/payout-candidates?**', route => route.fulfill({ json: { page: 1, total: 3, items: [
    { ...item, payout_issues: [] }, { ...item, id: 'occupied', batch_id: 'another-batch', payout_issues: ['已加入付款批次：原付款批次'] }, { ...item, id: 'missing', payout_issues: ['尚未留存本单收款资料'] },
  ] } }))
  await page.goto('/admin/#financePayments')
  await page.getByText('选择待付款结算单，创建批次', { exact: true }).click()
  await expect(page.getByRole('checkbox', { name: '加入付款批次occupied' })).toBeDisabled()
  await expect(page.getByRole('checkbox', { name: '加入付款批次missing' })).toBeDisabled()
  await page.getByRole('textbox', { name: '付款批次名称' }).fill('预检批次')
  await page.getByRole('checkbox', { name: '加入付款批次' + item.id }).check()
  await expect(page.getByText('所选总金额：')).toContainText('¥10.00')
  await expect(page.getByRole('button', { name: '创建付款批次', exact: true })).toBeEnabled()
  item.status = 'paid'
  await page.getByRole('button', { name: '重新检查所选单据' }).click()
  await expect(page.getByRole('button', { name: '创建付款批次', exact: true })).toBeDisabled()
  await expect(page.getByText(/结算单不再是待付款状态/)).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await page.screenshot({ path: '../artifacts/promotion-six/payout-mobile.png', fullPage: true })
})

test('同周期对比可排序，保留前期与不完整成本说明，窄屏可读', async ({ page, context }) => {
  await businessFixture(context)
  const calls: string[] = []
  const metric = { cost_complete: false, spend_fen: 1000, paying_users: 2, paid_fen: 4000, refunded_fen: 0, net_fen: 4000, refund_rate_bps: 0, cost_per_payer_fen: null }
  await context.route('**/api/v1/admin/referrals/comparison?**', route => {
    calls.push(route.request().url())
    return route.fulfill({ json: { items: [{ ...metric, id: 'campaign-1', name: '活动甲', source: '微信群', admin_id: 1, admin_name: '管理员', previous: { ...metric, paying_users: 1 } }], total: 1, page: 1, start_date: '2026-10-01', end_date: '2026-10-31', previous_start: '2026-08-31', previous_end: '2026-09-30', as_of: 1794300000 } })
  })
  await page.goto('/admin/#referrals')
  await page.getByText('同周期活动对比', { exact: true }).click()
  await expect(page.getByText(/前期 2026-08-31 至 2026-09-30/)).toBeVisible()
  await expect(page.getByText('累计成本或历史投入日期未补齐', { exact: true })).toBeVisible()
  await page.getByRole('combobox', { name: '排序指标' }).click()
  await page.getByRole('option', { name: '每位付费用户投入', exact: true }).click()
  await page.getByRole('button', { name: '查询活动对比' }).click()
  await expect.poll(() => calls.at(-1)).toContain('sort=cost_per_payer')
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await page.getByRole('region', { name: '同周期活动对比表' }).scrollIntoViewIfNeeded()
  await page.screenshot({ path: '../artifacts/promotion-six/comparison-mobile.png', fullPage: true })
})

test('原始凭据支持登记、查看分摊、上传附件及版本冲突保留输入', async ({ page, context }) => {
  await businessFixture(context)
  let saved = false, reject = false
  const item = { id: 'voucher-1', admin_id: 1, reference: 'FP-001', name: '推广发票', total_fen: 10000, evidence: '原始发票依据', revision: 1, expense_fen: 3000, deduction_fen: 2000, expense_remaining_fen: 7000, deduction_remaining_fen: 8000, count: 1, entries: [{ kind: 'expense', id: 'expense-1', amount_fen: 3000, source_ref: 'fp-001/广告' }], files: [] as { id: string; name: string; media_type: string; created_at: number }[] }
  await context.route('**/api/v1/admin/settlements/cost-vouchers**', route => {
    const req = route.request()
    if (req.method() === 'GET') return route.fulfill({ json: { items: saved ? [item] : [], total: saved ? 1 : 0, page: 1 } })
    if (req.url().includes('/files?')) { item.files.push({ id: 'file-1', name: 'invoice.pdf', media_type: 'application/pdf', created_at: 1 }); return route.fulfill({ json: { id: 'file-1' } }) }
    if (reject) return route.fulfill({ status: 409, json: { detail: { error: '凭据已更新，请刷新后核对再保存' } } })
    saved = true; Object.assign(item, req.postDataJSON()); return route.fulfill({ json: item })
  })
  await page.goto('/admin/#financeExpenses')
  await page.getByText('原始凭据、附件与分摊额度', { exact: true }).click()
  await page.getByRole('button', { name: '登记原始凭据', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '登记原始凭据' })
  await dialog.getByRole('textbox', { name: '原始凭据号（不含斜杠）' }).fill('FP-001')
  await dialog.getByRole('textbox', { name: '凭据名称' }).fill('推广发票')
  await dialog.getByRole('textbox', { name: '凭据总额（元）' }).fill('100.00')
  await dialog.getByRole('textbox', { name: '凭据依据或修改原因' }).fill('原始发票依据')
  await dialog.getByRole('button', { name: '保存原始凭据' }).click()
  await expect(dialog).toHaveCount(0)
  await page.getByRole('button', { name: '查看凭据分摊' }).click()
  await expect(page.getByText('¥30.00 / ¥70.00', { exact: true })).toBeVisible()
  await page.locator('input[type=file]').setInputFiles({ name: 'invoice.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n%%EOF') })
  await expect(page.getByRole('button', { name: '下载附件：invoice.pdf' })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await page.getByRole('button', { name: '下载附件：invoice.pdf' }).scrollIntoViewIfNeeded()
  await page.screenshot({ path: '../artifacts/promotion-six/voucher-mobile.png', fullPage: true })
  await page.getByRole('button', { name: '修改凭据', exact: true }).click()
  await page.getByRole('textbox', { name: '凭据总额（元）' }).fill('90.00'); reject = true
  await page.getByRole('button', { name: '保存原始凭据' }).click()
  await expect(page.getByRole('dialog').getByText('凭据已更新，请刷新后核对再保存')).toBeVisible()
  await expect(page.getByRole('textbox', { name: '凭据总额（元）' })).toHaveValue('90.00')
})

test('月末清单汇总缺口，账单办理链接携带所选日期', async ({ page, context }) => {
  await businessFixture(context)
  await context.route('**/api/v1/admin/commerce/plans', route => route.fulfill({ json: { items: [], checkout_enabled: false, configuration: { ready: false }, virtual_configuration: { ready: false } } }))
  await context.route('**/api/v1/admin/commerce/reconciliations?**', route => route.fulfill({ json: { items: [], total: 0 } }))
  await context.route('**/api/v1/admin/settlements/month-end?**', route => route.fulfill({ json: { month: '2026-10', month_end: '2026-10-31', ended: true, as_of: 1794300000,
    archives: { total: 1, page: 1, items: [{ admin_id: 1, admin_name: '推广管理员', closing_fen: 100 }] },
    bills: [{ day: '2026-10-15', reason: '未核对', differences: 0 }], costs: { total: 1, page: 1, items: [{ id: 'campaign-1', name: '活动甲', admin_id: 1, spend_fen: null, missing_evidence: 1 }] }, disputes: { total: 1, page: 1, items: [{ id: 'issue-1', title: '费用核对异议' }] },
  } }))
  await page.goto('/admin/#financeOverview')
  await page.getByText('月末核对清单', { exact: true }).click()
  await expect(page.getByRole('heading', { name: '月度账本待留档 · 1 位推广人' })).toBeVisible()
  await expect(page.getByText('费用核对异议', { exact: true })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await page.getByRole('heading', { name: '成本或原始附件待补齐 · 1 个活动' }).scrollIntoViewIfNeeded()
  await page.screenshot({ path: '../artifacts/promotion-six/close-mobile.png', fullPage: true })
  await page.getByRole('button', { name: '进入账单核对' }).click()
  await expect(page).toHaveURL(/day=2026-10-15/)
  await expect(page.getByLabel('账单日期')).toHaveValue('2026-10-15')
})
