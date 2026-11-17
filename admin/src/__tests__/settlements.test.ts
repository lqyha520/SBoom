import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { calculateReward, channelFeeFen, channelLabel, feeDrafts, feeValues, moneyFen, percentageBps, personalFeeValues, resolvePersonalFees, rewardApplicationState, rewardCalculation, sharedFeeValues, starterPolicy } from '../settlements'
import SettlementChannels from '../components/SettlementChannels.vue'
import RewardCalculation from '../components/RewardCalculation.vue'
import SettlementCalculation from '../components/SettlementCalculation.vue'
import SettlementApplicationSummary from '../components/SettlementApplicationSummary.vue'
import SettlementRateSummary from '../components/SettlementRateSummary.vue'
import type { ApplicationSnapshot, Reward } from '../settlements'
import SettlementDifference from '../components/SettlementDifference.vue'

describe('结算金额输入', () => {
  it('单笔奖励封顶使用本单快照并在公式中展示，零上限不视为未配置', () => {
    expect(calculateReward(10000, 60, [], 2000, 500).commission).toBe(500)
    expect(calculateReward(10000, 60, [], 2000, 0).commission).toBe(0)
    const wrapper = mount(RewardCalculation, { props: { amount: 10000, channel: 60, fees: [], rate: 2000, cap: 500 } })
    expect(wrapper.text()).toContain('本单奖励上限：¥5.00')
    expect(wrapper.text()).toContain('min（¥99.40 × 20%，¥5.00） = ¥5.00')
    wrapper.unmount()
  })
  it('个人费用在结算单汇总计算，展示比例、基数，保留核定快照', () => {
    const fees = personalFeeValues([{ name: '协作费', amount: '', mode: 'percent', rate: '3.33', basis: 'reward_gross' },
      { name: '服务费', amount: '', mode: 'percent', rate: '5', basis: 'after_adjustment' }, { name: '固定费用', amount: '0.07' }])
    expect(fees[0]).not.toHaveProperty('amount_fen')
    expect(resolvePersonalFees(fees, 796, -100).map(fee => fee.amount_fen)).toEqual([26, 34, 7])
    expect(resolvePersonalFees([fees[1]!], 100, -200)[0]).toMatchObject({ base_fen: 0, amount_fen: 0 })
    expect(resolvePersonalFees([{ ...fees[0]!, base_fen: 796, amount_fen: 26 }], 99999, 0)[0]?.amount_fen).toBe(26)
    expect(() => personalFeeValues([{ name: '错误基数', amount: '', mode: 'percent', rate: '5', basis: 'order_gross' }])).toThrow()
    const wrapper = mount(SettlementCalculation, { props: { gross: 796, adjustment: -100, fees, tax: 10 } })
    expect(wrapper.text()).toContain('税前奖励合计 ¥7.96 × 3.33% = ¥0.26')
    expect(wrapper.text()).toContain('历史调整后可用奖励 ¥6.96 × 5% = ¥0.34')
    expect(wrapper.text()).toContain('最终到手：max(0，¥6.19) = ¥6.19')
    wrapper.unmount()
  })
  it('未对账展示本单费率，核定后以费用快照为准，未知费率不套用新版配置', () => {
    const item = { amount_fen: 1990, costs: null, commission_fen: null,
      policy: { revision: 1, enabled: true, beneficiary: 'admin' as const, rate_bps: 10000, hold_days: 14,
        channel_rate_bps: 60, channel_rates: { wechat: 100, virtual_android: 100, virtual_ios: 1200 },
        shared_fees: [{ name: '技术服务费', mode: 'percent' as const, rate_bps: 500, basis: 'order_gross' as const }] } }
    expect(rewardCalculation(item)).toMatchObject({ channelRate: 60, channel: 12, commission: 1879, estimated: true,
      fees: [{ amount_fen: 99 }] })
    expect(rewardCalculation({ ...item, costs: { channel_fee_fen: 20, channel_rate_bps: 100,
      shared_fees: [{ name: '实际成本', amount_fen: 150 }], evidence: '核对凭据', confirmed: true }, commission_fen: 1820 }))
      .toMatchObject({ channelRate: 100, channel: 20, commission: 1820, estimated: false, fees: [{ name: '实际成本', amount_fen: 150 }] })
    expect(rewardCalculation({ ...item, policy: { ...item.policy, channel_rate_bps: null } }))
      .toMatchObject({ channelRate: null, channel: null, commission: null })
    expect(rewardCalculation({ ...item, costs: { channel_fee_fen: 15, shared_fees: [], evidence: '历史账单', confirmed: true }, commission_fen: 1975 }))
      .toMatchObject({ channelRate: null, channel: 15, commission: 1975, estimated: false })
  })
  it('申请费率按真实规则分组，百分比基数不同不混合，固定费用不伪装为百分比', () => {
    const base: ApplicationSnapshot['items'][number] = { order_id: 'a', revision: 1, amount_fen: 10000,
      payment_channel: 'virtual', device_platform: 'ios', costs: null,
      policy: { revision: 1, enabled: true, beneficiary: 'admin', rate_bps: 10000, hold_days: 14, shared_fees: [] },
      reference_channel_rate_bps: 1200, reference_channel_fen: 1200, reference_commission_fen: 8300,
      reference_fees: [{ name: '技术服务费', mode: 'percent', rate_bps: 500, basis: 'order_gross', base_fen: 10000, amount_fen: 500 }] }
    const wrapper = mount(SettlementRateSummary, { props: { items: [base,
      { ...base, order_id: 'b', amount_fen: 19900, reference_fees: [{ ...base.reference_fees[0]!, base_fen: 19900, amount_fen: 995 }] },
      { ...base, order_id: 'c', reference_fees: [{ ...base.reference_fees[0]!, basis: 'after_channel', base_fen: 8800, amount_fen: 440 }] },
      { ...base, order_id: 'd', reference_channel_rate_bps: null, reference_fees: [{ name: '资料费', amount_fen: 100 }] },
    ] } })
    expect(wrapper.findAll('dl')).toHaveLength(3)
    expect(wrapper.text()).toContain('2 笔 · 参考费率')
    expect(wrapper.text()).toContain('12%')
    expect(wrapper.text()).toContain('5%')
    expect(wrapper.text()).toContain('100%')
    expect(wrapper.text()).toContain('按扣支付手续费后金额')
    expect(wrapper.text()).toContain('固定金额 / 单')
    expect(wrapper.text()).toContain('未记录费率')
    wrapper.unmount()
  })
  it('普通微信与虚拟支付分开，未知设备保持待核对，并展示分组金额', () => {
    expect(channelLabel('wechat', 'ios')).toBe('普通微信支付')
    expect(channelLabel('virtual', 'ios')).toBe('虚拟支付 · iOS')
    expect(channelLabel('virtual', 'android')).toBe('虚拟支付 · 安卓/鸿蒙/Windows')
    expect(channelLabel('virtual', '')).toBe('渠道或设备待核对')
    const wrapper = mount(SettlementChannels, { props: { reference: true, channels: [
      { key: 'virtual_ios', label: '虚拟支付 · iOS', orders: 2, amount_fen: 20000, channel_fen: 2400, shared_fen: 880, commission_fen: 1672, unknown_rates: 0 },
      { key: 'unknown', label: '渠道或设备待核对', orders: 1, amount_fen: 10000, channel_fen: 0, shared_fen: 0, commission_fen: 1000, unknown_rates: 1 },
    ] } })
    expect(wrapper.text()).toContain('实收 ¥200.00 · 渠道费 ¥24.00')
    expect(wrapper.text()).toContain('税前奖励 ¥16.72')
    expect(wrapper.text()).toContain('1 笔渠道费率未知')
    expect(wrapper.text()).toContain('渠道费 待核对')
    expect(wrapper.text()).not.toContain('税前奖励 ¥10.00')
    wrapper.unmount()
  })
  it('渠道费率按实收计算，四舍五入到分，并展示计算公式', () => {
    expect(channelFeeFen(1990, 60)).toBe(12)
    expect(channelFeeFen(1, 5000)).toBe(1)
    expect(channelFeeFen(1, 4999)).toBe(0)
    const wrapper = mount(RewardCalculation, { props: { amount: 1990, channel: 12, channelRate: 60, fees: [], rate: 1000 } })
    expect(wrapper.text()).toContain('支付渠道费：订单实收 ¥19.90 × 0.6% = ¥0.12')
    expect(wrapper.text()).toContain('四舍五入到分')
    wrapper.unmount()
  })
  it('精确换算分，不将未填、非法金额或超过两位小数变成零', () => {
    expect(moneyFen('19.90')).toBe(1990)
    expect(moneyFen('0.29')).toBe(29)
    expect(moneyFen('0')).toBe(0)
    expect(moneyFen('-1.75', true)).toBe(-175)
    for (const value of ['', ' ', '1.001', '1e3', 'NaN', '-1', 'Infinity', '1,000', '100000000000000000']) expect(() => moneyFen(value)).toThrow()
  })
  it('每项费用都必须有名称和实际金额', () => {
    expect(feeValues([{ name: ' 资料成本 ', amount: '1.05' }])).toEqual([{ name: '资料成本', amount_fen: 105 }])
    expect(() => feeValues([{ name: '成本', amount: '' }])).toThrow()
    expect(() => feeValues([{ name: ' ', amount: '0' }])).toThrow()
  })
  it('按不同基数独立计算百分比，逐项到分，再算奖励', () => {
    const result = calculateReward(1990, 12, [{ name: '技术服务', mode: 'percent', rate_bps: 500, basis: 'after_channel' },
      { name: '运营分摊', mode: 'percent', rate_bps: 1000, basis: 'order_gross' }, { name: '资料费', amount_fen: 11 }], 2000)
    expect(result.fees.map(fee => fee.amount_fen)).toEqual([98, 199, 11])
    expect(result.distributable).toBe(1670)
    expect(result.commission).toBe(334)
    expect(calculateReward(1990, 2000, [{ name: '分摊', mode: 'percent', rate_bps: 500 }], 2000).commission).toBe(0)
  })
  it('重开百分比快照时只提交比例和基数，服务端计算金额', () => {
    const saved = [{ name: '服务费', mode: 'percent' as const, rate_bps: 500, basis: 'after_channel' as const, base_fen: 1978, amount_fen: 98 }]
    expect(sharedFeeValues(feeDrafts(saved))).toEqual([{ name: '服务费', mode: 'percent', rate_bps: 500, basis: 'after_channel' }])
    expect(sharedFeeValues([{ name: '固定费用', mode: 'fixed', rate: '90', amount: '1.00' }])).toEqual([{ name: '固定费用', amount_fen: 100 }])
    expect(() => feeValues(feeDrafts(saved))).toThrow('实际金额')
    for (const value of ['', '-1', '100.01', '0.001', 'NaN']) expect(() => percentageBps(value)).toThrow()
    expect(percentageBps('0.01')).toBe(1)
    expect(percentageBps('100')).toBe(10000)
  })
  it('展示每项费用基数、比例与奖励计算，已核对快照优先', () => {
    const wrapper = mount(RewardCalculation, { props: { amount: 10000, channel: 60, rate: 1000,
      fees: [{ name: '服务费', mode: 'percent', rate_bps: 500, basis: 'after_channel' }], commission: 944 } })
    expect(wrapper.text()).toContain('服务费：扣支付手续费后金额 ¥99.40 × 5% = ¥4.97')
    expect(wrapper.text()).toContain('税前奖励：¥94.43 × 10% = ¥9.44')
    wrapper.unmount()
  })
  it('未核定个税不显示到手金额，负余额显示结转', async () => {
    const wrapper = mount(SettlementCalculation, { props: { gross: 944, adjustment: -100, fees: [], tax: null } })
    expect(wrapper.text()).toContain('最终到手：待核对')
    await wrapper.setProps({ fees: [{ name: '转账费', amount_fen: 20 }], tax: 24 })
    expect(wrapper.text()).toContain('结算余额：¥9.44 − ¥1.00 − ¥0.20 − ¥0.24 = ¥8.00')
    expect(wrapper.text()).toContain('最终到手：max(0，¥8.00) = ¥8.00')
    await wrapper.setProps({ adjustment: -1000, fees: [], tax: 0 })
    expect(wrapper.text()).toContain('剩余扣回 ¥0.56')
    wrapper.unmount()
  })
  it('起步建议不包含虚构的实际税费或自动启用', () => {
    expect(starterPolicy()).toMatchObject({ rate_bps: 1000, hold_days: 14, shared_fees: [{ mode: 'percent', rate_bps: 0 }] })
    expect(starterPolicy().channel_rates).toEqual({ wechat: 60, virtual_android: 100, virtual_ios: 1200 })
    expect(starterPolicy()).not.toHaveProperty('enabled')
    expect(starterPolicy()).not.toHaveProperty('tax_fen')
  })
  it('历史申请缺少渠道费率时，不把原来的零费用试算展示成完整参考金额', async () => {
    const snapshot: ApplicationSnapshot = { items: [{ order_id: 'order-1', revision: 1, amount_fen: 10000,
      policy: { revision: 1, enabled: true, beneficiary: 'admin', rate_bps: 1000, hold_days: 14, shared_fees: [] }, costs: null,
      reference_channel_fen: 0, reference_fees: [{ name: '服务成本', mode: 'percent', rate_bps: 500, basis: 'after_channel', base_fen: 10000, amount_fen: 500 }], reference_commission_fen: 950 }],
    adjustments: [], reference_gross_fen: 950, adjustment_fen: 0, reference_after_adjustment_fen: 950, unconfirmed_orders: 1, personal_fen: null, tax_fen: null, net_fen: null }
    const wrapper = mount(SettlementApplicationSummary, { props: { snapshot } })
    expect(wrapper.text()).toContain('申请时参考税前奖励合计：待核对')
    expect(wrapper.text()).toContain('支付渠道费：待核对')
    expect(wrapper.text()).not.toContain('¥9.50')
    expect(wrapper.text()).toContain('个人承担费用：待对账确认')
    expect(wrapper.text()).toContain('实际代扣个人所得税：待核定')
    expect(wrapper.text()).toContain('申请时最终应付待审核')
    await wrapper.setProps({ snapshot: { ...snapshot, items: [{ ...snapshot.items[0]!, reference_channel_rate_bps: 0 }] } })
    expect(wrapper.text()).toContain('参考税前奖励：¥95.00 × 10% = ¥9.50')
    expect(wrapper.text()).toContain('支付渠道费：订单实收 ¥100.00 × 0% = ¥0.00')
    wrapper.unmount()
  })
  it('申请资格遵循服务器结果，异常订单不能只因满等待期就被当作可申请', () => {
    const reward = { status: 'pending', costs: null, statement_id: null, request_id: null, refund_status: null, available_at: 1 } as Reward
    expect(rewardApplicationState({ ...reward, application_state: 'exception' })).toBe('exception')
    expect(rewardApplicationState({ ...reward, application_state: 'available' })).toBe('available')
    expect(rewardApplicationState({ ...reward, application_state: 'holding' })).toBe('holding')
    expect(rewardApplicationState(reward)).toBe('exception')
  })
  it('未知参考与核定金额的对比不显示虚构的金额增减', () => {
    const wrapper = mount(SettlementDifference, { props: { value: {
      reference_gross_fen: null, actual_gross_fen: 375, adjustment_before_fen: 0, adjustment_after_fen: 0, reason: '',
      items: [{ order_id: 'order-1', before_fen: null, after_fen: 375, channel_before_fen: null, channel_after_fen: 12,
        fees: [{ name: '服务费', before_fen: null, after_fen: 100 }] }],
    } } })
    expect(wrapper.text()).toContain('税前奖励：待核对 → ¥3.75')
    expect(wrapper.findAll('tbody tr').every(row => row.findAll('td')[3]?.text() === '待核对')).toBe(true)
    wrapper.unmount()
  })
})
