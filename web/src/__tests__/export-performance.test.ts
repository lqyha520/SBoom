import { afterEach, expect, it, vi } from 'vitest'
import { measureExport } from '../export-performance'

afterEach(() => { vi.restoreAllMocks(); performance.clearMeasures('lc.export.encode') })

it('长批次导出的阶段计时保持有界', async () => {
  for (let i = 0; i < 125; i++) await measureExport('encode', async () => i)
  expect(performance.getEntriesByName('lc.export.encode', 'measure').length).toBeLessThanOrEqual(60)
})

it('计时 API 不兼容时保留导出结果和原始错误', async () => {
  vi.spyOn(performance, 'measure').mockImplementation(() => { throw new TypeError('unsupported') })
  await expect(measureExport('encode', async () => 'PDF')).resolves.toBe('PDF')
  await expect(measureExport('encode', async () => { throw new Error('encoding failed') })).rejects.toThrow('encoding failed')
})
