import { emptyConversion, promotionRules } from './promotion-fixtures'
import { expect, test, type BrowserContext } from '@playwright/test'
import type { ApplicationQuote, Reward, RewardPolicy, SettlementApplication, Statement } from '../src/settlements'

function commonResponse(path: string) {
  if (path.endsWith('/rules')) return promotionRules
  if (path.endsWith('/conversion')) return emptyConversion
  if (path.endsWith('/summary')) return { ...Object.fromEntries(['available','holding','exception','pending','reviewing','approved','paid'].map(key => [key, { count: 0, amount_fen: 0, unknown: 0 }])), overdue: 0 }
  if (path.endsWith('/admins')) return { items: [{ id: 1, username: '推广管理员' }] }
  if (path.endsWith('/payee')) return null
  if (path.endsWith('/notices')) return { unread: 0, last_id: 0, items: [] }
  if (path.endsWith('/bills')) return { items: [] }
  if (path.endsWith('/batches')) return { items: [], total: 0 }
  return undefined
}

async function fixture(context: BrowserContext, superAdmin = true, percentage = false, applications = false, unknownFees = false, blocked = false, billConflicts?: { value: boolean }) {
  const writes: { path: string; body: Record<string, unknown> }[] = []
  const policy: RewardPolicy = { revision: 1, enabled: true, beneficiary: 'admin', rate_bps: 2000, hold_days: 0, shared_fees: [{ name: '资料成本', amount_fen: 100 }] }
  const reward: Reward = { order_id: 'order-first-1234', beneficiary: 'admin:1', beneficiary_name: '推广管理员', revision: 1, status: 'pending', application_state: 'available', policy, costs: null, commission_fen: null, statement_id: null, reason: '', amount_fen: 1990, paid_at: 1794300000, available_at: 1794300000, refund_status: null, payment_channel: 'wechat', device_platform: 'android' }
  if (percentage) {
    policy.rate_bps = 1000
    policy.shared_fees = [{ name: '服务成本分摊', mode: 'percent', rate_bps: 500, basis: 'after_channel' }]
    reward.amount_fen = 10000
    if (!superAdmin) {
      reward.costs = { channel_fee_fen: 60, shared_fees: [{ ...policy.shared_fees[0]!, base_fen: 9940, amount_fen: 497 }], evidence: '账单与费用约定', confirmed: true }
      reward.commission_fen = 944
    }
  }
  let statement: Statement | null = null
  let application: SettlementApplication | null = null
  const quote: ApplicationQuote = { quote_digest: 'a'.repeat(64), snapshot: { items: [{ order_id: reward.order_id, revision: 1, amount_fen: reward.amount_fen,
    policy: { ...policy, channel_rate_bps: 0 }, costs: null, reference_channel_rate_bps: 0, reference_channel_fen: 0, reference_fees: policy.shared_fees, reference_commission_fen: 378 }],
    adjustments: [], service_terms: { review_days: 3, payout_days: 2 }, reference_gross_fen: 378, adjustment_fen: 0, reference_after_adjustment_fen: 378, unconfirmed_orders: 1, personal_fen: null, tax_fen: null, net_fen: null } }
  if (unknownFees) {
    Object.assign(quote.snapshot, { reference_gross_fen: null, reference_after_adjustment_fen: null, unknown_orders: 1, known_reference_gross_fen: 0 })
    Object.assign(quote.snapshot.items[0]!, { reference_channel_rate_bps: null, reference_channel_fen: null, reference_commission_fen: null })
  }
  if (blocked) {
    reward.application_state = 'exception'
    reward.eligibility_issue = { code: 'earlier_order', reason: '仍有较早的未完成订单，请先查单或关闭后再结算', order_id: 'order-earlier-1234' }
  }
  await context.route('**/api/v1/**', route => {
    const req = route.request(), path = new URL(req.url()).pathname
    if (req.method() === 'GET' && /\/statements\/[^/]+$/.test(path) && statement) return route.fulfill({ json: { statement, attachments: [], timeline: [], bill_differences: billConflicts?.value ? [{ order_id: reward.order_id, reasons: ['微信账单差异未完整留存'] }] : [] } })
    if (path.endsWith('/payout-candidates')) return route.fulfill({ json: { items: statement?.status === 'approved' ? [{ ...statement, payout_issues: [], batch_id: null }] : [], total: statement?.status === 'approved' ? 1 : 0 } })
    const common = req.method() === 'GET' ? commonResponse(path) : undefined
    if (common !== undefined) return route.fulfill({ json: common })
    if (path === '/api/v1/auth/me') return route.fulfill({ json: { id: 1, username: 'lqyha', role: 'admin', is_super_admin: superAdmin, admin_permissions: { settlements: applications ? ['view', 'create'] : ['view'] }, permissions_revision: 1 } })
    if (req.method() !== 'GET') writes.push({ path, body: req.postDataJSON() })
    if (path.endsWith('/policy')) {
      if (req.method() === 'PUT') Object.assign(policy, req.postDataJSON(), { revision: policy.revision + 1 })
      return route.fulfill({ json: policy })
    }
    if (path.endsWith('/list/rewards')) return route.fulfill({ json: { total: 1, items: [reward] } })
    if (path.endsWith('/list/statements')) return route.fulfill({ json: { total: statement ? 1 : 0, items: statement ? [statement] : [] } })
    if (path.endsWith('/list/adjustments')) return route.fulfill({ json: { total: 0, items: [] } })
    if (path.endsWith('/list/requests')) return route.fulfill({ json: { total: application ? 1 : 0, items: application ? [application] : [] } })
    if (path.endsWith('/requests/preview')) return route.fulfill({ json: quote })
    if (path.endsWith('/requests')) {
      application = { ...structuredClone(quote), id: 'application-1234', beneficiary: reward.beneficiary, beneficiary_name: reward.beneficiary_name,
        revision: 1, status: 'pending', request_key: req.postDataJSON().request_key, note: req.postDataJSON().note,
        reason: '', statement_id: null, created_at: 1794300000, updated_at: 1794300000 }
      reward.request_id = application.id
      return route.fulfill({ json: application })
    }
    if (path.endsWith('/costs') && path.includes('/requests/') && application) {
      const item = req.postDataJSON().items[0]
      reward.costs = { ...item, channel_fee_fen: Math.floor((reward.amount_fen * item.channel_rate_bps + 5000) / 10000) }
      reward.commission_fen = 375; reward.revision++; application.revision++
      return route.fulfill({ json: application })
    }
    if (path.includes('/requests/') && application) {
      if (path.endsWith('/start')) { application.status = 'reviewing'; application.revision++; return route.fulfill({ json: application }) }
      if (path.endsWith('/cancel') || path.endsWith('/reject')) {
        application.status = path.endsWith('/cancel') ? 'cancelled' : 'rejected'; application.reason = req.postDataJSON().reason; application.revision++; reward.request_id = null
        return route.fulfill({ json: application })
      }
      return route.fulfill({ json: { request: application, rewards: [reward], statement } })
    }
    if (path.endsWith('/costs')) {
      reward.costs = { ...req.postDataJSON(), channel_fee_fen: Math.floor((reward.amount_fen * req.postDataJSON().channel_rate_bps + 5000) / 10000) }; reward.commission_fen = percentage ? 944 : 375; reward.revision++
      if (percentage && reward.costs) reward.costs.shared_fees = [{ ...reward.costs.shared_fees[0]!, base_fen: 9940, amount_fen: 497 }]
      return route.fulfill({ json: reward })
    }
    if (path.endsWith('/statements')) {
      statement = { id: 'statement-1234', beneficiary: reward.beneficiary, beneficiary_name: reward.beneficiary_name, revision: 1, status: 'draft', gross_fen: 375, adjustment_fen: 0, personal_fen: 0, tax_fen: null, net_fen: null, reason: '', receipt: '', created_at: 1794300000, snapshot: { items: [{ order_id: reward.order_id, amount_fen: reward.amount_fen, commission_fen: 375, costs: reward.costs!, policy }], adjustments: [] }, review: null }
      reward.statement_id = statement.id
      statement.snapshot.payee = { name: '测试收款人', method: 'bank', account: '****5678', bank: '测试银行', revision: 1 }
      statement.snapshot.service_terms = application?.snapshot.service_terms ?? { review_days: null, payout_days: null }
      if (application) { application.statement_id = statement.id; application.revision++ }
      return route.fulfill({ json: statement })
    }
    if (path.endsWith('/approve') && statement) {
      statement.review = req.postDataJSON(); statement.personal_fen = 10; statement.tax_fen = 20; statement.net_fen = 345; statement.status = 'approved'; statement.revision++
      statement.approved_at = 1794386400
      if (application) { application.status = 'approved'; application.revision++ }
      return route.fulfill({ json: statement })
    }
    if (path.endsWith('/paid') && statement) {
      statement.receipt = req.postDataJSON().receipt; statement.status = 'paid'; statement.revision++
      if (application) { application.status = 'paid'; application.revision++ }
      return route.fulfill({ json: statement })
    }
    return route.fulfill({ status: 403, json: { detail: { error: '未授权' } } })
  })
  return writes
}

test('财务默认进入申请待办，奖励入口和规则草稿保留，手机布局不溢出', async ({ page, context }) => {
  const writes = await fixture(context)
  await page.goto('/admin/#settlements')
  await expect(page.getByRole('tabpanel')).toHaveCount(1)
  await expect(page.getByLabel('结算金额汇总').locator('.metric')).toHaveCount(3)
  await expect(page.getByRole('button', { name: '保存奖励规则' })).toBeHidden()
  await expect(page.getByRole('textbox', { name: '收款人' })).toBeHidden()
  await expect(page.getByRole('combobox', { name: '结算支付渠道' })).toBeHidden()
  await expect(page.getByRole('button', { name: '结算申请与处理', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: '首付奖励', exact: true }).click()
  const row = page.getByRole('row').filter({ has: page.getByRole('checkbox', { name: '选择订单order-first-1234' }) })
  await expect(row).toBeInViewport({ ratio: 1 })
  await page.screenshot({ path: '../artifacts/settlement-workspace-redesign.png', animations: 'disabled' })
  await page.evaluate(() => { location.hash = '#referralRules' })
  await page.getByRole('textbox', { name: '奖励比例（%）' }).fill('15')
  await page.evaluate(() => { location.hash = '#financeSettlements' })
  await page.evaluate(() => { location.hash = '#referralRules' })
  await expect(page.getByRole('textbox', { name: '奖励比例（%）' })).toHaveValue('15')
  await page.evaluate(() => { location.hash = '#financeSettlements' })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.locator('.admin-main').evaluate(element => { element.scrollTop = 0 })
  expect(await page.getByRole('tabpanel').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
  await page.screenshot({ path: '../artifacts/settlement-workspace-mobile-redesign.png', animations: 'disabled' })
  expect(writes).toHaveLength(0)
})

test('核对手续费和个税后才可结款，保留分成与费用快照', async ({ page, context }) => {
  const writes = await fixture(context)
  await page.goto('/admin/#settlements?mode=rewards')
  await expect(page.getByText('费用待核对', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '核对费用', exact: true }).click()
  let dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('textbox', { name: '实际支付渠道手续费率（%）' })).toHaveValue('')
  await expect(dialog.getByRole('button', { name: '确认保存', exact: true })).toBeDisabled()
  await dialog.getByRole('textbox', { name: '实际支付渠道手续费率（%）' }).fill('0.60')
  await expect(dialog.getByText('支付渠道费：订单实收 ¥19.90 × 0.6% = ¥0.12', { exact: true })).toBeVisible()
  await dialog.getByRole('textbox', { name: '核对依据 / 凭据编号' }).fill('微信实际账单与资料成本凭据')
  await dialog.getByRole('checkbox', { name: '已据实核对全部费用及凭据，无重复扣费' }).check()
  await expect(dialog.getByText('税前奖励：¥3.75', { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '确认保存', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await page.getByRole('checkbox', { name: '选择订单order-first-1234' }).check()
  await page.getByRole('button', { name: '生成结算草稿', exact: true }).click()
  await expect(page.getByRole('cell', { name: '待核对 / 待核对', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '审核结算', exact: true }).click()
  dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('textbox', { name: '实际代扣个人所得税（元）' })).toHaveValue('')
  await dialog.getByRole('button', { name: '添加个人费用', exact: true }).click()
  await dialog.getByRole('textbox', { name: '个人费用名称1', exact: true }).fill('转账服务费')
  await dialog.getByRole('textbox', { name: '个人费用金额1', exact: true }).fill('0.10')
  await dialog.getByRole('textbox', { name: '实际代扣个人所得税（元）' }).fill('0.20')
  await dialog.getByRole('textbox', { name: '核对依据 / 凭据编号' }).fill('财务核定税款凭据')
  await dialog.getByRole('checkbox', { name: '已据实核对全部费用及凭据，无重复扣费' }).check()
  await expect(dialog.getByText('最终应付：¥3.45', { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '核对并批准结算', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await page.getByRole('button', { name: '办理付款', exact: true }).click()
  await expect(page).toHaveURL(/#financePayments\?statement=statement-1234/)
  await dialog.getByRole('textbox', { name: '实际付款金额（元）' }).fill('3.45')
  await dialog.getByRole('textbox', { name: '转账流水号 / 核销凭据' }).fill('bank-transfer-123')
  await dialog.locator('input[type=datetime-local]').fill('2026-11-11T12:00')
  await dialog.getByRole('button', { name: '确认登记付款', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await page.evaluate(() => { location.hash = '#financeSettlements?mode=statements' })
  await expect(page.getByRole('button', { name: '办理付款', exact: true })).toHaveCount(0)
  await expect(page.getByRole('cell').filter({ hasText: '¥3.45' }).filter({ hasText: '已结算' })).toBeVisible()
  expect(writes.find(item => item.path.endsWith('/costs'))?.body).toMatchObject({ channel_rate_bps: 60, shared_fees: [{ name: '资料成本', amount_fen: 100 }], confirmed: true })
  expect(writes.find(item => item.path.endsWith('/costs'))?.body).not.toHaveProperty('channel_fee_fen')
  expect(writes.find(item => item.path.endsWith('/approve'))?.body).toMatchObject({ personal_fees: [{ name: '转账服务费', amount_fen: 10 }], tax_fen: 20 })
  expect(writes.find(item => item.path.endsWith('/paid'))?.body).toMatchObject({ amount_fen: 345, receipt: 'bank-transfer-123' })
  await page.screenshot({ path: '../artifacts/settlements-desktop.png', fullPage: true })
})

test('审核窗口提前显示账单阻塞，刷新通过后需重新确认才能批准', async ({ page, context }) => {
  const conflicts = { value: true }
  const writes = await fixture(context, true, false, false, false, false, conflicts)
  await page.goto('/admin/#settlements?mode=rewards')
  await page.getByRole('button', { name: '核对费用', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: '实际支付渠道手续费率（%）' }).fill('0.60')
  await dialog.getByRole('textbox', { name: '核对依据 / 凭据编号' }).fill('实际渠道费用凭据')
  await dialog.getByRole('checkbox', { name: '已据实核对全部费用及凭据，无重复扣费' }).check()
  await dialog.getByRole('button', { name: '确认保存', exact: true }).click()
  await page.getByRole('checkbox', { name: '选择订单order-first-1234' }).check()
  await page.getByRole('button', { name: '生成结算草稿', exact: true }).click()
  await page.getByRole('button', { name: '审核结算', exact: true }).click()
  await expect(dialog.getByText('order-first-1234：微信账单差异未完整留存', { exact: true })).toBeVisible()
  await dialog.getByRole('textbox', { name: '实际代扣个人所得税（元）' }).fill('0.00')
  await dialog.getByRole('textbox', { name: '核对依据 / 凭据编号' }).fill('个人税费核定依据')
  await dialog.getByRole('checkbox', { name: '已据实核对全部费用及凭据，无重复扣费' }).check()
  await expect(dialog.getByRole('button', { name: '核对并批准结算', exact: true })).toBeDisabled()
  expect(writes.some(item => item.path.endsWith('/approve'))).toBe(false)
  conflicts.value = false
  await dialog.getByRole('button', { name: '刷新审核账单检查', exact: true }).click()
  await expect(dialog.getByText('order-first-1234：微信账单差异未完整留存', { exact: true })).toHaveCount(0)
  await expect(dialog.getByRole('checkbox', { name: '已据实核对全部费用及凭据，无重复扣费' })).not.toBeChecked()
  await dialog.getByRole('checkbox', { name: '已据实核对全部费用及凭据，无重复扣费' }).check()
  await dialog.getByRole('button', { name: '核对并批准结算', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  expect(writes.filter(item => item.path.endsWith('/approve'))).toHaveLength(1)
})

test('普通管理员仅能查看自身奖励，不显示财务操作，手机视图可用', async ({ page, context }) => {
  const writes = await fixture(context, false)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/#settlements')
  await expect(page.getByText('费用待核对', { exact: true })).toBeVisible()
  for (const name of ['申请结算', '核对费用', '生成结算草稿', '导出结算明细', '保存奖励规则', '记调整']) await expect(page.getByRole('button', { name, exact: true })).toBeHidden()
  expect(writes).toHaveLength(0)
  await page.screenshot({ path: '../artifacts/settlements-mobile.png', fullPage: true })
})

test('百分比费用显示基数和到分计算，修改时不回传已计算金额', async ({ page, context }) => {
  const writes = await fixture(context, true, true)
  await page.goto('/admin/#settlements?mode=rewards')
  await page.getByRole('button', { name: '核对费用', exact: true }).click()
  let dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('textbox', { name: '共同费用比例1' })).toHaveValue('5.00')
  await dialog.getByRole('textbox', { name: '实际支付渠道手续费率（%）' }).fill('1.00')
  await expect(dialog.getByText('支付渠道费：订单实收 ¥100.00 × 1% = ¥1.00', { exact: true })).toBeVisible()
  await dialog.getByRole('textbox', { name: '实际支付渠道手续费率（%）' }).fill('0.60')
  await expect(dialog.getByText('支付渠道费：订单实收 ¥100.00 × 0.6% = ¥0.60', { exact: true })).toBeVisible()
  await expect(dialog.getByText('服务成本分摊：扣支付手续费后金额 ¥99.40 × 5% = ¥4.97')).toBeVisible()
  await expect(dialog.getByText('税前奖励：¥94.43 × 10% = ¥9.44')).toBeVisible()
  await dialog.getByRole('textbox', { name: '核对依据 / 凭据编号' }).fill('实际支付账单和服务费约定')
  await dialog.getByRole('checkbox', { name: '已据实核对全部费用及凭据，无重复扣费' }).check()
  await dialog.getByRole('button', { name: '确认保存', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  expect(writes.find(item => item.path.endsWith('/costs'))?.body.shared_fees).toEqual([
    { name: '服务成本分摊', mode: 'percent', rate_bps: 500, basis: 'after_channel' },
  ])
  await page.getByRole('button', { name: '核对费用', exact: true }).click()
  dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('textbox', { name: '共同费用比例1' })).toHaveValue('5.00')
  await expect(dialog.getByRole('textbox', { name: '实际支付渠道手续费率（%）' })).toHaveValue('0.60')
  await expect(dialog.getByText('税前奖励：¥94.43 × 10% = ¥9.44')).toBeVisible()
  await dialog.screenshot({ path: '../artifacts/settlement-percentage-calculation.png' })
})

test('普通管理员手机端可核对百分比计算明细', async ({ page, context }) => {
  const writes = await fixture(context, false, true)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/#settlements')
  await page.getByRole('button', { name: '计算明细', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('服务成本分摊：扣支付手续费后金额 ¥99.40 × 5% = ¥4.97')).toBeVisible()
  await expect(dialog.getByText('税前奖励：¥94.43 × 10% = ¥9.44')).toBeVisible()
  expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
  expect(writes).toHaveLength(0)
  await dialog.screenshot({ path: '../artifacts/settlement-percentage-mobile.png' })
})

test('起步建议可编辑并实时试算，保存前不改规则', async ({ page, context }) => {
  const writes = await fixture(context)
  await page.goto('/admin/#settlements')
  await page.evaluate(() => { location.hash = '#referralRules' })
  await page.getByRole('button', { name: '填入起步建议', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '奖励比例（%）' })).toHaveValue('10.00')
  await expect(page.getByRole('textbox', { name: '普通微信支付费率（%）' })).toHaveValue('0.60')
  await expect(page.getByRole('textbox', { name: '虚拟支付安卓/鸿蒙/Windows费率（%）' })).toHaveValue('1.00')
  await expect(page.getByRole('textbox', { name: '虚拟支付iOS费率（%）' })).toHaveValue('12.00')
  await expect(page.getByRole('spinbutton', { name: '付款后等待天数' })).toHaveValue('14')
  await expect(page.getByRole('spinbutton', { name: '审核处理目标（自然日，留空不指定）' })).toHaveValue('')
  await expect(page.getByRole('spinbutton', { name: '付款处理目标（自然日，留空不指定）' })).toHaveValue('')
  await expect(page.getByRole('textbox', { name: '默认共同费用比例1' })).toHaveValue('0.00')
  await expect(page.getByRole('checkbox', { name: '启用首次付费奖励' })).toBeChecked()
  expect(writes).toHaveLength(0)
  await page.getByText('规则试算（不入账）', { exact: true }).click()
  await expect(page.getByText('最终到手：max(0，¥9.94) = ¥9.94')).toBeVisible()
  await page.getByRole('textbox', { name: '默认共同费用比例1' }).fill('5')
  await page.getByRole('spinbutton', { name: '审核处理目标（自然日，留空不指定）' }).fill('3')
  await page.getByRole('spinbutton', { name: '付款处理目标（自然日，留空不指定）' }).fill('2')
  await expect(page.getByText('最终到手：max(0，¥9.44) = ¥9.44')).toBeVisible()
  await page.getByRole('button', { name: '保存奖励规则', exact: true }).click()
  await expect(page.getByText('规则已保存：奖励规则用于新订单，处理目标用于新申请')).toBeVisible()
  expect(writes.find(item => item.path.endsWith('/policy'))?.body).toMatchObject({
    enabled: true, rate_bps: 1000, hold_days: 14, review_days: 3, payout_days: 2, channel_rates: { wechat: 60, virtual_android: 100, virtual_ios: 1200 }, shared_fees: [{ mode: 'percent', rate_bps: 500, basis: 'after_channel' }],
  })
  await page.screenshot({ path: '../artifacts/settlement-policy-preview.png', fullPage: true })
})

test('未知渠道费的申请预览和提交结果显示待核对，仍可提交对账', async ({ page, context }) => {
  await fixture(context, false, false, true, true)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/#settlements')
  await page.getByRole('checkbox', { name: '选择订单order-first-1234' }).check()
  await page.getByRole('button', { name: '申请结算', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('申请时参考税前奖励合计：待核对', { exact: true })).toBeVisible()
  await expect(dialog.getByText('支付渠道费：待核对', { exact: true })).toBeVisible()
  await expect(dialog.getByText(/¥3\.78/)).toHaveCount(0)
  await dialog.getByRole('checkbox', { name: '已了解奖励和扣费明细，待核费用及最终应付以对账审核为准' }).check()
  await dialog.screenshot({ path: '../artifacts/settlement-unknown-reference-mobile.png' })
  await dialog.getByRole('button', { name: '确认提交申请' }).click()
  await expect(page.getByRole('cell', { name: /参考税前 待核对/ })).toBeVisible()
})

test('服务器判定异常的成熟奖励不可勾选，并显示核对提示', async ({ page, context }) => {
  await fixture(context, false, false, true, false, true)
  await page.goto('/admin/#settlements')
  await expect(page.getByRole('checkbox', { name: '选择订单order-first-1234' })).toBeDisabled()
  await expect(page.getByText('仍有较早的未完成订单，请先查单或关闭后再结算', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '申请结算', exact: true })).toHaveCount(0)
})

test('管理员申请先展示扣费参考，超级管理员对账审核付款后可查最终金额', async ({ page, context }) => {
  test.setTimeout(60000)
  const writes = await fixture(context, false, false, true)
  await page.goto('/admin/#settlements')
  await page.getByRole('checkbox', { name: '选择订单order-first-1234' }).check()
  await page.getByRole('button', { name: '申请结算', exact: true }).click()
  let dialog = page.getByRole('dialog')
  await expect(dialog.getByText('资料成本：固定金额 ¥1.00')).toBeVisible()
  await expect(dialog.getByText('参考税前奖励：¥18.90 × 20% = ¥3.78')).toBeVisible()
  await expect(dialog.getByText('实际代扣个人所得税：待核定。')).toBeVisible()
  await expect(dialog.getByText(/审核处理目标.*3 个自然日/)).toBeVisible()
  await expect(dialog.getByRole('button', { name: '确认提交申请' })).toBeDisabled()
  await dialog.getByRole('textbox', { name: '申请备注' }).fill('请核对我的推广奖励')
  await dialog.getByRole('checkbox', { name: '已了解奖励和扣费明细，待核费用及最终应付以对账审核为准' }).check()
  await dialog.screenshot({ path: '../artifacts/settlement-application-preview.png' })
  await dialog.getByRole('button', { name: '确认提交申请' }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('cell', { name: /待对账/ })).toBeVisible()
  await page.getByRole('button', { name: '申请明细' }).click()
  const panel = page.getByLabel('结算处理区')
  await expect(panel).toBeFocused()
  await panel.getByRole('button', { name: '收起处理区' }).click()
  await expect(page.getByRole('button', { name: '申请明细' })).toBeFocused()
  await page.getByRole('button', { name: '申请明细' }).click()
  await expect(panel.getByText(/^审核处理目标：2026/)).toBeVisible()
  await expect(panel.getByText(/提交时未设置/)).toHaveCount(0)
  await expect(panel.getByRole('button', { name: '撤回申请' })).toBeVisible()
  await expect(panel.getByRole('button', { name: '开始对账' })).toHaveCount(0)
  await panel.getByRole('button', { name: '收起处理区' }).click()
  await expect(dialog).toHaveCount(0)

  await context.route('**/api/v1/auth/me', route => route.fulfill({ json: { id: 99, username: 'super', role: 'admin', is_super_admin: true, admin_permissions: {}, permissions_revision: 1 } }))
  await page.reload()
  await expect(page.locator('#nav-panel-finance')).toHaveCount(1)
  await page.evaluate(() => { location.hash = '#financeSettlements?mode=requests' })
  await page.getByRole('button', { name: '开始对账', exact: true }).click()
  await expect(panel.getByRole('button', { name: '生成本次申请结算单' })).toBeDisabled()
  await panel.getByRole('textbox', { name: '实际支付渠道手续费率（%）' }).fill('0.60')
  await panel.getByRole('textbox', { name: '核对依据 / 凭据编号' }).fill('微信实际账单与资料成本凭据')
  await panel.getByRole('checkbox', { name: '已据实核对全部费用及凭据，无重复扣费' }).check()
  await panel.getByRole('button', { name: '保存并核对下一笔' }).click()
  await expect(panel.getByText('订单费用：已核对 1 / 1 笔')).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await panel.getByRole('button', { name: '生成本次申请结算单' }).click()
  await panel.getByRole('button', { name: '审核个人费用与税费' }).click()
  dialog = page.getByRole('dialog', { name: '核对个人费用与税费' })
  await dialog.getByRole('button', { name: '添加个人费用', exact: true }).click()
  await dialog.getByRole('textbox', { name: '个人费用名称1' }).fill('转账服务费')
  await dialog.getByRole('textbox', { name: '个人费用金额1' }).fill('0.10')
  await dialog.getByRole('textbox', { name: '实际代扣个人所得税（元）' }).fill('0.20')
  await dialog.getByRole('textbox', { name: '核对依据 / 凭据编号' }).fill('财务核定税款凭据')
  await dialog.getByRole('checkbox', { name: '已据实核对全部费用及凭据，无重复扣费' }).check()
  await dialog.getByRole('button', { name: '核对并批准结算' }).click()
  await expect(dialog).toHaveCount(0)
  await expect(panel.getByText('最终到手：max(0，¥3.45) = ¥3.45')).toBeVisible()
  await expect(panel.getByText(/^付款处理目标：2026/)).toBeVisible()
  await panel.getByRole('button', { name: '办理付款', exact: true }).click()
  await expect(page).toHaveURL(/#financePayments\?statement=statement-1234/)
  dialog = page.getByRole('dialog', { name: '登记已完成的付款' })
  await dialog.getByRole('textbox', { name: '实际付款金额（元）' }).fill('3.45')
  await dialog.getByRole('textbox', { name: '转账流水号 / 核销凭据' }).fill('bank-application-123')
  await dialog.locator('input[type=datetime-local]').fill('2026-11-11T12:00')
  await dialog.getByRole('button', { name: '确认登记付款' }).click()
  await expect(dialog).toHaveCount(0)
  await page.evaluate(() => { location.hash = '#financeSettlements?mode=requests' })
  await expect(page.getByRole('cell', { name: /已结算/ })).toBeVisible()

  await context.route('**/api/v1/auth/me', route => route.fulfill({ json: { id: 1, username: 'promoter', role: 'admin', is_super_admin: false, admin_permissions: { settlements: ['view', 'create'] }, permissions_revision: 1 } }))
  await page.reload()
  await expect(page.locator('#nav-panel-finance')).toHaveCount(0)
  await page.evaluate(() => { location.hash = '#referralEarnings?mode=requests' })
  await page.getByRole('button', { name: '申请明细' }).click()
  dialog = page.getByLabel('结算处理区')
  await expect(dialog.getByText('最终到手：max(0，¥3.45) = ¥3.45')).toBeVisible()
  await expect(dialog.getByText('付款凭证：bank-application-123')).toBeVisible()
  await expect(dialog.getByRole('button', { name: '办理付款' })).toHaveCount(0)
  await dialog.getByText('提交时的奖励与扣费明细（留档）', { exact: true }).click()
  await expect(dialog.getByText('参考税前奖励：¥18.90 × 20% = ¥3.78')).toBeVisible()
  expect(writes.find(item => item.path.endsWith('/requests'))?.body).toMatchObject({ order_ids: ['order-first-1234'], confirmed: true, quote_digest: 'a'.repeat(64) })
  expect(writes.find(item => item.path.endsWith('/statements'))?.body).toMatchObject({ settlement_request_id: 'application-1234', order_ids: [] })
  await dialog.getByText('提交时的奖励与扣费明细（留档）', { exact: true }).click()
  await dialog.screenshot({ path: '../artifacts/settlement-application-paid.png' })
})

test('手机端申请预览可读，待对账申请可填写原因撤回', async ({ page, context }) => {
  const writes = await fixture(context, false, false, true)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/#settlements')
  await page.getByRole('checkbox', { name: '选择订单order-first-1234' }).check()
  await page.getByRole('button', { name: '申请结算', exact: true }).click()
  let dialog = page.getByRole('dialog')
  await expect(dialog.getByText('实际代扣个人所得税：待核定。')).toBeVisible()
  expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
  await dialog.screenshot({ path: '../artifacts/settlement-application-mobile.png' })
  await dialog.getByRole('checkbox', { name: '已了解奖励和扣费明细，待核费用及最终应付以对账审核为准' }).check()
  await dialog.getByRole('button', { name: '确认提交申请' }).click()
  await expect(dialog).toHaveCount(0)
  await page.getByRole('button', { name: '申请明细' }).click()
  dialog = page.getByLabel('结算处理区')
  await expect(dialog.getByRole('button', { name: '撤回申请' })).toBeDisabled()
  await dialog.getByRole('textbox', { name: '撤回原因' }).fill('补充订单后重新申请')
  await dialog.getByRole('button', { name: '撤回申请' }).click()
  await expect(dialog.getByText('推广管理员 · 已撤回', { exact: true })).toBeVisible()
  expect(writes.find(item => item.path.endsWith('/cancel'))?.body).toMatchObject({ revision: 1, reason: '补充订单后重新申请' })
})

test('申请失败后重新预览须再次确认，重试沿用同一申请编号', async ({ page, context }) => {
  const writes = await fixture(context, false, false, true)
  let firstBody: Record<string, unknown> | null = null
  await context.route('**/api/v1/admin/settlements/requests', route => {
    if (firstBody) return route.fallback()
    firstBody = route.request().postDataJSON()
    return route.fulfill({ status: 409, json: { detail: { error: '费用或奖励已变化，请重新查看申请明细后确认' } } })
  })
  await page.goto('/admin/#settlements')
  await page.getByRole('checkbox', { name: '选择订单order-first-1234' }).check()
  await page.getByRole('button', { name: '申请结算', exact: true }).click()
  const dialog = page.getByRole('dialog')
  const confirm = dialog.getByRole('checkbox', { name: '已了解奖励和扣费明细，待核费用及最终应付以对账审核为准' })
  await confirm.check()
  await dialog.getByRole('button', { name: '确认提交申请' }).click()
  await expect(dialog.getByText('费用或奖励已变化，请重新查看申请明细后确认', { exact: true })).toBeVisible()
  await expect(confirm).not.toBeChecked()
  await dialog.getByRole('button', { name: '重新核对申请明细' }).click()
  await expect(dialog.getByRole('button', { name: '确认提交申请' })).toBeDisabled()
  await confirm.check()
  await dialog.getByRole('button', { name: '确认提交申请' }).click()
  await expect(dialog).toHaveCount(0)
  expect(writes.filter(item => item.path.endsWith('/preview'))).toHaveLength(2)
  expect(writes.find(item => item.path.endsWith('/requests'))?.body.request_key).toBe(firstBody!['request_key'])
})


async function batchFixture(context: BrowserContext) {
  const policy: RewardPolicy = { revision: 1, enabled: true, beneficiary: 'admin', rate_bps: 1000, hold_days: 14,
    channel_rates: { wechat: 60, virtual_android: 100, virtual_ios: 1200 }, shared_fees: [] }
  const rewards: Reward[] = Array.from({ length: 22 }, (_, i) => ({ order_id: 'batch-' + (i + 1), beneficiary: 'admin:1', beneficiary_name: '演示管理员',
    revision: 1, status: 'pending', policy: { ...policy, channel_rate_bps: i === 20 ? 1200 : 100 }, costs: null, commission_fen: null,
    statement_id: null, request_id: null, reason: '', amount_fen: 10000, paid_at: 1600000000 + i * 86400,
    application_state: i === 21 ? 'holding' : 'available', available_at: i === 21 ? 253402300000 : 1600000000, refund_status: null, payment_channel: 'virtual', device_platform: i === 20 ? 'ios' : 'android' }))
  const writes: Record<string, unknown>[] = []
  await context.route('**/api/v1/**', route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname
    const common = req.method() === 'GET' ? commonResponse(path) : undefined
    if (common !== undefined) return route.fulfill({ json: common })
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 1, username: 'demo', role: 'admin', is_super_admin: false, admin_permissions: { settlements: ['view', 'create'] }, permissions_revision: 1 } })
    if (path.endsWith('/list/rewards')) {
      const offset = Number(url.searchParams.get('offset') || 0)
      return route.fulfill({ json: { total: rewards.length, items: rewards.slice(offset, offset + 20) } })
    }
    if (path.endsWith('/requests/preview')) {
      const body = req.postDataJSON()
      const chosen = body.all_eligible ? rewards.slice(0, 21) : rewards.filter(r => body.order_ids.includes(r.order_id))
      const items = chosen.map((r: Reward) => ({ ...r, reference_channel_fen: r.policy.channel_rate_bps!, reference_channel_rate_bps: r.policy.channel_rate_bps!, reference_fees: [], reference_commission_fen: r.device_platform === 'ios' ? 880 : 990 }))
      const channels = ['android', 'ios'].map(platform => {
        const group = items.filter((r: Reward) => r.device_platform === platform)
        return { key: 'virtual_' + platform, label: platform === 'ios' ? '虚拟支付 · iOS' : '虚拟支付 · 安卓/鸿蒙/Windows', orders: group.length, amount_fen: group.length * 10000,
          channel_fen: group.length * (platform === 'ios' ? 1200 : 100), shared_fen: 0, commission_fen: group.length * (platform === 'ios' ? 880 : 990), unknown_rates: 0 }
      }).filter(group => group.orders)
      const gross = channels.reduce((n, group) => n + group.commission_fen, 0)
      return route.fulfill({ json: { quote_digest: 'b'.repeat(64), snapshot: { items, channels, all_eligible: !!body.all_eligible,
        excluded: body.all_eligible ? [{ order_id: 'batch-22', reason: '尚未到结算等待期', available_at: 253402300000 }] : [],
        adjustments: [], reference_gross_fen: gross, adjustment_fen: 0, reference_after_adjustment_fen: gross, unconfirmed_orders: items.length, personal_fen: null, tax_fen: null, net_fen: null } } })
    }
    if (path.endsWith('/requests') && req.method() === 'POST') { writes.push(req.postDataJSON()); return route.fulfill({ json: {} }) }
    if (path.endsWith('/list/requests')) return route.fulfill({ json: { total: 0, items: [] } })
    return route.fulfill({ status: 403, json: { detail: { error: '未授权' } } })
  })
  return writes
}

test('跨页勾选多笔到期订单，安卓和iOS合并申请并显示分别扣费', async ({ page, context }) => {
  const writes = await batchFixture(context)
  await page.goto('/admin/#settlements')
  const android = page.getByRole('row').filter({ has: page.getByRole('checkbox', { name: '选择订单batch-1', exact: true }) })
  await expect(android.getByLabel('本单扣费与奖励比例').getByText('1%', { exact: true })).toBeVisible()
  await expect(android.getByText('参考税前奖励：¥9.90', { exact: true })).toBeVisible()
  await page.getByRole('checkbox', { name: '选择订单batch-1', exact: true }).check()
  await page.getByRole('button', { name: 'Page 2', exact: true }).click()
  const ios = page.getByRole('row').filter({ has: page.getByRole('checkbox', { name: '选择订单batch-21', exact: true }) })
  await expect(ios.getByLabel('本单扣费与奖励比例').getByText('12%', { exact: true })).toBeVisible()
  await expect(ios.getByText('参考税前奖励：¥8.80', { exact: true })).toBeVisible()
  await ios.getByRole('button', { name: '计算明细' }).click()
  await expect(page.getByRole('dialog').getByText('参考支付渠道费：订单实收 ¥100.00 × 12% = ¥12.00（待对账）', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByText('已选择 1 笔（包含其他分页）')).toBeVisible()
  await page.getByRole('checkbox', { name: '选择订单batch-21', exact: true }).check()
  await expect(page.getByRole('checkbox', { name: '选择订单batch-22', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: '申请结算', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('虚拟支付 · iOS · 1 笔', { exact: true })).toBeVisible()
  await expect(dialog.getByText('实收 ¥100.00 · 渠道费 ¥12.00', { exact: true })).toBeVisible()
  await expect(dialog.getByText('实收 ¥100.00 · 渠道费 ¥1.00', { exact: true })).toBeVisible()
  await expect(dialog.getByText('申请时参考税前奖励合计：¥9.90 + ¥8.80 = ¥18.70')).toBeVisible()
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: '确认提交申请' }).click()
  await expect(dialog).toHaveCount(0)
  expect(writes[0]).toMatchObject({ order_ids: ['batch-1', 'batch-21'], confirmed: true })
})

test('手机端可一次预览全部成熟订单，等待期未满明确排除，无月份限制', async ({ page, context }) => {
  const writes = await batchFixture(context)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/#settlements')
  await expect(page.getByLabel('结算月份')).toHaveCount(0)
  await page.getByRole('button', { name: '预览全部可申请订单' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByLabel('分渠道结算汇总').getByText('虚拟支付 · 安卓/鸿蒙/Windows · 20 笔')).toBeVisible()
  await expect(dialog.getByLabel('本次申请扣费比例').getByText('1%', { exact: true })).toBeVisible()
  await expect(dialog.getByLabel('本次申请扣费比例').getByText('12%', { exact: true })).toBeVisible()
  await expect(dialog.getByText('申请时参考税前奖励合计：21 笔逐单奖励相加 = ¥206.80')).toBeVisible()
  await dialog.getByText('本次未纳入 1 笔，查看原因').click()
  await expect(dialog.getByText(/batch-22：尚未到结算等待期/)).toBeVisible()
  expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
  await dialog.screenshot({ path: '../artifacts/settlement-batch-mobile.png' })
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: '确认提交申请' }).click()
  await expect(dialog).toHaveCount(0)
  expect(writes[0]).toMatchObject({ all_eligible: true, confirmed: true })
  expect(writes[0]).not.toHaveProperty('order_ids')
  expect(writes[0]).not.toHaveProperty('month')
})

test('主页面连续核对和分渠道批量核对，个人费用按比例审核后直接登记付款', async ({ page, context }) => {
  const policy: RewardPolicy = { revision: 6, enabled: true, beneficiary: 'admin', rate_bps: 10000, hold_days: 14,
    channel_rate_bps: 100, shared_fees: [{ name: '技术服务费', mode: 'percent', rate_bps: 500, basis: 'order_gross' }] }
  const rewards: Reward[] = [1, 2, 3].map(i => ({ order_id: 'flow-order-' + i, beneficiary: 'admin:1', beneficiary_name: '测试推广人',
    revision: 2, status: 'pending', policy: { ...policy, channel_rate_bps: i === 3 ? 1200 : 100 }, costs: null, commission_fen: null,
    statement_id: null, request_id: 'flow-request', reason: '', amount_fen: 10000, paid_at: 1600000000, available_at: 1600000000,
    refund_status: null, payment_channel: 'virtual', device_platform: i === 3 ? 'ios' : 'android' }))
  const snapshot: ApplicationQuote['snapshot'] = { items: rewards.map(r => ({ ...r, reference_channel_fen: r.policy.channel_rate_bps!,
    reference_channel_rate_bps: r.policy.channel_rate_bps!, reference_fees: policy.shared_fees, reference_commission_fen: r.device_platform === 'ios' ? 8300 : 9400 })),
    adjustments: [], reference_gross_fen: 27100, adjustment_fen: 0, reference_after_adjustment_fen: 27100, unconfirmed_orders: 3, personal_fen: null, tax_fen: null, net_fen: null }
  const application: SettlementApplication = { id: 'flow-request', beneficiary: 'admin:1', beneficiary_name: '测试推广人', revision: 1, status: 'pending',
    request_key: 'flow-request-key', quote_digest: 'a'.repeat(64), note: '', reason: '', statement_id: null, created_at: 1600000000, updated_at: 1600000000, snapshot }
  let statement: Statement | null = null
  const batches: { items: { order_id: string; channel_rate_bps: number }[] }[] = []
  let reviewBody: Record<string, unknown> | null = null
  await context.route('**/api/v1/**', route => {
    const req = route.request(), path = new URL(req.url()).pathname
    if (req.method() === 'GET' && /\/statements\/[^/]+$/.test(path) && statement) return route.fulfill({ json: { statement, attachments: [], timeline: [], bill_differences: [] } })
    if (path.endsWith('/payout-candidates')) return route.fulfill({ json: { items: statement?.status === 'approved' ? [{ ...statement, payout_issues: [], batch_id: null }] : [], total: statement?.status === 'approved' ? 1 : 0 } })
    const common = req.method() === 'GET' ? commonResponse(path) : undefined
    if (common !== undefined) return route.fulfill({ json: common })
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 99, username: 'super', role: 'admin', is_super_admin: true, admin_permissions: {}, permissions_revision: 1 } })
    if (path.endsWith('/policy')) return route.fulfill({ json: policy })
    if (path.endsWith('/list/requests')) return route.fulfill({ json: { total: 1, items: [{ ...application, confirmed_orders: rewards.filter(r => r.costs).length, statement_summary: statement }] } })
    if (path.endsWith('/list/statements')) return route.fulfill({ json: { items: statement ? [statement] : [], total: statement ? 1 : 0 } })
    if (path.endsWith('/requests/flow-request/start')) { application.status = 'reviewing'; application.revision++; return route.fulfill({ json: application }) }
    if (path.endsWith('/requests/flow-request/costs')) {
      const body = req.postDataJSON(); batches.push(body)
      expect(body.revision).toBe(application.revision)
      for (const item of body.items) {
        const r = rewards.find(r => r.order_id === item.order_id)!
        expect(item.revision).toBe(r.revision)
        const channel = Math.floor((r.amount_fen * item.channel_rate_bps + 5000) / 10000)
        r.costs = { channel_fee_fen: channel, channel_rate_bps: item.channel_rate_bps,
          shared_fees: [{ name: '技术服务费', mode: 'percent', rate_bps: 500, basis: 'order_gross', base_fen: 10000, amount_fen: 500 }], evidence: item.evidence, confirmed: true }
        r.commission_fen = r.device_platform === 'ios' ? 8300 : 9400; r.revision++
      }
      application.revision++; return route.fulfill({ json: application })
    }
    if (path.endsWith('/requests/flow-request')) return route.fulfill({ json: { request: application, rewards, statement } })
    if (path.endsWith('/statements')) {
      statement = { id: 'flow-statement', beneficiary: application.beneficiary, beneficiary_name: application.beneficiary_name,
        revision: 1, status: 'draft', gross_fen: 27100, adjustment_fen: 0, personal_fen: 0, tax_fen: null, net_fen: null, reason: '', receipt: '', created_at: 1600000000,
        snapshot: { payee: { name: '测试收款人', method: 'bank', account: '****5678', bank: '测试银行', revision: 1 }, items: rewards.map(r => ({ ...r, costs: r.costs!, commission_fen: r.commission_fen! })), adjustments: [] }, review: null }
      application.statement_id = statement.id; application.revision++; return route.fulfill({ json: statement })
    }
    if (path.endsWith('/approve') && statement) {
      const body = req.postDataJSON(); reviewBody = body
      const personal = [{ ...body.personal_fees[0], base_fen: 27100, amount_fen: 1355 }]
      statement.review = { ...body, personal_fees: personal }; statement.personal_fen = personal.reduce((n, f) => n + f.amount_fen, 0)
      statement.tax_fen = body.tax_fen; statement.net_fen = 27100 - statement.personal_fen - body.tax_fen
      statement.status = 'approved'; statement.revision++; application.status = 'approved'; application.revision++
      return route.fulfill({ json: statement })
    }
    if (path.endsWith('/paid') && statement) {
      expect(req.postDataJSON().amount_fen).toBe(25744)
      statement.receipt = req.postDataJSON().receipt; statement.status = 'paid'; statement.revision++
      application.status = 'paid'; application.revision++; return route.fulfill({ json: statement })
    }
    return route.fulfill({ status: 403, json: { detail: { error: '未授权' } } })
  })
  await page.goto('/admin/#settlements?mode=requests')
  await page.getByRole('button', { name: '开始对账', exact: true }).click()
  const panel = page.getByLabel('结算处理区')
  await expect(panel.getByText('当前核对：flow-order-1')).toBeVisible()
  await panel.getByRole('textbox', { name: '核对依据 / 凭据编号' }).fill('第一笔已与账单核实')
  await panel.getByRole('checkbox', { name: '已据实核对全部费用及凭据，无重复扣费' }).check()
  await panel.getByRole('button', { name: '保存并核对下一笔' }).click()
  await expect(panel.getByText('当前核对：flow-order-2')).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await panel.getByRole('button', { name: '按各单规则批量核对' }).click()
  await expect(panel.getByText('本批参考税前奖励：¥177.00')).toBeVisible()
  await panel.getByRole('textbox', { name: '核对依据 / 凭据编号' }).fill('剩余两笔分渠道核实')
  await panel.getByRole('checkbox', { name: '已逐单核实本批费用规则与实际账单一致，无重复扣费' }).check()
  await panel.getByRole('button', { name: '确认批量核对 2 笔' }).click()
  await expect(panel.getByText('订单费用：已核对 3 / 3 笔')).toBeVisible()
  expect(batches.map(b => b.items.map(i => [i.order_id, i.channel_rate_bps]))).toEqual([[['flow-order-1', 100]], [['flow-order-2', 100], ['flow-order-3', 1200]]])
  await panel.getByRole('button', { name: '生成本次申请结算单' }).click()
  await panel.getByRole('button', { name: '审核个人费用与税费' }).click()
  let dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: '添加个人费用' }).click()
  await dialog.getByRole('textbox', { name: '个人费用名称1' }).fill('个人服务费')
  await dialog.getByRole('combobox', { name: '个人费用方式1' }).click()
  await page.getByRole('option', { name: '按百分比', exact: true }).click()
  await dialog.getByRole('textbox', { name: '个人费用比例1' }).fill('5')
  await dialog.getByRole('textbox', { name: '实际代扣个人所得税（元）' }).fill('0.01')
  await expect(dialog.getByText('个人费用 · 个人服务费：税前奖励合计 ¥271.00 × 5% = ¥13.55（扣除）')).toBeVisible()
  await dialog.getByRole('textbox', { name: '核对依据 / 凭据编号' }).fill('个人费用按约定核对')
  await dialog.getByRole('checkbox', { name: '已据实核对全部费用及凭据，无重复扣费' }).check()
  await dialog.getByRole('button', { name: '核对并批准结算' }).click()
  await expect(dialog).toHaveCount(0)
  await expect(panel.getByText('最终到手：max(0，¥257.44) = ¥257.44')).toBeVisible()
  expect(reviewBody).toMatchObject({ personal_fees: [{ name: '个人服务费', mode: 'percent', rate_bps: 500, basis: 'reward_gross' }] })
  await panel.getByRole('button', { name: '收起处理区' }).click()
  await expect(page.getByText('最终应付：¥257.44', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '办理付款', exact: true }).click()
  dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: '实际付款金额（元）' }).fill('257.44')
  await dialog.getByRole('textbox', { name: '转账流水号 / 核销凭据' }).fill('DEMO-browser-only')
  await dialog.locator('input[type=datetime-local]').fill('2026-11-11T12:00')
  await dialog.getByRole('button', { name: '确认登记付款' }).click()
  await expect(dialog).toHaveCount(0)
  await page.evaluate(() => { location.hash = '#financeSettlements?mode=requests' })
  await page.getByRole('button', { name: '申请明细', exact: true }).click()
  await expect(panel.getByText('付款凭证：DEMO-browser-only')).toBeVisible()
  await panel.screenshot({ path: '../artifacts/settlement-inline-workflow.png' })
})
