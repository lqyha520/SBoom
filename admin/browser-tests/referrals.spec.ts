import { emptyConversion, promotionRules } from './promotion-fixtures'
import { test, expect, type BrowserContext } from '@playwright/test'

async function fixture(context: BrowserContext, superAdmin = false) {
  const requests: string[] = [], writes: unknown[] = []
  let source = 'legacy'
  await context.route('**/api/v1/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname
    if (path.endsWith('/rules')) return route.fulfill({ json: promotionRules })
    if (path.endsWith('/conversion')) return route.fulfill({ json: emptyConversion })
    if (path.endsWith('/campaigns')) return route.fulfill({ json: { items: [] } })
    if (path.includes('/budget/')) return route.fulfill({ json: { revision: 0, budget_fen: null, used_fen: 0, unknown: 0, reached: false } })
    requests.push(req.method() + ' ' + path + url.search)
    if (path === '/api/v1/auth/me') return route.fulfill({ json: { id: 1, username: superAdmin ? 'lqyha' : 'promoter-a', role: 'admin', is_super_admin: superAdmin, admin_permissions: { referrals: ['view'] }, permissions_revision: 1 } })
    if (path === '/api/v1/admin/referrals/admins') return route.fulfill({ json: { items: [{ id: 1, username: 'promoter-a', is_active: 1 }, ...(superAdmin ? [{ id: 2, username: 'promoter-b', is_active: 1 }] : [])] } })
    if (path === '/api/v1/admin/referrals/summary') return route.fulfill({ json: { registrations: 1, orders: 2, paying_users: 1, paid_fen: 3980, refunded_fen: 1990, net_fen: 1990 } })
    if (path === '/api/v1/admin/referrals/users') return route.fulfill({ json: { total: 1, items: [{ id: 'reader-1', username: 'wx12345', nickname: '小海豚', created_at: 1794300000, referral: { source, ...(source === 'manual' ? { admin_name: 'promoter-b', admin_id: 2 } : {}) } }] } })
    if (path === '/api/v1/admin/referrals/orders') return route.fulfill({ json: { total: 1, items: [{ id: 'order-1', username: 'wx12345', nickname: '小海豚', plan_name: '月会员', amount_fen: 1990, status: 'paid', created_at: 1794300000, referral: { source: 'admin', admin_id: 1, admin_name: 'promoter-a', inviter_name: 'promoter-a' } }] } })
    if (path === '/api/v1/admin/referrals/code') { writes.push(req.postDataJSON()); return route.fulfill({ json: { code: 'a_' + 'a'.repeat(20), admin_id: 1, admin_name: 'promoter-a', path: 'pages/home/index?ref=a_' + 'a'.repeat(20) } }) }
    if (path === '/api/v1/admin/referrals/users/reader-1/audit') return route.fulfill({ json: { items: source === 'manual' ? [{ id: 1, actor_name: 'lqyha', after_json: { source: 'manual', admin_name: 'promoter-b' }, reason: '核对历史登记表', created_at: 1794300000 }] : [] } })
    if (path === '/api/v1/admin/referrals/users/reader-1' && req.method() === 'PUT') { writes.push(req.postDataJSON()); source = 'manual'; return route.fulfill({ json: { source, admin_id: 2, admin_name: 'promoter-b' } }) }
    if (path === '/api/v1/admin/referrals/qrcode') return route.fulfill({ status: 502, json: { detail: { error: '微信小程序码生成失败，请核对所选版本是否已上传' } } })
    return route.fulfill({ status: 403, json: { detail: { code: 'permission_denied', error: '未获授权' } } })
  })
  return { requests, writes }
}

test('普通管理员只看到获授权的推广入口和账号安全，订单展示付款时归属', async ({ page, context }) => {
  await fixture(context)
  await page.goto('/admin/#referrals')
  await page.getByRole('tab', { name: '用户与订单' }).click()
  await expect(page.getByRole('cell', { name: '小海豚 wx12345', exact: true })).toBeVisible()
  await expect(page.locator('.admin-sidebar .nav-item')).toHaveText(['推广管理', '奖励规则', '我的账号安全'])
  await expect(page.locator('#nav-panel-finance')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '获取推广码', exact: true })).toBeHidden()
  await expect(page.getByRole('button', { name: '下载小程序码', exact: true })).toBeHidden()
  await expect(page.getByRole('button', { name: '导出 CSV', exact: true })).toBeHidden()
  await expect(page.getByRole('button', { name: '补录归属', exact: true })).toHaveCount(0)
  await expect(page.getByRole('combobox', { name: '归属管理员', exact: true })).toHaveCount(0)
  await page.getByRole('combobox', { name: '明细类型' }).click()
  await page.getByRole('option', { name: '推广订单' }).click()
  await expect(page.getByText('order-1', { exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '管理员推广 promoter-a', exact: true })).toBeVisible()
})

test('超级管理员获取专属码、补录历史用户并查看审计，生成失败可重试', async ({ page, context }) => {
  const server = await fixture(context, true)
  await page.goto('/admin/#referrals')
  await page.getByRole('tab', { name: '活动与推广码' }).click()
  await page.getByRole('button', { name: '获取推广码', exact: true }).click()
  await expect(page.getByText(/pages\/home\/index\?ref=a_/)).toBeVisible()
  await page.getByRole('button', { name: '下载小程序码', exact: true }).click()
  await expect(page.getByText('微信小程序码生成失败，请核对所选版本是否已上传')).toBeVisible()
  await page.getByRole('tab', { name: '用户与订单' }).click()
  await page.getByRole('button', { name: '补录归属', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('combobox').click()
  await page.getByRole('option', { name: 'promoter-b', exact: true }).click()
  await dialog.getByRole('textbox', { name: '补录原因' }).fill('核对历史登记表')
  await dialog.getByRole('button', { name: '确认补录', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('cell', { name: '人工补录 —', exact: true })).toBeVisible()
  expect(server.writes).toContainEqual({ admin_id: 2, reason: '核对历史登记表' })
  await page.getByRole('button', { name: '补录记录', exact: true }).click()
  await expect(page.getByRole('dialog').getByText('核对历史登记表')).toBeVisible()
  await expect(page.getByRole('button', { name: '确认补录', exact: true })).toHaveCount(0)
})

test('筛选管理员与日期同步到统计和明细，窄屏仍可查看', async ({ page, context }) => {
  const server = await fixture(context, true)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/#referrals?admin=2&start=2026-11-01&end=2026-11-10')
  await page.getByRole('tab', { name: '用户与订单' }).click()
  await expect(page.getByRole('cell', { name: '小海豚 wx12345', exact: true })).toBeVisible()
  expect(server.requests).toContain('GET /api/v1/admin/referrals/summary?admin_id=2&start_date=2026-11-01&end_date=2026-11-10&date_basis=paid')
  expect(server.requests).toContain('GET /api/v1/admin/referrals/users?admin_id=2&start_date=2026-11-01&end_date=2026-11-10&date_basis=paid&offset=0')
  await page.screenshot({ path: '../artifacts/referrals-mobile.png', fullPage: true })
})

test('同批注册漏斗可比较活动并进入明细，财务口径和关键词不改变分母', async ({ page, context }) => {
  const server = await fixture(context, true)
  const calls: URL[] = []
  const counts = { registrations: 4, ordered_users: 2, paying_users: 1, not_ordered_users: 2,
    unpaid_users: 1, order_rate_bps: 5000, pay_rate_bps: 2500, order_pay_rate_bps: 5000 }
  await context.route('**/api/v1/admin/referrals/conversion?**', route => {
    calls.push(new URL(route.request().url()))
    return route.fulfill({ json: { ...emptyConversion, summary: counts, total: 1,
      items: [{ ...counts, key: 'campaign:summer', campaign_id: 'summer', admin_id: '2',
        admin_name: 'promoter-b', name: '新用户体验活动', source: '小红书' }] } })
  })
  await page.goto('/admin/#referrals?section=overview&start=2026-11-01&end=2026-11-10&basis=created&q=小海豚')
  const funnel = page.getByRole('region', { name: '推广转化漏斗' })
  await expect(funnel.locator('.conversion-stages strong')).toHaveText(['4', '2', '1', '1'])
  await expect(funnel.getByText('注册→付费 25.00%', { exact: true })).toBeVisible()
  await expect(funnel.getByText(/下单→付费 50.00%/)).toBeVisible()
  expect(calls[0]!.searchParams.get('start_date')).toBe('2026-11-01')
  expect(calls[0]!.searchParams.get('end_date')).toBe('2026-11-10')
  expect(calls[0]!.searchParams.has('date_basis')).toBe(false)
  expect(calls[0]!.searchParams.has('q')).toBe(false)
  await page.locator('.admin-main').evaluate(element => { element.scrollTop = 0 })
  await page.screenshot({ path: '../artifacts/promotion-overview-redesign.png', animations: 'disabled' })
  await funnel.getByText('活动转化对比 · 1 个来源', { exact: true }).click()
  await funnel.screenshot({ path: '../artifacts/promotion-conversion-desktop.png' })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(await funnel.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
  expect(await funnel.evaluate(element => [...element.querySelectorAll('.conversion-stages strong')].every(value => value.getBoundingClientRect().right <= element.getBoundingClientRect().right))).toBe(true)
  await funnel.screenshot({ path: '../artifacts/promotion-conversion-mobile.png' })
  await funnel.getByRole('button', { name: '查看此活动' }).click()
  await expect(page.getByRole('tab', { name: '用户与订单' })).toHaveAttribute('aria-selected', 'true')
  await expect.poll(() => calls.at(-1)?.searchParams.get('campaign_id')).toBe('summer')
  expect(calls.at(-1)?.searchParams.get('admin_id')).toBe('2')
  expect(server.requests.some(value => value.includes('/users?') && value.includes('campaign_id=summer') && value.includes('admin_id=2'))).toBe(true)
})

test('推广规则可直接查看，漏斗故障可独立重试，零分母不显示虚假转化率', async ({ page, context }) => {
  await fixture(context)
  let fail = true
  await context.route('**/api/v1/admin/referrals/conversion?**', route => fail
    ? route.fulfill({ status: 503, json: { detail: { error: '转化统计暂不可用' } } })
    : route.fulfill({ json: emptyConversion }))
  await page.goto('/admin/#referrals')
  await page.getByRole('tab', { name: '奖励规则' }).click()
  const rules = page.getByLabel('邀请与奖励规则')
  await expect(rules.getByText('首付奖励 10% · 支付后等待 14 天 · 单笔奖励上限 ¥5.00')).toBeVisible()
  await expect(rules.getByText(/提交申请后 3 个自然日内/)).toBeVisible()
  await page.getByRole('tab', { name: '推广概览' }).click()
  const funnel = page.getByRole('region', { name: '推广转化漏斗' })
  await expect(funnel.getByRole('alert')).toContainText('转化统计暂不可用')
  await page.getByRole('tab', { name: '用户与订单' }).click()
  await expect(page.getByRole('cell', { name: '小海豚 wx12345', exact: true })).toBeVisible()
  await page.getByRole('tab', { name: '推广概览' }).click()
  fail = false
  await funnel.getByRole('button', { name: '刷新转化数据' }).click()
  await expect(funnel.getByText('注册→付费 —')).toBeVisible()
  await expect(funnel.getByText(/这段时间暂无注册用户/)).toBeVisible()
  await expect(page.getByRole('button', { name: '保存奖励规则' })).toHaveCount(0)
})

test('页面分区支持键盘、历史返回和刷新，概览不堆放配置或明细', async ({ page, context }) => {
  const server = await fixture(context, true)
  await page.goto('/admin/#referrals?start=2026-11-01')
  await expect(page.getByRole('tabpanel')).toHaveCount(1)
  await expect(page.getByRole('button', { name: '新建推广活动' })).toBeHidden()
  await expect(page.getByRole('combobox', { name: '明细类型' })).toBeHidden()
  await expect(page.getByLabel('邀请与奖励规则')).toBeHidden()
  const tab = page.getByRole('tab', { name: '推广概览' })
  await tab.focus(); await tab.press('ArrowRight')
  await expect(page.getByRole('tab', { name: '活动与推广码' })).toBeFocused()
  await expect(page.getByRole('button', { name: '新建推广活动' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '活动名称', exact: true })).toHaveCount(0)
  await page.getByRole('tab', { name: '用户与订单' }).click()
  await page.getByRole('textbox', { name: '搜索推广明细' }).fill('小海豚')
  await page.getByRole('button', { name: '搜索明细' }).click()
  await page.getByRole('tab', { name: '奖励规则' }).click()
  await page.goBack()
  await expect(page.getByRole('tab', { name: '用户与订单' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('textbox', { name: '搜索推广明细' })).toHaveValue('小海豚')
  await page.reload()
  await expect(page.getByRole('tab', { name: '用户与订单' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('textbox', { name: '起始日期' })).toHaveValue('2026-11-01')
  expect(server.writes).toHaveLength(0)
})
