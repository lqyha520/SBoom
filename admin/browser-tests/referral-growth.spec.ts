import { test, expect, type BrowserContext } from '@playwright/test'
import { emptyConversion, promotionRules } from './promotion-fixtures'

const campaign = { id: 'growth-demo', admin_id: 1, admin_name: 'lqyha', name: '秋季练习资料', source: '家长群',
  active: true, code: 'a_' + 'a'.repeat(20), revision: 1, path: 'pages/home/index?ref=a_' + 'a'.repeat(20),
  budget_fen: null, spend_fen: 1000, landing_kind: 'paper', landing_id: 'public-paper',
  registrations: 4, paying_users: 1, reward_fen: 100, unknown: 0, budget_reached: false }
const income = { registrations: 4, orders: 2, paying_users: 1, paid_fen: 1990, refunded_fen: 0, net_fen: 1990, reward_reference_fen: 100 }
async function fixture(context: BrowserContext) {
  const requests: URL[] = []
  await context.route('**/api/v1/**', route => {
    const url = new URL(route.request().url()), path = url.pathname
    requests.push(url)
    if (path === '/api/v1/auth/me') return route.fulfill({ json: { id: 1, username: 'lqyha', role: 'admin', is_super_admin: true } })
    if (path === '/api/v1/generation/options') return route.fulfill({ json: { revision: 'image-r1', timeout_ms: 30000 } })
    if (path.endsWith('/poster')) return route.fulfill({ json: { asset_id: 'a'.repeat(32), request_id: route.request().headers()['x-request-id'], expires_at: 9999999999 } })
    if (path.includes('/image-generation/assets/')) return route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAACgAAAAoCAIAAAADnC86AAAATElEQVR4nO3NsQHAMAzDMIf//+yu0QPMUOEBnN2dF3iyTmMRZnZrrMGrUmMNXpUaa/Cq1FiDV6XGGrwqNdbgVamxBq9KjTV41fw8/gCD6wNNCJl4CAAAAABJRU5ErkJggg==', 'base64') })
    if (path.endsWith('/admins')) return route.fulfill({ json: { items: [{ id: 1, username: 'lqyha', is_active: 1 }] } })
    if (path.endsWith('/rules')) return route.fulfill({ json: promotionRules })
    if (path.endsWith('/summary')) return route.fulfill({ json: income })
    if (path.endsWith('/acquisition')) return route.fulfill({ json: { visits: 10, started: 6, registered: 4, paid: 1, tracking_since: 1794300000, as_of: emptyConversion.as_of } })
    if (path.endsWith('/conversion')) return route.fulfill({ json: { ...emptyConversion, summary: { ...emptyConversion.summary,
      registrations: 4, not_ordered_users: 2, unpaid_users: 1, paying_users: 1, pay_rate_bps: 2500 } } })
    if (path.endsWith('/users')) return route.fulfill({ json: { total: 1, items: [{ id: 'reader', username: 'reader', nickname: '待转化用户', stage: url.searchParams.get('stage') || 'not_ordered', created_at: 1794300000, referral: { source: 'admin', campaign_name: campaign.name, campaign_source: campaign.source } }] } })
    if (path.endsWith('/export/users')) return route.fulfill({ contentType: 'text/csv', body: '账号,来源渠道\nreader,家长群' })
    if (path.endsWith('/campaigns')) return route.fulfill({ json: { items: [campaign], total: 1, page: 1 } })
    if (path.includes('/budget/')) return route.fulfill({ json: { revision: 0, budget_fen: null, used_fen: 100, unknown: 0, reached: false } })
    if (path.endsWith('/performance')) return route.fulfill({ json: { campaign, income, spend_fen: 1000, remainder_fen: 890, return_bps: 8900, trend: [] } })
    if (path.endsWith('/qrcode')) return route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAACgAAAAoCAIAAAADnC86AAAATElEQVR4nO3NsQHAMAzDMIf//+yu0QPMUOEBnN2dF3iyTmMRZnZrrMGrUmMNXpUaa/Cq1FiDV6XGGrwqNdbgVamxBq9KjTV41fw8/gCD6wNNCJl4CAAAAABJRU5ErkJggg==', 'base64') })
    return route.fulfill({ status: 404, json: { detail: 'unknown fixture' } })
  })
  return requests
}

test('点击漏斗打开同一统计时点的名单，刷新与导出保留筛选', async ({ page, context }) => {
  const calls = await fixture(context)
  await page.goto('/admin/#referrals?start=2026-11-01')
  await page.locator('.conversion-stages button').nth(1).click()
  await expect(page.getByRole('tab', { name: '用户与订单' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByText(/名单统计截至/)).toBeVisible()
  await page.reload()
  await expect(page.getByRole('combobox', { name: '转化阶段' })).toContainText('尚未下单')
  await expect(page.getByText(/名单统计截至/)).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出 CSV', exact: true }).click()
  await download
  const exported = calls.filter(url => url.pathname.endsWith('/export/users')).at(-1)!
  expect(exported.searchParams.get('stage')).toBe('not_ordered')
  expect(exported.searchParams.get('as_of')).toBe(String(emptyConversion.as_of))
  expect(exported.searchParams.get('start_date')).toBe('2026-11-01')
})

test('活动搜索、详情与素材按需打开，窄屏海报可下载', async ({ page, context }) => {
  const calls = await fixture(context)
  await page.goto('/admin/#referrals?section=campaigns')
  await page.getByRole('textbox', { name: '活动名称筛选' }).fill('秋季')
  await page.getByRole('textbox', { name: '活动渠道筛选' }).fill('家长群')
  await page.getByRole('button', { name: '筛选活动', exact: true }).click()
  await expect.poll(() => calls.filter(url => url.pathname.endsWith('/campaigns')).at(-1)?.searchParams.get('q')).toBe('秋季')
  await page.getByRole('button', { name: '活动详情', exact: true }).click()
  const detail = page.getByRole('dialog')
  await expect(detail.getByText('89.00%', { exact: true })).toBeVisible()
  await detail.screenshot({ path: '../artifacts/promotion-growth-20261111/campaign-detail.png' })
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '推广素材', exact: true }).click()
  const materials = page.getByRole('dialog')
  await materials.getByRole('button', { name: '预览活动码' }).click()
  await expect(materials.getByRole('img')).toBeVisible()
  await materials.getByRole('button', { name: 'AI 生成海报', exact: true }).click()
  await expect(materials.getByRole('img', { name: 'AI 推广海报完整预览' })).toBeVisible()
  await materials.getByRole('textbox', { name: '海报标题' }).fill('每天进步一点点')
  await expect(materials.getByRole('button', { name: '下载推广海报' })).toBeEnabled()
  expect(calls.filter(url => url.pathname.endsWith('/poster'))).toHaveLength(1)
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await materials.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
  const download = page.waitForEvent('download')
  await materials.getByRole('button', { name: '下载推广海报' }).click()
  expect((await download).suggestedFilename()).toBe('推广海报-growth-demo.png')
  await materials.screenshot({ path: '../artifacts/promotion-ai-poster-20261111/materials-mobile.png' })
  await page.reload()
  await page.getByRole('button', { name: '推广素材', exact: true }).click()
  await expect(page.getByRole('img', { name: 'AI 推广海报完整预览' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '海报标题' })).toHaveValue('每天进步一点点')
  expect(calls.filter(url => url.pathname.endsWith('/poster'))).toHaveLength(1)
})

test('生成断线后刷新查询原图，禁止无意重复生图', async ({ page, context }) => {
  const calls = await fixture(context)
  let submitted = 0
  await context.route('**/api/v1/admin/referrals/poster', route => { submitted++; return route.abort('failed') })
  await context.route('**/api/v1/me/generations/*', route => route.fulfill({ json: { status: 'succeeded', result: { asset_id: 'a'.repeat(32), request_id: 'original', expires_at: 9999999999 } } }))
  await page.goto('/admin/#referrals?section=campaigns')
  await page.getByRole('button', { name: '推广素材', exact: true }).click()
  await page.getByRole('button', { name: 'AI 生成海报', exact: true }).click()
  await expect(page.getByRole('button', { name: '查询原图' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'AI 生成海报', exact: true })).toBeDisabled()
  await page.reload()
  await page.getByRole('button', { name: '推广素材', exact: true }).click()
  await page.getByRole('button', { name: '查询原图' }).click()
  await expect(page.getByRole('img', { name: 'AI 推广海报完整预览' })).toBeVisible()
  expect(submitted).toBe(1)
  expect(calls.filter(url => url.pathname === '/api/v1/generation/options')).toHaveLength(1)
})
