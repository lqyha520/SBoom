export interface ServiceTerms { review_days?: number | null; payout_days?: number | null }
export function settlementTarget(status: string, terms: ServiceTerms | undefined, submittedAt: number, approvedAt?: number | null) {
  const review = status === 'pending' || status === 'reviewing'
  if (!review && status !== 'approved') return null
  const days = review ? terms?.review_days : terms?.payout_days
  const origin = review ? submittedAt : approvedAt
  return { label: review ? '审核处理目标' : '付款处理目标', dueAt: days != null && origin != null ? origin + days * 86400 : null }
}
export function processingDays(value: string) {
  const text = String(value).trim()
  if (!text) return null
  if (!/^\d+$/.test(text) || Number(text) < 1 || Number(text) > 90) throw new Error('处理目标须填写 1 至 90 个自然日，或留空')
  return Number(text)
}
