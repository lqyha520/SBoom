import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { request } from '../api'
import { processingDays, settlementTarget } from '../settlement-timing'
import type { ConversionData } from '../referral-conversion'
import type { SettlementSummary } from '../settlement-operations'
import ReferralConversion from '../components/ReferralConversion.vue'
import ReferralRules from '../components/ReferralRules.vue'
import SettlementPromoterOverview from '../components/SettlementPromoterOverview.vue'
import SettlementTarget from '../components/SettlementTarget.vue'

vi.mock('../api', async importOriginal => ({ ...await importOriginal<typeof import('../api')>(), request: vi.fn() }))
const api = vi.mocked(request)
const global = { stubs: {
  UButton: { props: ['label', 'disabled'], template: '<button :disabled="disabled">{{ label }}<slot /></button>' },
  UAlert: { props: ['title'], template: '<p role="alert">{{ title }}</p>' },
  UPagination: true,
  UIcon: true,
} }
const empty: ConversionData = { summary: { registrations: 0, ordered_users: 0, paying_users: 0,
  not_ordered_users: 0, unpaid_users: 0, order_rate_bps: null, pay_rate_bps: null, order_pay_rate_bps: null },
items: [], page: 1, total: 0, as_of: 1794360000 }
const cohort: ConversionData = { ...empty, summary: { registrations: 4, ordered_users: 2, paying_users: 1,
  not_ordered_users: 2, unpaid_users: 1, order_rate_bps: 5000, pay_rate_bps: 2500, order_pay_rate_bps: 5000 } }

beforeEach(() => api.mockReset())

describe('推广转化与结算体验', () => {
  it('处理目标按提交和审核时间分别起算，历史未约定及结束状态不编造期限', () => {
    const submitted = 1794300000, approved = submitted + 5 * 86400
    const terms = { review_days: 3, payout_days: 2 }
    expect(settlementTarget('pending', terms, submitted)).toEqual({ label: '审核处理目标', dueAt: submitted + 3 * 86400 })
    expect(settlementTarget('reviewing', terms, submitted)).toEqual(settlementTarget('pending', terms, submitted))
    expect(settlementTarget('approved', terms, submitted, approved)).toEqual({ label: '付款处理目标', dueAt: approved + 2 * 86400 })
    expect(settlementTarget('pending', undefined, submitted)?.dueAt).toBeNull()
    expect(settlementTarget('approved', terms, submitted)?.dueAt).toBeNull()
    for (const status of ['paid', 'cancelled', 'invalidated', 'rejected', 'void']) expect(settlementTarget(status, terms, submitted, approved)).toBeNull()
    const wrapper = mount(SettlementTarget, { props: { status: 'pending', submittedAt: submitted } })
    expect(wrapper.text()).toContain('提交时未设置，请与财务明确')
    expect(wrapper.text()).not.toContain('已超过目标时间')
    wrapper.unmount()
  })

  it('处理天数允许留空，只接受 1 至 90 的整数', () => {
    expect(processingDays(' ')).toBeNull()
    expect(processingDays('1')).toBe(1)
    expect(processingDays(' 90 ')).toBe(90)
    for (const value of ['0', '-1', '91', '1.5', '1e1', 'NaN']) expect(() => processingDays(value)).toThrow('1 至 90')
  })

  it('首页三种金额口径分开，未知参考金额不显示零，进度入口跳转正确', async () => {
    const summary: SettlementSummary = { available: { count: 2, amount_fen: 0, unknown: 2 },
      pending: { count: 1, amount_fen: 10000 }, reviewing: { count: 2, amount_fen: 20000 },
      approved: { count: 3, amount_fen: 345 }, paid: { count: 4, amount_fen: 1234 },
      holding: { count: 2, amount_fen: 300 }, exception: { count: 1, amount_fen: 500 }, overdue: 0 }
    const wrapper = mount(SettlementPromoterOverview, { props: { summary }, global })
    expect(wrapper.findAll('.metric')).toHaveLength(3)
    expect(wrapper.findAll('.metric-number').map(item => item.text())).toEqual(['待核对', '6 份', '¥12.34'])
    expect(wrapper.text()).toContain('已核定待付 ¥3.45')
    expect(wrapper.text()).not.toContain('¥303.45')
    const approved = wrapper.findAll('button').find(item => item.text() === '待付款 3')!
    await approved.trigger('click')
    expect(wrapper.emitted('select')).toEqual([['statements', 'approved']])
    await wrapper.setProps({ summary: { ...summary, available: { count: 2, amount_fen: 123, unknown: 1 } } })
    expect(wrapper.findAll('.metric-number')[0]!.text()).toBe('¥1.23')
    expect(wrapper.text()).toContain('已知参考税前小计；另有 1 笔金额待核对')
    wrapper.unmount()
  })

  it('筛选变化期间忽略旧漏斗响应，重试失败不展示上次数据，空分母显示横线', async () => {
    let finishOld!: (value: ConversionData) => void
    api.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve }))
      .mockResolvedValueOnce(cohort).mockRejectedValueOnce(new Error('转化统计暂不可用')).mockResolvedValueOnce(empty)
    const wrapper = mount(ReferralConversion, { props: { filters: { campaign_id: 'old' } }, global })
    await wrapper.setProps({ filters: { campaign_id: 'new', start_date: '2026-11-01' } })
    finishOld({ ...cohort, summary: { ...cohort.summary, registrations: 999 } })
    await flushPromises()
    expect(api).toHaveBeenLastCalledWith(expect.stringContaining('campaign_id=new&start_date=2026-11-01'))
    expect(wrapper.findAll('.conversion-stages strong').map(item => item.text())).toEqual(['4', '2', '1', '1'])
    await wrapper.get('.conversion-stages button:nth-child(2)').trigger('click')
    expect(wrapper.emitted('stage')).toEqual([['not_ordered', cohort.as_of]])
    expect(wrapper.text()).toContain('注册→付费 25.00%')
    expect(wrapper.text()).not.toContain('999')
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('转化统计暂不可用')
    expect(wrapper.findAll('.conversion-stages button')).toHaveLength(0)
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('注册→付费 —')
    expect(wrapper.text()).toContain('这段时间暂无注册用户')
    wrapper.unmount()
  })

  it('推广规则独立只读加载，刷新失败隐藏旧奖励，重试能显示停用和未约定时效', async () => {
    const rules = { revision: 1, enabled: true, rate_bps: 1000, hold_days: 14, max_reward_fen: 500,
      channel_rate_bps: 60, shared_fees: [], review_days: 3, payout_days: 2 }
    api.mockResolvedValueOnce(rules).mockRejectedValueOnce(new Error('服务暂不可用'))
      .mockResolvedValueOnce({ ...rules, enabled: false, review_days: null, payout_days: null })
    const wrapper = mount(ReferralRules, { props: { area: 'settlements' }, global })
    await flushPromises()
    expect(wrapper.attributes('open')).toBeUndefined()
    expect(api).toHaveBeenCalledWith('/api/v1/admin/settlements/rules')
    expect(wrapper.text()).toContain('首付奖励 10%')
    expect(wrapper.text()).toContain('提交申请后 3 个自然日')
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('奖励规则读取失败')
    expect(wrapper.text()).not.toContain('首付奖励 10%')
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('当前未启用新订单推广奖励')
    expect(wrapper.text()).toContain('尚未设置，提交前请与财务明确')
    expect(api.mock.calls.every(([path]) => path === '/api/v1/admin/settlements/rules')).toBe(true)
    wrapper.unmount()
  })
})
