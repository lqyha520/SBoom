import type { ConversionData } from '../src/referral-conversion'
import type { RewardPolicy } from '../src/settlements'
export const promotionRules: RewardPolicy = {
  revision: 1, enabled: true, beneficiary: 'admin', rate_bps: 1000, hold_days: 14,
  max_reward_fen: 500, channel_rate_bps: 60, channel_rates: { wechat: 60, virtual_android: 100, virtual_ios: 1200 },
  shared_fees: [], review_days: 3, payout_days: 2,
}
export const emptyConversion: ConversionData = {
  summary: { registrations: 0, ordered_users: 0, paying_users: 0, not_ordered_users: 0, unpaid_users: 0,
    order_rate_bps: null, pay_rate_bps: null, order_pay_rate_bps: null },
  items: [], total: 0, page: 1, as_of: 1794360000,
}
