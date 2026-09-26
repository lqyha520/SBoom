import { describe, expect, it } from 'vitest'
import { paginateSections, type MeasuredSection } from '../paper-pagination'

const segment = (sec: number, rows: number[], rowStride = 1): MeasuredSection => ({
  sec,
  rows,
  rowStride,
  headBlockH: 20,
  total: rows.length * rowStride,
})
describe('卷尾空间与页段完整性', () => {
  it('满页两大题为卷尾让出空间', () => {
    const pages = paginateSections([segment(0, [400]), segment(1, [400])], 900, 100)
    expect(pages.map((page) => page.map((chunk) => chunk.sec))).toEqual([[0], [1]])
  })
  it('单个大题将最后一行与卷尾移到新页，保留题号和题目', () => {
    expect(paginateSections([segment(0, [280, 280, 280], 2)], 900, 100)).toEqual([
      [{ sec: 0, qFrom: 0, qTo: 4, first: true }],
      [{ sec: 0, qFrom: 4, qTo: 6, first: false }],
    ])
  })
  it('单题与卷尾无法共页时卷尾独占末页', () => {
    expect(paginateSections([segment(0, [840])], 900, 100)).toEqual([[{ sec: 0, qFrom: 0, qTo: 1, first: true }], []])
  })
  it('没有题目的说明大题也保留', () => {
    const pages = paginateSections([segment(0, [840]), { ...segment(1, []), headBlockH: 100 }], 900, 80)
    expect(pages.flat().map((chunk) => chunk.sec)).toEqual([0, 1])
  })
  it('分页后的题目不遗漏、不重复，末页为页脚留足空间', () => {
    for (let count = 1; count <= 30; count++) {
      const input = segment(
        0,
        Array.from({ length: count }, () => 90),
      )
      const pages = paginateSections([input], 900, 150)
      expect(
        pages.flat().flatMap((chunk) => Array.from({ length: chunk.qTo - chunk.qFrom }, (_, i) => chunk.qFrom + i)),
      ).toEqual(Array.from({ length: count }, (_, i) => i))
      const lastHeight = pages
        .at(-1)!
        .reduce((sum, chunk) => sum + (chunk.first ? 20 : 0) + (chunk.qTo - chunk.qFrom) * 90, 150)
      expect(lastHeight).toBeLessThanOrEqual(900)
    }
  })
})
