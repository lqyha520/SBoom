import { expect, test } from '@playwright/test'
import type { Order, Reconciliation } from '../src/growth'

const item: Order = { id: 'order-1', user_id: 'buyer-1', username: 'buyer', nickname: '测试用户', plan_name: '月会员', plan_days: 30,
  amount_fen: 3000, status: 'pending', payment_channel: 'wechat', virtual_env: 0, virtual_offer_id: '', virtual_product_id: '',
  virtual_order_id: '', virtual_order_type: 0, device_platform: 'android', delivered_at: null, revision: 1,
  created_at: 1761177600, paid_at: null, expires_at: 1761178500, transaction_id: null, refund: null }
const record: Reconciliation = { id: 'recon-1', bill_date: '2026-10-20', status: 'complete', error: '', created_at: 1792540800,
  summary: { wechat_paid_fen: 3000, wechat_refunded_fen: 0, local_paid_fen: 3000, local_refunded_fen: 0, differences: 0 } }
function plans(wechat: boolean, virtual: boolean, virtualEnabled = virtual) {
  return { items: [], checkout_enabled: virtualEnabled ? virtual : wechat, checkout_channel: virtualEnabled ? 'virtual' : 'wechat',
    configuration: { enabled: wechat, ready: wechat }, virtual_configuration: { enabled: virtualEnabled, ready: virtual } }
}

test('慢配置不阻塞历史订单，配置失败可在订单弹窗内重试且撤回旧能力', async ({ context, page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  let failConfig = false, configReads = 0, listReads = 0
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/auth/me') { await route.fulfill({ json: { id: 1, username: 'admin', role: 'admin' } }); return }
    if (path === '/api/v1/admin/commerce/plans') {
      if (++configReads === 1) await pending
      await route.fulfill(failConfig ? { status: 503, json: { detail: { error: '配置暂不可用' } } } : { json: plans(true, false) })
      return
    }
    if (path === '/api/v1/admin/commerce/orders') {
      listReads++
      await route.fulfill({ json: { items: [item], total: 1, has_more: false, summary: { orders: 1, paid_fen: 3000, refunded_fen: 0 } } }); return
    }
    if (path === '/api/v1/admin/commerce/orders/' + item.id) { await route.fulfill({ json: item }); return }
    throw new Error('未声明请求：' + path)
  })
  try {
    await page.goto('/admin/#orders')
    await expect(page.getByText('月会员 · 30 天', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '导出 CSV', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: '查看订单', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '会员订单', exact: true })
    const sync = dialog.getByRole('button', { name: '查询微信状态', exact: true })
    await expect(sync).toBeDisabled()
    release()
    await expect(sync).toBeEnabled()
    failConfig = true
    await dialog.getByRole('button', { name: '刷新支付配置', exact: true }).click()
    await expect(sync).toBeDisabled()
    await expect(dialog.getByText(/支付配置读取失败/)).toBeVisible()
    failConfig = false
    await dialog.getByRole('button', { name: '刷新支付配置', exact: true }).click()
    await expect(sync).toBeEnabled()
    expect(listReads).toBe(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  } finally { release() }
})

test('对账按微信商户配置启用，虚拟支付就绪与故障均不干扰判断', async ({ context, page }) => {
  let current = plans(false, true), listReads = 0
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/auth/me') { await route.fulfill({ json: { id: 1, username: 'admin', role: 'admin' } }); return }
    if (path === '/api/v1/admin/commerce/plans') { await route.fulfill({ json: current }); return }
    if (path === '/api/v1/admin/commerce/reconciliations') {
      listReads++
      await route.fulfill({ json: { items: [record], total: 1, has_more: false } }); return
    }
    if (path === '/api/v1/admin/commerce/reconciliations/' + record.id) { await route.fulfill({ json: record }); return }
    throw new Error('未声明请求：' + path)
  })
  await page.goto('/admin/#reconciliations')
  await expect(page.getByText(record.bill_date, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '下载并核对账单', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: '查看差异', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '账单核对 · ' + record.bill_date })
  await expect(dialog.getByText('此日收款与退款记录一致', { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '关闭', exact: true }).filter({ hasText: '关闭' }).click()
  current = plans(true, false, true)
  await page.getByRole('button', { name: '刷新支付配置', exact: true }).click()
  await expect(page.getByRole('button', { name: '下载并核对账单', exact: true })).toBeEnabled()
  expect(listReads).toBe(1)
})

test('过期用户列表链接直接回有效末页，不连续请求中间空页', async ({ context, page }) => {
  const offsets: number[] = []
  await context.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/auth/me') { await route.fulfill({ json: { id: 1, username: 'admin', role: 'admin' } }); return }
    if (url.pathname === '/api/v1/admin/mini-users') {
      const offset = Number(url.searchParams.get('offset')); offsets.push(offset)
      await route.fulfill({ json: { items: offset === 20 ? [{ id: 'buyer', username: 'buyer', nickname: '末页用户', avatar: '', has_password: true,
        membership: 'regular', is_vip: false, membership_status: 'regular', vip_expires_at: null, is_active: true,
        revision: 1, created_at: 1, updated_at: 1, login_method: 'password' }] : [], total: 21, has_more: false } }); return
    }
    throw new Error('未声明请求：' + url.pathname)
  })
  await page.goto('/admin/#miniUsers?page=40')
  await expect(page.getByRole('row').filter({ hasText: '末页用户' })).toBeVisible()
  await expect(page).toHaveURL(/#miniUsers\?page=2$/)
  expect(offsets).toContain(780)
  expect(offsets).toContain(20)
  expect(offsets.every(offset => offset === 780 || offset === 20)).toBe(true)
  expect(offsets.length).toBeLessThanOrEqual(3)
})
