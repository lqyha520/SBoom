import type { BrowserContext } from '@playwright/test'
import { emptyConversion, promotionRules } from './promotion-fixtures'
import type { Statement } from '../src/settlements'
import type { CampaignExpense, Dispute, FinanceControls, FinanceExpense, MonthlyReport, PayoutBatch } from '../src/promotion-finance'

export async function businessFixture(context: BrowserContext, role: 'super' | 'promoter' | 'costs' | 'review' | 'payout' | 'reconcile' = 'super', options: { loseExpenseResponse?: boolean } = {}) {
  const writes: { path: string; body: Record<string, unknown> }[] = [], requests: string[] = []
  const controls: FinanceControls = { revision: 1, separate_review: false, separate_payment: false }
  const report: MonthlyReport = { admin_id: 1, admin_name: '推广管理员', month: '2026-10', quote_digest: 'a'.repeat(64), opening_fen: 1000, closing_fen: 800, totals: { reward: 1000, tax: -100, payment: -1100 }, as_of: 1794300000, archive_id: null, items: [] }
  const statement: Statement = { id: 'statement-business-1', beneficiary: 'admin:1', beneficiary_name: '推广管理员', revision: 2, status: 'approved', gross_fen: 1000, adjustment_fen: 0, personal_fen: 0, tax_fen: 0, net_fen: 1000, reason: '', receipt: '', created_at: 1794300000,
    snapshot: { items: [], adjustments: [], payee: { name: '测试收款人', method: 'bank', account: '****5678', bank: '测试银行', revision: 1 } }, review: null }
  const campaign = { id: 'campaign-business-1', admin_id: 1, admin_name: '推广管理员', name: '家长群活动', source: '微信群', active: true, revision: 1, code: 'a_test', path: 'pages/home/index', budget_fen: null, spend_fen: 1000, registrations: 3, paying_users: 1, unknown: 0, reward_known: 1 }
  const expenses: CampaignExpense[] = [], batches: PayoutBatch[] = [], issues: Dispute[] = []
  const statements = [statement], financeRows: FinanceExpense[] = []
  const expenseRequests = new Map<string, CampaignExpense>()
  let loseExpenseResponse = options.loseExpenseResponse
  await context.route('**/api/v1/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname, method = req.method()
    requests.push(method + ' ' + path + url.search)
    const body = method !== 'GET' && req.headers()['content-type']?.includes('json') ? req.postDataJSON() as Record<string, unknown> : {}
    if (method !== 'GET') writes.push({ path, body })
    const respond = (json: unknown) => route.fulfill({ json })
    if (path.endsWith('/auth/me')) return respond({ id: 1, username: '推广管理员', role: 'admin', is_super_admin: role === 'super', admin_permissions: {
      settlements: ['super', 'promoter'].includes(role) ? ['view', 'create', 'export'] : ['view'],
      ...(['super', 'promoter'].includes(role) ? { referrals: ['view', 'create', 'export'] } : {}),
      ...(role === 'costs' ? { settlementCosts: ['view', 'run'] } : {}),
      ...(role === 'review' ? { settlementReview: ['view', 'run'] } : {}),
      ...(role === 'payout' ? { settlementPayout: ['view', 'run', 'export'] } : {}),
      ...(role === 'reconcile' ? { reconciliations: ['view'] } : {}),
    }, permissions_revision: 1 })
    if (path.endsWith('/admins')) return respond({ items: [{ id: 1, username: '推广管理员', is_active: true }] })
    if (path.endsWith('/rules') || path.endsWith('/policy')) return respond(promotionRules)
    if (path.endsWith('/conversion')) return respond(emptyConversion)
    if (path.endsWith('/acquisition')) return respond({ visits: 0, started: 0, registered: 0, paid: 0, tracking_since: 1794300000 })
    if (path.endsWith('/notices')) return respond({ unread: 0, last_id: 0, items: [] })
    if (path.endsWith('/payee')) return respond(null)
    if (path.endsWith('/bills')) return respond({ items: [] })
    if (path.endsWith('/settlements/summary')) return respond({ ...Object.fromEntries(['available', 'holding', 'exception', 'pending', 'reviewing', 'approved', 'paid'].map(key => [key, { count: 0, amount_fen: 0 }])), overdue: 0 })
    if (path.endsWith('/referrals/summary')) return respond({ registrations: 3, orders: 2, paying_users: 1, paid_fen: 2000, refunded_fen: 0, net_fen: 2000 })
    if (/\/statements\/[^/]+$/.test(path) && method === 'GET') { const item = statements.find(item => item.id === path.split('/').at(-1)); return respond({ statement: item, attachments: [], timeline: [], bill_differences: [] }) }
    if (path.endsWith('/paid')) { const item = statements.find(item => item.id === path.split('/').at(-2))!; Object.assign(item, { status: 'paid', receipt: body.receipt, revision: item.revision + 1 }); return respond(item) }
    if (path.endsWith('/payout-candidates')) {
      const items = statements.filter(item => item.status === 'approved').map(item => ({ ...item, payout_issues: [], batch_id: null }))
      const page = Math.min(Number(url.searchParams.get('page') || 1), Math.max(1, Math.ceil(items.length / 20)))
      return respond({ items: items.slice((page - 1) * 20, page * 20), total: items.length, page })
    }
    if (path.endsWith('/payout-candidates/preview')) {
      const items = statements.filter(item => (body.statement_ids as string[]).includes(item.id)).map(item => ({ ...item, payout_issues: item.status === 'approved' ? [] : ['结算单不再是待付款状态'] }))
      return respond({ items, total_fen: items.reduce((n, item) => n + Math.max(0, item.net_fen || 0), 0), blocked: items.filter(item => item.payout_issues.length).length })
    }
    if (path.endsWith('/list/statements')) { const items = statements.filter(item => (!url.searchParams.get('admin_id') || item.beneficiary === 'admin:' + url.searchParams.get('admin_id')) && (!url.searchParams.get('status') || item.status === url.searchParams.get('status'))); return respond({ items, total: items.length }) }
    if (path.endsWith('/settlements/expenses')) { const scope = financeRows.filter(item => (!url.searchParams.get('admin_id') || String(item.admin_id) === url.searchParams.get('admin_id')) && (!url.searchParams.get('q') || item.campaign_name.includes(url.searchParams.get('q')!))); const items = scope.filter(item => (!url.searchParams.get('start_date') || item.expense_date >= url.searchParams.get('start_date')!) && (!url.searchParams.get('end_date') || item.expense_date <= url.searchParams.get('end_date')!) && (!url.searchParams.get('state') || url.searchParams.get('state') === 'all' || item.active === (url.searchParams.get('state') === 'active'))); const offset = (Number(url.searchParams.get('page') || 1) - 1) * 20; return respond({ items: items.slice(offset, offset + 20), total: items.length, period_fen: items.filter(item => item.active).reduce((n, item) => n + item.amount_fen, 0), baseline_fen: 1000, cumulative_fen: 1000 + scope.filter(item => item.active && !item.included_in_baseline).reduce((n, item) => n + item.amount_fen, 0), unknown_campaigns: 0 }) }
    if (path.includes('/list/') || path.endsWith('/users') || path.endsWith('/orders')) return respond({ items: [], total: 0 })
    if (path.endsWith('/finance-controls')) { if (method === 'PUT') Object.assign(controls, body, { revision: controls.revision + 1 }); return respond(controls) }
    if (path.endsWith('/monthly')) return respond({ ...report, month: url.searchParams.get('month') })
    if (path.endsWith('/monthly/archive')) {
      if (body.quote_digest !== report.quote_digest) return route.fulfill({ status: 409, json: { detail: { error: '月度账本已变化，请刷新后重新核对再留档' } } })
      Object.assign(report, { archive_id: 'monthly-archive-1' }); return respond(report)
    }
    if (path.endsWith('/export.xlsx') || path.endsWith('/export.csv')) return route.fulfill({ body: 'download-fixture', contentType: 'application/octet-stream' })
    if (path.endsWith('/batches')) {
      if (method === 'POST') { const item: PayoutBatch = { id: 'batch-business-1', name: String(body.name), status: 'active', revision: 1, created_at: 1794300000, total_fen: 1000, items: [{ statement_id: statement.id, status: 'pending', statement_status: 'approved', reason: '', receipt: '', snapshot: { revision: 2, amount_fen: 1000, beneficiary_name: '推广管理员', payee: statement.snapshot.payee! } }] }; batches.push(item); return respond(item) }
      const items = batches.filter(item => (!url.searchParams.get('q') || (item.name + item.id).includes(url.searchParams.get('q')!)) && (!url.searchParams.get('status') || item.status === url.searchParams.get('status')))
      const offset = (Number(url.searchParams.get('page') || 1) - 1) * 20
      return respond({ items: items.slice(offset, offset + 20), total: items.length })
    }
    if (/\/batches\/[^/]+$/.test(path) && method === 'GET') { const item = batches.find(value => value.id === path.split('/').at(-1)); return item ? respond(item) : route.fulfill({ status: 404, json: { detail: { error: '付款批次不存在' } } }) }
    if (path.endsWith('/preview')) return respond({ matched: String(body.content).includes('bad') ? 0 : 1, blocked: String(body.content).includes('bad') ? 1 : 0, items: [{ statement_id: statement.id, status: 'paid', amount_fen: 1000, receipt: 'bank-001', issues: String(body.content).includes('bad') ? ['收款账号不一致'] : [] }] })
    if (path.endsWith('/import')) { Object.assign(batches[0]!, { status: 'completed', revision: 2 }); batches[0]!.items[0]!.status = 'paid'; return respond({ paid: 1, failed: 0, pending: 0, blocked: 0, issues: [] }) }
    if (path.endsWith('/cancel')) { Object.assign(batches[0]!, { status: 'cancelled', revision: batches[0]!.revision + 1 }); for (const item of batches[0]!.items) if (item.status !== 'paid') item.status = 'cancelled'; return respond(batches[0]) }
    if (path.endsWith('/disputes')) {
      if (method === 'POST') { const issue: Dispute = { id: 'dispute-business-1', beneficiary: 'admin:1', target_kind: body.target_kind as Dispute['target_kind'], target_id: String(body.target_id), title: String(body.title), status: 'open', revision: 1, created_at: 1794300000, messages: [{ id: 1, actor_name: '推广管理员', content: String(body.content), evidence: String(body.evidence), created_at: 1794300000 }], files: [] }; issues.push(issue); return respond(issue) }
      const items = issues.filter(item => (!url.searchParams.get('status') || item.status === url.searchParams.get('status')) && (!url.searchParams.get('personal') || item.beneficiary === 'admin:1'))
      return respond({ items, total: items.length })
    }
    if (/\/disputes\/[^/]+$/.test(path) && method === 'GET') { const issue = issues.find(item => item.id === path.split('/').slice(-1)[0]); return issue ? respond(issue) : route.fulfill({ status: 404, json: { detail: { error: '异议不存在' } } }) }
    if (path.endsWith('/reply')) { const issue = issues.find(item => item.id === path.split('/').slice(-2)[0])!; issue.status = body.status as Dispute['status']; issue.revision++; issue.messages.push({ id: 2, actor_name: '推广管理员', content: String(body.content), evidence: String(body.evidence), created_at: 1794300000 }); return respond(issue) }
    if (path.endsWith('/files')) { issues[0]!.files.push({ id: 'file-1', name: '凭据.pdf', media_type: 'application/pdf', created_at: 1794300000 }); issues[0]!.revision++; return respond({ id: 'file-1' }) }
    if (path.endsWith('/campaigns')) return respond({ items: [campaign], total: 1 })
    if (path.includes('/budget/')) return respond({ revision: 1, budget_fen: null, used_fen: 0, unknown: 0, reached: false })
    if (path.endsWith('/performance')) return respond({ campaign, income: { paid_fen: 5000, refunded_fen: 0, reward_reference_fen: 1000, reward_known: 1 }, spend_fen: 1000 + expenses.filter(item => item.active && !item.included_in_baseline).reduce((n, item) => n + item.amount_fen, 0), remainder_fen: null, return_bps: null, trend: [] })
    if (path.endsWith('/expenses')) {
      if (method === 'POST') {
        const key = String(body.request_key), prior = expenseRequests.get(key)
        if (prior) return respond(prior)
        const item = { ...body, id: 'expense-1', revision: 1, active: true } as unknown as CampaignExpense
        expenseRequests.set(key, item); expenses.push(item)
        if (loseExpenseResponse) { loseExpenseResponse = false; return route.abort('failed') }
        return respond(item)
      }
      return respond({ items: expenses, total: expenses.length, baseline_fen: 1000, period_fen: expenses.filter(item => item.active).reduce((n, item) => n + item.amount_fen, 0), cumulative_fen: 1000 + expenses.filter(item => item.active && !item.included_in_baseline).reduce((n, item) => n + item.amount_fen, 0) })
    }
    if (path.endsWith('/expenses/expense-1')) { Object.assign(expenses[0]!, body, { revision: expenses[0]!.revision + 1 }); return respond(expenses[0]) }
    if (path.endsWith('/quality')) return respond({ as_of: 1794300000, total: 1, items: [30, 60, 90].map(days => ({ group_key: campaign.id, campaign_name: campaign.name, admin_name: '推广管理员', days, observed_users: 1, waiting_users: 2, paying_users: 1, renewing_users: 1, refunded_users: 0, net_fen: 3000, pay_rate_bps: 10000, renewal_rate_bps: 10000, value_per_user_fen: 3000 })) })
    return route.fulfill({ status: 403, json: { detail: { error: '未配置的测试接口' } } })
  })
  return { writes, requests, report, controls, batches, expenses, issues, statements, financeRows }
}
