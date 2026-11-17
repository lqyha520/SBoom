import { emptyConversion, promotionRules } from './promotion-fixtures'
import { expect, test, type BrowserContext } from '@playwright/test'
import type { Campaign } from '../src/referral-operations'
import type { Payee } from '../src/settlement-operations'

async function fixture(context: BrowserContext, superAdmin = true, unknownRewards = false) {
  const requests: string[] = [], writes: { path: string; body: Record<string, unknown> }[] = []
  const campaigns: Campaign[] = []
  let payee: Payee | null = null, imported = false
  const budget = { revision: 0, budget_fen: null as number | null, used_fen: unknownRewards ? 0 : 500, unknown: unknownRewards ? 2 : 0, reward_known: unknownRewards ? 0 : 1, reached: false }
  await context.route('**/api/v1/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname
    requests.push(req.method() + ' ' + path + url.search)
    const body = req.method() === 'GET' ? {} : req.postDataJSON() as Record<string, unknown>
    if (req.method() !== 'GET') writes.push({ path, body })
    if (path.endsWith('/rules')) return route.fulfill({ json: promotionRules })
    if (path.endsWith('/conversion')) return route.fulfill({ json: emptyConversion })
    if (path.endsWith('/acquisition')) return route.fulfill({ json: { visits: 0, started: 0, registered: 0, paid: 0, tracking_since: 1794300000, as_of: emptyConversion.as_of } })
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 1, username: '推广管理员', role: 'admin', is_super_admin: superAdmin, admin_permissions: { settlements: ['view', 'create', 'export'], referrals: ['view', 'create', 'export'] }, permissions_revision: 1 } })
    if (path.endsWith('/admins')) return route.fulfill({ json: { items: [{ id: 1, username: '推广管理员', is_active: 1 }] } })
    if (path.endsWith('/settlements/summary')) return route.fulfill({ json: { ...Object.fromEntries(['available', 'holding', 'exception', 'pending', 'reviewing', 'approved', 'paid'].map(key => [key, { count: 2, amount_fen: 500, unknown: 0 }])), overdue: 1 } })
    if (path.endsWith('/referrals/summary')) return route.fulfill({ json: { registrations: 2, orders: 3, paying_users: 2, paid_fen: 3000, refunded_fen: 0, net_fen: 3000, first_paid_fen: 2000, renewal_paid_fen: 1000, reward_reference_fen: 500 } })
    if (path.includes('/list/') || path.endsWith('/users') || path.endsWith('/orders')) return route.fulfill({ json: { items: [], total: 0 } })
    if (path.endsWith('/policy')) return route.fulfill({ json: { revision: 1, enabled: true, beneficiary: 'admin', rate_bps: 2000, hold_days: 7, shared_fees: [], channel_rates: { wechat: 60, virtual_android: 60, virtual_ios: 1500 } } })
    if (path.endsWith('/notices')) return route.fulfill({ json: { unread: 0, last_id: 0, items: [] } })
    if (path.endsWith('/payee')) {
      if (req.method() === 'PUT') payee = { ...body, account: '****' + String(body.account).slice(-4), revision: Number(body.revision) + 1 } as Payee
      return route.fulfill({ json: payee })
    }
    if (path.includes('/budget/')) {
      if (req.method() === 'PUT' && body.revision !== budget.revision) return route.fulfill({ status: 409, json: { detail: { error: '预算已变化，请刷新' } } })
      if (req.method() === 'PUT') Object.assign(budget, body, { revision: budget.revision + 1, reached: Number(body.budget_fen) <= budget.used_fen })
      return route.fulfill({ json: budget })
    }
    if (path.endsWith('/campaigns')) {
      if (req.method() === 'POST') campaigns.push({ ...body, id: 'campaign-one', code: 'a_' + 'a'.repeat(20), revision: 1, active: true, admin_name: '推广管理员', path: 'pages/home/index?ref=a_' + 'a'.repeat(20), registrations: 2, paying_users: 1, reward_fen: unknownRewards ? 0 : 500, unknown: unknownRewards ? 2 : 0, reward_known: unknownRewards ? 0 : 1, budget_reached: !unknownRewards } as Campaign)
      return route.fulfill({ json: req.method() === 'GET' ? { items: campaigns } : campaigns[0] })
    }
    if (path.endsWith('/campaigns/campaign-one')) { Object.assign(campaigns[0]!, body, { revision: campaigns[0]!.revision + 1 }); return route.fulfill({ json: campaigns[0] }) }
    if (path.endsWith('/campaigns/campaign-one/performance')) return route.fulfill({ json: { campaign: campaigns[0], income: { paid_fen: 3000, refunded_fen: 0, reward_reference_fen: 500 }, spend_fen: null, remainder_fen: null, return_bps: null, trend: [] } })
    if (path.endsWith('/export.xlsx')) return route.fulfill({ contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', body: 'download-fixture' })
    if (path.endsWith('/bills')) {
      if (req.method() === 'POST') { imported = true; return route.fulfill({ json: { id: 'bill-one', orders: 1, duplicate: false } }) }
      return route.fulfill({ json: { items: imported ? [{ id: 'bill-one', name: '渠道账单.csv', created_at: 1794300000, orders: 1 }] : [] } })
    }
    if (path.endsWith('/bills/bill-one')) return route.fulfill({ json: { items: [{ id: 1, order_id: 'order-finance', channel_label: '微信支付', amount_fen: 1990, channel_fee_fen: 15, refunded_fen: 0, check: { bill_row_id: 1, differences: [], fee_difference: false } }] } })
    return route.fulfill({ status: 403, json: { detail: { error: '未授权的测试请求' } } })
  })
  return { requests, writes, budget }
}

test('汇总卡片保留筛选条件，财务导出跟随列表范围', async ({ page, context }) => {
  const server = await fixture(context)
  await page.goto('/admin/#settlements?admin=1&channel=wechat&q=order-finance')
  await page.getByRole('button', { name: /待付款结算单 · 2/ }).click()
  await expect.poll(() => server.requests.some(value => value.includes('/list/statements?') && value.includes('status=approved') && value.includes('q=order-finance') && value.includes('channel=wechat'))).toBeTruthy()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出结算明细', exact: true }).click()
  expect((await download).suggestedFilename()).toBe('推广结算明细.xlsx')
  expect(server.requests.some(value => value.includes('/export.xlsx?kind=statements') && value.includes('status=approved') && value.includes('admin_id=1'))).toBeTruthy()
})

test('实际付款日期与超时待办筛选同步到列表、历史和导出', async ({ page, context }) => {
  const server = await fixture(context)
  await context.route('**/api/v1/admin/settlements/summary?**', route => route.fulfill({ json: {
    ...Object.fromEntries(['available', 'holding', 'exception', 'pending', 'reviewing', 'approved', 'paid'].map(key => [key, { count: 2, amount_fen: 500, unknown: 0 }])),
    stalled: 1, review_overdue: 1, payout_overdue: 1, overdue: 2,
  } }))
  await page.goto('/admin/#settlements?admin=1&q=order-finance')
  await page.getByRole('button', { name: '1 份申请超过审核目标', exact: true }).click()
  await expect.poll(() => server.requests.some(value => value.includes('/list/requests?') && value.includes('timing=review_overdue') && value.includes('q=order-finance'))).toBe(true)
  await expect(page.getByRole('combobox', { name: '处理时效' })).toContainText('超过审核目标')
  await page.getByRole('combobox', { name: '日期口径' }).click()
  await page.getByRole('option', { name: '按实际付款日期', exact: true }).click()
  await expect.poll(() => server.requests.some(value => value.includes('/list/requests?') && value.includes('date_basis=paid'))).toBe(true)
  await page.reload()
  await expect(page.getByRole('combobox', { name: '日期口径' })).toContainText('按实际付款日期')
  await expect(page.getByRole('combobox', { name: '处理时效' })).toContainText('超过审核目标')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出结算明细', exact: true }).click()
  await download
  expect(server.requests.some(value => value.includes('/export.xlsx?kind=requests') && value.includes('date_basis=paid') && value.includes('timing=review_overdue'))).toBe(true)
})

test('预算未保存时筛选仍保留输入，活动详情不把未知奖励显示成零', async ({ page, context }) => {
  await fixture(context, true, true)
  await page.goto('/admin/#referrals')
  await page.getByRole('tab', { name: '活动与推广码' }).click()
  await expect(page.getByText('本月参考奖励支出 待核对（2 笔） · 预算 未设置', { exact: true })).toBeVisible()
  await page.getByText('预算设置与说明', { exact: true }).click()
  const input = page.getByRole('textbox', { name: '管理员月度预算（元，留空关闭预警）' })
  await input.fill('88.00')
  await page.getByRole('button', { name: '筛选活动', exact: true }).click()
  await expect(input).toHaveValue('88.00')
  await expect(page.getByText('预算修改尚未保存，筛选和翻页会保留输入')).toBeVisible()
  await page.getByRole('button', { name: '新建推广活动', exact: true }).click()
  await page.getByRole('dialog').getByRole('textbox', { name: '活动名称' }).fill('未知费用活动')
  await page.getByRole('button', { name: '创建活动推广码', exact: true }).click()
  await expect(input).toHaveValue('88.00')
  await expect(page.getByRole('row').filter({ hasText: '未知费用活动' }).getByText('待核对（2 笔）', { exact: true })).toBeVisible()
  await context.route('**/api/v1/admin/referrals/campaigns/campaign-one/performance', route => route.fulfill({ json: {
    campaign: { id: 'campaign-one', admin_id: 1, admin_name: '推广管理员', name: '未知费用活动', source: '微信群' },
    income: { paid_fen: 1990, refunded_fen: 0, reward_reference_fen: 0, reward_unknown: 2, reward_known: 0 },
    spend_fen: null, remainder_fen: null, return_bps: null, trend: [],
  } }))
  await page.getByRole('button', { name: '活动详情', exact: true }).click()
  await expect(page.getByRole('dialog').getByText('待核对（2 笔）', { exact: true })).toBeVisible()
})

test('刷新恢复预算草稿，后台版本冲突不覆盖输入，重新载入与保存清除备份', async ({ page, context }) => {
  const server = await fixture(context)
  await page.goto('/admin/#referrals')
  await page.getByRole('tab', { name: '活动与推广码' }).click()
  await page.getByText('预算设置与说明', { exact: true }).click()
  const input = page.getByRole('textbox', { name: '管理员月度预算（元，留空关闭预警）' })
  await input.fill('88.00')
  Object.assign(server.budget, { revision: 1, budget_fen: 2000 })
  page.once('dialog', dialog => dialog.accept())
  await page.reload()
  await expect(page.getByText('已恢复本标签页尚未保存的预算草稿，保存后生效。')).toBeVisible()
  await expect(page.getByText(/后台预算已更新，当前草稿保留原版本/)).toBeVisible()
  await page.getByText('预算设置与说明', { exact: true }).click()
  await expect(input).toHaveValue('88.00')
  await page.getByRole('button', { name: '保存月度预算', exact: true }).click()
  await expect(page.getByText('预算已变化，请刷新', { exact: true })).toBeVisible()
  await expect(input).toHaveValue('88.00')
  expect(server.budget.budget_fen).toBe(2000)
  expect(server.writes.find(item => item.path.includes('/budget/'))?.body.revision).toBe(0)
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '重新载入预算', exact: true }).click()
  await expect(input).toHaveValue('20.00')
  await input.fill('99.00')
  await page.getByRole('button', { name: '保存月度预算', exact: true }).click()
  await expect(page.getByText('月度预算预警已保存', { exact: true })).toBeVisible()
  await page.reload()
  await page.getByText('预算设置与说明', { exact: true }).click()
  await expect(input).toHaveValue('99.00')
  await expect(page.getByText(/已恢复本标签页尚未保存/)).toHaveCount(0)
})

test('手机端保存收款资料后仅显示尾号，普通管理员无账单财务入口', async ({ page, context }) => {
  const server = await fixture(context, false)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/#settlements')
  await page.getByRole('tab', { name: '收款资料' }).click()
  await page.getByRole('textbox', { name: '收款人' }).fill('测试收款人')
  await page.getByRole('textbox', { name: '完整收款账号（修改时重新填写）' }).fill('6222000012345678')
  await page.getByRole('textbox', { name: '开户行' }).fill('测试银行')
  await page.getByRole('button', { name: '保存收款资料' }).click()
  await expect(page.getByText('我的收款资料 · 测试收款人 / ****5678')).toBeVisible()
  await expect(page.getByRole('textbox', { name: '完整收款账号（修改时重新填写）' })).toHaveValue('')
  expect(server.writes[0]?.body).toMatchObject({ revision: 0, account: '6222000012345678' })
  await expect(page.getByText('渠道账单辅助核对', { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
})

test('推广管理员首页聚焦三个状态，时效规则可展开，进度入口沿用筛选', async ({ page, context }) => {
  const server = await fixture(context, false)
  await page.goto('/admin/#settlements?channel=wechat')
  const overview = page.getByRole('region', { name: '我的推广结算' })
  await expect(overview.locator('.metric')).toHaveCount(3)
  await expect(overview.getByText('已核定待付 ¥5.00；其余申请金额待审核。')).toBeVisible()
  await expect(overview.getByText('已登记的实际付款，到账请核对收款账户')).toBeVisible()
  await page.getByRole('tab', { name: '奖励规则' }).click()
  await expect(page.getByText(/审核通过后 2 个自然日内安排付款/)).toBeVisible()
  await expect(page.getByRole('button', { name: '保存奖励规则' })).toHaveCount(0)
  expect(server.requests.some(value => value.includes('/policy'))).toBe(false)
  await page.getByRole('tab', { name: '我的收益' }).click()
  await overview.getByRole('button', { name: '待付款 2', exact: true }).click()
  await expect.poll(() => server.requests.some(value => value.includes('/list/statements?') && value.includes('status=approved') && value.includes('channel=wechat'))).toBe(true)
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await overview.screenshot({ path: '../artifacts/promotion-settlement-mobile.png' })
  expect(server.writes).toHaveLength(0)
})

test('未读提醒在页签显示数量，点击进度回到对应结算列表', async ({ page, context }) => {
  const server = await fixture(context, false)
  await context.route('**/api/v1/admin/settlements/notices**', route => route.fulfill({ json: { unread: 1, last_id: 0,
    items: [{ id: 1, kind: 'apply_settlement', target: 'application-one', created_at: 1794300000 }] } }))
  await page.goto('/admin/#settlements')
  await page.getByRole('tab', { name: /结算提醒.*1.*条未读/ }).click()
  await page.getByText('结算提醒 · 1 条未读', { exact: true }).click()
  await page.getByRole('button', { name: '提交结算申请', exact: true }).click()
  await expect(page.getByRole('tab', { name: '我的收益' })).toHaveAttribute('aria-selected', 'true')
  await expect.poll(() => server.requests.some(value => value.includes('/list/requests?') && value.includes('q=application-one'))).toBe(true)
})

test('活动创建修改和停用保留版本，活动筛选同步到统计与明细', async ({ page, context }) => {
  const server = await fixture(context)
  await page.goto('/admin/#referrals')
  await page.getByRole('tab', { name: '活动与推广码' }).click()
  await page.getByText('预算设置与说明', { exact: true }).click()
  await page.getByRole('textbox', { name: '管理员月度预算（元，留空关闭预警）' }).fill('5.00')
  await page.getByRole('button', { name: '保存月度预算' }).click()
  await expect(page.getByText('管理员本月奖励预算已达到，请检查推广投入')).toBeVisible()
  await page.getByRole('button', { name: '新建推广活动', exact: true }).click()
  await page.getByRole('dialog').getByRole('textbox', { name: '活动名称' }).fill('家长微信群')
  await page.getByRole('textbox', { name: '活动累计预算（元，留空关闭预警）' }).fill('10.00')
  await page.getByRole('button', { name: '创建活动推广码' }).click()
  await page.getByRole('button', { name: '更多操作' }).click()
  await page.getByRole('menuitem', { name: '修改活动' }).click()
  await page.getByRole('dialog').getByRole('textbox', { name: '活动名称' }).fill('周末家长群')
  await page.getByRole('button', { name: '保存活动修改' }).click()
  await expect(page.getByRole('cell', { name: /周末家长群 · 微信群/ })).toBeVisible()
  await page.getByRole('button', { name: '更多操作' }).click()
  await page.getByRole('menuitem', { name: '停用活动码' }).click()
  await expect(page.getByRole('dialog', { name: '停用活动推广码' })).toBeVisible()
  expect(server.writes).toHaveLength(3)
  await page.getByRole('dialog').getByRole('button', { name: '取消' }).click()
  expect(server.writes).toHaveLength(3)
  await page.getByRole('button', { name: '更多操作' }).click()
  await page.getByRole('menuitem', { name: '停用活动码' }).click()
  await page.getByRole('button', { name: '确认停用' }).click()
  await expect(page.getByText('已停用新注册入口')).toBeVisible()
  await expect(page.getByRole('button', { name: '下载活动码', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '活动详情', exact: true }).click()
  await page.getByRole('button', { name: '查看推广明细' }).click()
  await expect.poll(() => server.requests.filter(value => value.includes('campaign_id=campaign-one') && value.includes('date_basis=paid')).length).toBeGreaterThanOrEqual(2)
  expect(server.writes.filter(value => value.path.endsWith('/campaign-one')).map(value => value.body.revision)).toEqual([1, 2])
})

test('导入渠道账单展示核对结果，导入本身不确认订单费用', async ({ page, context }) => {
  const server = await fixture(context)
  await page.goto('/admin/#settlements')
  await page.goto('/admin/#financeBills')
  await page.locator('input[type=file]').setInputFiles({ name: '渠道账单.csv', mimeType: 'text/csv', buffer: Buffer.from('订单号,交易号,渠道,实收（元）,手续费（元）,退款（元）,交易日期\norder-finance,transaction,wechat,19.90,0.15,0,2026-11-11\n') })
  await page.getByRole('textbox', { name: '账单来源 / 核对依据' }).fill('渠道后台下载的已核对账单')
  await page.getByRole('button', { name: '导入并检查差异' }).click()
  await expect(page.getByText('已导入 1 笔账单')).toBeVisible()
  await expect(page.getByRole('cell', { name: '关键字段一致，可在申请中采用手续费' })).toBeVisible()
  expect(server.writes).toHaveLength(1)
  expect(server.writes[0]?.path).toBe('/api/v1/admin/settlements/bills')
})


test('推广筛选可一键重置，保留当前明细类型并同步地址和数据', async ({ page, context }) => {
  const server = await fixture(context)
  await page.goto('/admin/#referrals?section=records&mode=orders&admin=1&start=2026-10-01&end=2026-10-31&q=old-order&campaign=old-campaign')
  await expect(page.getByRole('textbox', { name: '搜索推广明细' })).toHaveValue('old-order')
  await page.getByRole('button', { name: '重置筛选', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '搜索推广明细' })).toHaveValue('')
  await expect(page.getByRole('tab', { name: '用户与订单', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('combobox', { name: '明细类型' })).toContainText('推广订单')
  await expect.poll(() => server.requests.filter(value => value.includes('/referrals/orders')).at(-1)).not.toContain('old-order')
  await expect(page).not.toHaveURL(/campaign=|start=|end=|q=/)
  await expect(page.getByRole('button', { name: '重置筛选', exact: true })).toHaveCount(0)
  expect(server.writes).toHaveLength(0)
})
