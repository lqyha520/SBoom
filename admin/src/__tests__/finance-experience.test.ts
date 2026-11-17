import { expect, it } from 'vitest'
import { financeDateRange } from '../finance-experience'

it('成本快捷日期按北京时间跨日和闰月计算', () => {
  const now = new Date('2024-02-29T16:30:00Z')
  expect(financeDateRange('month', now)).toEqual({ start: '2024-03-01', end: '2024-03-01' })
  expect(financeDateRange('previous', now)).toEqual({ start: '2024-02-01', end: '2024-02-29' })
})
it('跨年上月范围完整，全部日期清除两个边界', () => {
  const now = new Date('2026-12-31T16:00:00Z')
  expect(financeDateRange('previous', now)).toEqual({ start: '2026-12-01', end: '2026-12-31' })
  expect(financeDateRange('all', now)).toEqual({ start: '', end: '' })
})
