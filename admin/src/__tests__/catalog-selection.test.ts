import { expect, it } from 'vitest'
import { useCatalogSelection } from '../catalog-selection'
import type { CatalogPaper } from '../catalog'
const papers = (start: number, count: number) => Array.from({ length: count }, (_, index) => ({ id: String(index + start), revision: 2 } as CatalogPaper))
it('跨页选择最多50份，取消当前页保留其他页以及选择时的版本', () => {
  const state = useCatalogSelection()
  expect(state.page(papers(0, 20), true)).toBe(true)
  expect(state.page(papers(20, 20), true)).toBe(true)
  expect(state.page(papers(40, 20), true)).toBe(false)
  expect(state.selected.value).toHaveLength(40)
  state.page(papers(0, 20), false)
  expect(state.ids.value).toEqual(papers(20, 20).map(item => item.id))
  state.page([{ id: '20', revision: 9 } as CatalogPaper], true)
  expect(state.selected.value[0]?.revision).toBe(2)
})
