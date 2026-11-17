export type FinanceDatePreset = 'month' | 'previous' | 'all'

/** 月份边界按北京时间计算，截止日期包含当天。 */
export function financeDateRange(preset: FinanceDatePreset, now = new Date()) {
  if (preset === 'all') return { start: '', end: '' }
  const day = new Date(now.getTime() + 8 * 3600000)
  const year = day.getUTCFullYear(), month = day.getUTCMonth()
  const date = (stamp: number) => new Date(stamp).toISOString().slice(0, 10)
  return preset === 'month'
    ? { start: date(Date.UTC(year, month, 1)), end: day.toISOString().slice(0, 10) }
    : { start: date(Date.UTC(year, month - 1, 1)), end: date(Date.UTC(year, month, 0)) }
}
