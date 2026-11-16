export interface Referral {
  campaign_id?: string; campaign_name?: string; campaign_source?: string
  source: 'legacy' | 'natural' | 'admin' | 'user' | 'manual'
  admin_id?: number | null
  admin_name?: string
  inviter_type?: 'admin' | 'user'
  inviter_id?: string
  inviter_name?: string
  bound_at?: number
}
export const referralSources = { legacy: '历史来源未知', natural: '自然注册', admin: '管理员推广', user: '用户邀请', manual: '人工补录' }
export const referralSource = (value?: Referral) => referralSources[value?.source || 'legacy']
