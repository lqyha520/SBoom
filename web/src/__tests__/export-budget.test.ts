import { expect, it } from 'vitest'
import { ExportBudget, EXPORT_LIMITS } from '../export-budget'

it('页数和编码数据累计到上限仍有效，下一份超限停止', () => {
  const budget = new ExportBudget()
  budget.reservePages(40); budget.reservePages(40); budget.reservePages(40)
  expect(() => budget.reservePages(1)).toThrow('容量上限')
  budget.retain(EXPORT_LIMITS.bytes)
  expect(() => budget.retain(1)).toThrow('容量上限')
  budget.checkFile(EXPORT_LIMITS.fileBytes)
  expect(() => budget.checkFile(EXPORT_LIMITS.fileBytes + 1)).toThrow('容量上限')
})

it('无效数字不能绕过限制，每次导出使用独立预算', () => {
  for (const value of [NaN, Infinity, -1, 0.5]) {
    expect(() => new ExportBudget().reservePages(value)).toThrow()
    expect(() => new ExportBudget().retain(value)).toThrow()
    expect(() => new ExportBudget().checkFile(value)).toThrow()
  }
  expect(() => new ExportBudget().reservePages(0)).toThrow()
  new ExportBudget().retain(EXPORT_LIMITS.bytes)
  expect(() => new ExportBudget().retain(1)).not.toThrow()
})
